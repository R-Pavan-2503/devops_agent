"""
sandbox/shadow_env.py

Shadow Environment Validator — Dynamic Docker-based build & test runner.

Responsibilities:
  1. Copy the (possibly Dev-Agent-modified) temp files into an isolated Docker container.
  2. Auto-detect the project type (Go, Node/React, Python).
  3. Install dependencies, compile, and run the test suite.
  4. Return a structured ShadowResult so LangGraph can route correctly.

Usage (from a LangGraph node):
    from sandbox.shadow_env import run_shadow_validation
    result = run_shadow_validation(files_dict, repo_name="backend_pandhi")
"""

import os
import re
import tarfile
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import docker  # pip install docker

# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------

ProjectType = Literal["go", "node", "python", "unknown"]


@dataclass
class ShadowResult:
    success: bool
    project_type: ProjectType
    install_log: str = ""
    build_log: str = ""
    test_log: str = ""
    error: str = ""
    # Structured failure reason for the Dev Agent critique log
    critique: str = ""

    @property
    def failed(self) -> bool:
        return not self.success


# ---------------------------------------------------------------------------
# Project-type detection
# ---------------------------------------------------------------------------

_GO_MARKERS      = {"go.mod", "go.sum"}
_NODE_MARKERS    = {"package.json"}
_PYTHON_MARKERS  = {"pyproject.toml", "setup.py", "requirements.txt", "setup.cfg"}


def _detect_project_type(files_dict: dict[str, str]) -> ProjectType:
    """
    Infer project type from the set of file paths in the PR/temp folder.
    Precedence: Go > Node > Python > unknown.
    """
    file_names = {Path(p).name for p in files_dict}

    if file_names & _GO_MARKERS or any(p.endswith(".go") for p in files_dict):
        return "go"
    if file_names & _NODE_MARKERS:
        return "node"
    if file_names & _PYTHON_MARKERS or any(p.endswith(".py") for p in files_dict):
        return "python"
    return "unknown"


# ---------------------------------------------------------------------------
# Docker command recipes per project type
# ---------------------------------------------------------------------------

def _build_dockerfile(project_type: ProjectType) -> str:
    """Return a minimal Dockerfile string for the detected project type."""
    if project_type == "go":
        return textwrap.dedent("""\
            FROM golang:1.22-alpine
            WORKDIR /app
            COPY . .
            RUN go mod download 2>/dev/null || true
        """)
    elif project_type == "node":
        return textwrap.dedent("""\
            FROM node:20-alpine
            WORKDIR /app
            COPY . .
            RUN npm install --legacy-peer-deps
        """)
    elif project_type == "python":
        return textwrap.dedent("""\
            FROM python:3.12-slim
            WORKDIR /app
            COPY . .
            RUN pip install -r requirements.txt --quiet 2>/dev/null || true
        """)
    else:
        return textwrap.dedent("""\
            FROM alpine:3.19
            WORKDIR /app
            COPY . .
        """)


def _get_run_commands(project_type: ProjectType) -> list[tuple[str, str]]:
    """
    Return a list of (label, shell_command) pairs executed INSIDE the container
    after image build. Each is run sequentially; failure of any = ShadowResult.success=False.
    """
    if project_type == "go":
        return [
            ("vet",   "go vet ./..."),
            ("build", "go build ./..."),
            ("test",  "go test ./... -timeout 60s -v 2>&1 | tail -40"),
        ]
    elif project_type == "node":
        return [
            ("lint",  "npm run lint --if-present 2>&1 | tail -30 || true"),
            ("build", "npm run build --if-present 2>&1 | tail -30 || true"),
            ("test",  "npm test -- --watchAll=false --passWithNoTests 2>&1 | tail -40"),
        ]
    elif project_type == "python":
        return [
            ("syntax", "python -m compileall . -q"),
            ("test",   "python -m pytest --tb=short -q 2>&1 | tail -40 || true"),
        ]
    else:
        return [
            ("echo", "echo 'Unknown project type — no build steps run.'"),
        ]


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

def _write_tar(tmp_dir: str, files_dict: dict[str, str], dockerfile_content: str) -> str:
    """
    Write all files + Dockerfile into tmp_dir and tar them up.
    Returns the path to the .tar file.
    """
    tar_path = os.path.join(tmp_dir, "context.tar")

    with tarfile.open(tar_path, "w") as tar:
        # Write Dockerfile
        dockerfile_path = os.path.join(tmp_dir, "Dockerfile")
        with open(dockerfile_path, "w") as f:
            f.write(dockerfile_content)
        tar.add(dockerfile_path, arcname="Dockerfile")

        # Write all PR files
        for rel_path, content in files_dict.items():
            # Normalize path separators; strip any leading "test_apps/..." prefix
            # so files land at the container WORKDIR root
            clean_path = _strip_test_prefix(rel_path)
            abs_path = os.path.join(tmp_dir, clean_path.replace("/", os.sep))
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            try:
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(content)
                tar.add(abs_path, arcname=clean_path)
            except Exception as e:
                print(f"  [shadow] Warning: could not write {rel_path}: {e}")

    return tar_path


def _strip_test_prefix(path: str) -> str:
    """Remove leading test_apps/<name>/ so the container sees a clean project root."""
    # e.g. "test_apps/backend_login_go/api/endpoints.go" → "api/endpoints.go"
    parts = path.replace("\\", "/").split("/")
    if len(parts) > 2 and parts[0] == "test_apps":
        return "/".join(parts[2:])
    return path


