"""
agents/sandbox.py

Ephemeral Sandbox Environment for the Dev Agent's 3-Round Fix Loop.

Architecture:
  - setup_workspace()      → Create a temp dir on the host, write all initial files.
  - update_workspace_files() → Overwrite specific files between iterations (rounds 2, 3).
  - run_tests_in_docker()  → Bind-mount the workspace into a fresh, network-isolated
                             container, run the test command, capture output, kill on timeout.
  - teardown_workspace()   → Nuke the temp dir after all 3 rounds are exhausted.

Container lifecycle is fully isolated from workspace lifecycle:
  - A new container is created per round (cheap, clean).
  - The host workspace directory persists across all 3 rounds.
  - teardown_workspace() is called exactly once — after the loop finishes.
"""

import os
import shutil
import tempfile
import logging
import atexit
from pathlib import Path
from typing import Optional

import docker
from docker.errors import DockerException, ContainerError, ImageNotFound, APIError
from docker.types import Mount

# ---------------------------------------------------------------------------
# Orphan Workspace Cleanup (atexit hook)
# ---------------------------------------------------------------------------
_active_workspaces = set()

def _cleanup_orphans():
    """Forces cleanup of any sandbox workspaces if the process is terminated abruptly."""
    for path in list(_active_workspaces):
        if os.path.exists(path):
            try:
                shutil.rmtree(path, ignore_errors=True)
                print(f"[sandbox] Cleaned up orphaned workspace on exit: {path}")
            except Exception:
                pass

atexit.register(_cleanup_orphans)

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[sandbox] %(levelname)s: %(message)s"))
    logger.addHandler(_handler)


# ---------------------------------------------------------------------------
# Public Dataclass for Test Results
# ---------------------------------------------------------------------------

class SandboxResult:
    """
    Structured result returned from run_tests_in_docker().

    Attributes:
        exit_code   : Container exit code (0 = pass, non-zero = fail, -1 = timeout/error).
        passed      : True if exit_code == 0.
        stdout      : Raw stdout captured from the container.
        stderr      : Raw stderr captured from the container.
        timed_out   : True if the container was killed due to the 60-second timeout.
        error       : Human-readable error string for infrastructure failures.
    """

    __slots__ = ("exit_code", "passed", "stdout", "stderr", "timed_out", "error")

    def __init__(
        self,
        exit_code: int = -1,
        passed: bool = False,
        stdout: str = "",
        stderr: str = "",
        timed_out: bool = False,
        error: str = "",
    ):
        self.exit_code = exit_code
        self.passed = passed
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.error = error

    def __repr__(self) -> str:
        return (
            f"SandboxResult(passed={self.passed}, exit_code={self.exit_code}, "
            f"timed_out={self.timed_out}, error={self.error!r})"
        )


# ---------------------------------------------------------------------------
# 1. Workspace Setup
# ---------------------------------------------------------------------------

def setup_workspace(file_structure_dict: dict[str, str]) -> str:
    """
    Create a temporary workspace directory on the host and write all
    initial source files into it, preserving multi-level path structure.

    Args:
        file_structure_dict: A mapping of {relative_file_path: file_content}.
                             Paths may contain subdirectories, e.g.
                             {"src/utils/math.go": "package utils\\n..."}.

    Returns:
        workspace_path: The absolute path to the created temp directory.

    Example:
        workspace_path = setup_workspace({
            "main.go": "package main\\n...",
            "api/endpoints.go": "package api\\n...",
        })
        # → "/tmp/devops_sandbox_xyz/"
    """
    workspace_path = tempfile.mkdtemp(prefix="devops_sandbox_")
    logger.info("Workspace created at: %s", workspace_path)

    for relative_path, content in file_structure_dict.items():
        # Normalize separators so Windows-style paths work uniformly
        normalized = relative_path.replace("\\", "/")
        absolute_path = os.path.join(workspace_path, normalized)

        # Create all intermediate directories in the path
        parent_dir = os.path.dirname(absolute_path)
        os.makedirs(parent_dir, exist_ok=True)

        with open(absolute_path, "w", encoding="utf-8") as fh:
            fh.write(content)

        logger.debug("  Wrote %d bytes → %s", len(content), normalized)

    logger.info("Workspace initialized with %d file(s).", len(file_structure_dict))
    _active_workspaces.add(workspace_path)
    return workspace_path