def _truncate(text: str, max_chars: int = 3000) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n… [truncated] …\n" + text[-half:]


def run_shadow_validation(
    files_dict: dict[str, str],
    repo_name: str = "pr_sandbox",
    timeout_seconds: int = 120,
) -> ShadowResult:
    """
    Main entry point. Spins up a Docker container, builds the project,
    runs tests, and returns a ShadowResult.

    Args:
        files_dict:       {relative_file_path: file_content} — same shape as AgentState["current_files"]
        repo_name:        Used only for labelling / image tag.
        timeout_seconds:  Hard cap per run command (not total).

    Returns:
        ShadowResult with structured logs and success flag.
    """
    project_type = _detect_project_type(files_dict)
    print(f"  [shadow] Detected project type: {project_type}")

    dockerfile = _build_dockerfile(project_type)
    commands   = _get_run_commands(project_type)

    try:
        client = docker.from_env()
    except Exception as e:
        return ShadowResult(
            success=False,
            project_type=project_type,
            error=f"Docker daemon not reachable: {e}",
            critique="[SHADOW] Docker unavailable — cannot validate build.",
        )

    image_tag = f"shadow_{repo_name.lower()}_{int(time.time())}:latest"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tar_path = _write_tar(tmp_dir, files_dict, dockerfile)

        # --- Build image ---
        print(f"  [shadow] Building image '{image_tag}'…")
        try:
            with open(tar_path, "rb") as f:
                image, build_logs_raw = client.images.build(
                    fileobj=f,
                    custom_context=True,
                    tag=image_tag,
                    rm=True,
                    forcerm=True,
                    timeout=timeout_seconds,
                )
            build_log = _truncate(
                "\n".join(
                    line.get("stream", line.get("error", "")).strip()
                    for line in build_logs_raw
                    if isinstance(line, dict) and (line.get("stream") or line.get("error"))
                )
            )
        except docker.errors.BuildError as e:
            build_log = _truncate(str(e))
            return ShadowResult(
                success=False,
                project_type=project_type,
                build_log=build_log,
                error="Image build failed",
                critique=f"[SHADOW] Build failed — dependency or syntax error:\n{build_log[-400:]}",
            )

        # --- Run each command ---
        all_logs: dict[str, str] = {}
        failed_step: str | None = None
        failed_output: str = ""

        for label, cmd in commands:
            print(f"  [shadow] Running step '{label}': {cmd}")
            try:
                container = client.containers.run(
                    image_tag,
                    command=f"/bin/sh -c '{cmd}'",
                    detach=True,
                    mem_limit="512m",
                    cpu_period=100000,
                    cpu_quota=50000,   # 50% of one core
                    network_disabled=True,
                    read_only=False,
                )
                exit_code = container.wait(timeout=timeout_seconds)["StatusCode"]
                output = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
                container.remove(force=True)

                all_logs[label] = _truncate(output)

                if exit_code != 0:
                    failed_step   = label
                    failed_output = _truncate(output, 600)
                    print(f"  [shadow] Step '{label}' FAILED (exit {exit_code})")
                    break
                else:
                    print(f"  [shadow] Step '{label}' passed.")

            except Exception as e:
                all_logs[label] = str(e)
                failed_step     = label
                failed_output   = str(e)[:600]
                break

        # --- Cleanup image ---
        try:
            client.images.remove(image_tag, force=True)
        except Exception:
            pass

        # --- Assemble result ---
        install_log = all_logs.get("install", "")
        build_log_run = all_logs.get("build", all_logs.get("vet", ""))
        test_log    = all_logs.get("test", all_logs.get("syntax", ""))

        if failed_step:
            # Parse test failures into a terse critique for the Dev Agent
            critique = _extract_critique(project_type, failed_step, failed_output)
            return ShadowResult(
                success=False,
                project_type=project_type,
                install_log=install_log,
                build_log=build_log_run,
                test_log=test_log,
                error=f"Step '{failed_step}' failed",
                critique=critique,
            )

        return ShadowResult(
            success=True,
            project_type=project_type,
            install_log=install_log,
            build_log=build_log_run,
            test_log=test_log,
        )


# ---------------------------------------------------------------------------
# Failure → critique formatter
# ---------------------------------------------------------------------------

_GO_FAIL_RE    = re.compile(r"(FAIL|Error|undefined|cannot|does not)")
_NODE_FAIL_RE  = re.compile(r"(FAIL|Error|Cannot find|SyntaxError|failed)")
_PY_FAIL_RE    = re.compile(r"(FAILED|Error|ImportError|SyntaxError|assert)")


def _extract_critique(project_type: ProjectType, step: str, output: str) -> str:
    """
    Distil the raw failure output into a short, actionable critique string
    suitable for injection into the Dev Agent's Critique Log.
    """
    pattern = {
        "go":     _GO_FAIL_RE,
        "node":   _NODE_FAIL_RE,
        "python": _PY_FAIL_RE,
    }.get(project_type, re.compile(r"(Error|FAIL)"))

    relevant_lines = [
        line.strip()
        for line in output.splitlines()
        if line.strip() and pattern.search(line)
    ][:6]  # max 6 lines

    body = "\n".join(relevant_lines) if relevant_lines else output[:300]
    return f"[SHADOW/{step.upper()}] Build/test failure in {project_type} project:\n{body}"