# ---------------------------------------------------------------------------
# 2. Direct File Modification (between iterations)
# ---------------------------------------------------------------------------

def update_workspace_files(
    workspace_path: str,
    file_updates: dict[str, str],
) -> None:
    """
    Overwrite specific files within the existing workspace with new content
    provided by the Dev Agent after each review iteration.

    This does NOT recreate the workspace — it surgically patches only the
    files that the LLM decided to rewrite, leaving others untouched.

    Args:
        workspace_path : Absolute path returned by setup_workspace().
        file_updates   : Mapping of {relative_file_path: new_content} for
                         files that need to be overwritten.

    Raises:
        ValueError: If workspace_path does not exist.
    """
    if not os.path.isdir(workspace_path):
        raise ValueError(
            f"Workspace path does not exist or is not a directory: {workspace_path!r}"
        )

    for relative_path, new_content in file_updates.items():
        normalized = relative_path.replace("\\", "/")
        absolute_path = os.path.join(workspace_path, normalized)

        # Create parent dirs in case the Dev Agent generates a brand-new file
        parent_dir = os.path.dirname(absolute_path)
        os.makedirs(parent_dir, exist_ok=True)

        with open(absolute_path, "w", encoding="utf-8") as fh:
            fh.write(new_content)

        logger.debug("  Updated %d bytes → %s", len(new_content), normalized)

    logger.info("Workspace patched: %d file(s) updated.", len(file_updates))


# ---------------------------------------------------------------------------
# 3. Docker Test Execution
# ---------------------------------------------------------------------------

_CONTAINER_WORKDIR = "/workspace"
_TIMEOUT_SECONDS = 60


def run_tests_in_docker(
    workspace_path: str,
    test_command: str,
    docker_image: str = "golang:1.22-alpine",
    timeout: int = _TIMEOUT_SECONDS,
) -> SandboxResult:
    """
    Bind-mount the host workspace into an ephemeral, network-isolated Docker
    container and execute the test command.

    Container Lifecycle (per iteration):
      1. Pull/resolve image (cached by Docker daemon).
      2. Create container with bind-mount + security constraints.
      3. Start → wait (up to `timeout` seconds).
      4. Capture exit code + combined logs.
      5. Kill + remove container unconditionally (try/finally).
      → Host workspace folder is LEFT INTACT for the next iteration.

    Args:
        workspace_path : Absolute host path (from setup_workspace).
        test_command   : Shell command string, e.g. "go test ./... -v".
        docker_image   : Docker image to run the tests in.
        timeout        : Seconds before the container is forcibly killed.

    Returns:
        SandboxResult with exit_code, stdout, stderr, timed_out, etc.
    """
    result = SandboxResult()
    client: Optional[docker.DockerClient] = None
    container = None

    try:
        client = docker.from_env()
        client.ping()  # Fast connectivity check — fails loudly if Docker is down
    except DockerException as exc:
        result.error = f"Docker daemon unreachable: {exc}"
        logger.error(result.error)
        return result

    # Resolve absolute path for bind-mount (Docker on Windows needs this)
    host_path = str(Path(workspace_path).resolve())

    # Docker SDK bind-mount specification
    mount = Mount(
        target=_CONTAINER_WORKDIR,
        source=host_path,
        type="bind",
        read_only=False,  # Dev Agent writes files; container only reads them
    )

    try:
        logger.info(
            "Spawning container | image=%s | timeout=%ds | cmd=%s",
            docker_image,
            timeout,
            test_command,
        )

        container = client.containers.create(
            image=docker_image,
            command=["/bin/sh", "-c", test_command],
            working_dir=_CONTAINER_WORKDIR,
            mounts=[mount],
            # ── Security constraints ─────────────────────────────────────
            network_disabled=True,           # No outbound/inbound network
            read_only=False,                 # Needed for test caches (e.g. go build cache)
            # ── Resource caps ────────────────────────────────────────────
            mem_limit="512m",
            nano_cpus=1_000_000_000,         # 1 vCPU
            # ── Metadata ─────────────────────────────────────────────────
            labels={"managed_by": "devops_sandbox"},
            detach=True,
        )

        container.start()
        logger.debug("Container started: %s", container.short_id)

        # ── Blocking wait with hard timeout ──────────────────────────────
        wait_response = container.wait(timeout=timeout)
        result.exit_code = wait_response.get("StatusCode", -1)
        result.timed_out = False

    except Exception as timeout_exc:
        # docker-py raises requests.exceptions.ReadTimeout on wait() expiry
        error_name = type(timeout_exc).__name__
        if "Timeout" in error_name or "ReadTimeout" in error_name:
            result.timed_out = True
            result.exit_code = -1
            result.error = (
                f"Container timed out after {timeout}s and was killed. "
                f"Original error: {timeout_exc}"
            )
            logger.warning(result.error)
            if container:
                try:
                    container.kill()
                    logger.debug("Container %s killed (timeout).", container.short_id)
                except APIError:
                    pass  # Already dead — ignore
        else:
            result.exit_code = -1
            result.error = f"Unexpected error during container execution: {timeout_exc}"
            logger.exception(result.error)

    finally:
        # ── Always capture logs before removal ───────────────────────────
        if container:
            try:
                raw_logs = container.logs(stdout=True, stderr=True, stream=False)
                combined = raw_logs.decode("utf-8", errors="replace") if isinstance(raw_logs, bytes) else str(raw_logs)

                # Attempt to split stdout / stderr separately; fall back to combined
                try:
                    result.stdout = container.logs(stdout=True, stderr=False, stream=False).decode("utf-8", errors="replace")
                    result.stderr = container.logs(stdout=False, stderr=True, stream=False).decode("utf-8", errors="replace")
                except Exception:
                    result.stdout = combined
                    result.stderr = ""

            except Exception as log_exc:
                logger.warning("Could not capture container logs: %s", log_exc)
                result.stderr = f"[Log capture failed: {log_exc}]"

            # ── Guaranteed container removal ──────────────────────────────
            try:
                container.remove(force=True)
                logger.debug("Container %s removed.", container.short_id)
            except APIError as rm_exc:
                logger.warning("Container removal failed (non-fatal): %s", rm_exc)

    # Determine pass/fail
    result.passed = (result.exit_code == 0)

    if result.passed:
        logger.info("✅ Tests PASSED (exit_code=0).")
    elif result.timed_out:
        logger.warning("⏱️  Tests TIMED OUT after %ds.", timeout)
    else:
        logger.warning(
            "❌ Tests FAILED (exit_code=%d).\n--- STDOUT ---\n%s\n--- STDERR ---\n%s",
            result.exit_code,
            result.stdout[:2000],
            result.stderr[:2000],
        )

    return result


# ---------------------------------------------------------------------------
# 4. Workspace Teardown (called once, after all 3 rounds)
# ---------------------------------------------------------------------------

def teardown_workspace(workspace_path: str) -> None:
    """
    Permanently delete the workspace directory and all its contents from
    the host machine. Call this ONLY after the 3-round fix loop is complete.

    Leaves zero footprint on the host filesystem.

    Args:
        workspace_path: Absolute path previously returned by setup_workspace().

    Raises:
        ValueError: If the path is obviously dangerous (e.g. root or home dir).
    """
    resolved = str(Path(workspace_path).resolve())

    # Safety guard: refuse to delete obviously dangerous paths
    _FORBIDDEN = {"/", os.path.expanduser("~"), "C:\\", "C:\\Users"}
    if resolved in _FORBIDDEN or len(resolved) < 10:
        raise ValueError(
            f"Refusing to delete suspicious path: {resolved!r}. "
            "This does not look like a sandbox directory."
        )

    if not os.path.exists(resolved):
        logger.info("Workspace already gone (or never existed): %s", resolved)
        return

    shutil.rmtree(resolved, ignore_errors=False)
    _active_workspaces.discard(resolved)
    logger.info("Workspace torn down: %s", resolved)
