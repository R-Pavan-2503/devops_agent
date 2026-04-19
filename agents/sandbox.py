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

Go module cache:
  The container runs with network_disabled=True, so `go get` cannot download packages.
  To resolve external imports (e.g. golang.org/x/crypto/bcrypt), the host's Go module
  cache is bind-mounted read-only at /root/go/pkg/mod inside the container and
  GOMODCACHE / GOPROXY=off are set so the toolchain reads from cache only.
"""

import os
import platform
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

    Args:
        workspace_path : Absolute path returned by setup_workspace().
        file_updates   : Mapping of {relative_file_path: new_content}.

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

        parent_dir = os.path.dirname(absolute_path)
        os.makedirs(parent_dir, exist_ok=True)

        with open(absolute_path, "w", encoding="utf-8") as fh:
            fh.write(new_content)

        logger.debug("  Updated %d bytes → %s", len(new_content), normalized)

    logger.info("Workspace patched: %d file(s) updated.", len(file_updates))


# ---------------------------------------------------------------------------
# Go module cache helpers
# ---------------------------------------------------------------------------

def _get_host_gomodcache() -> Optional[Path]:
    """
    Return the host machine's Go module cache directory, or None if not found.

    Search order:
      1. $GOMODCACHE env var (explicit override)
      2. $GOPATH/pkg/mod
      3. ~/go/pkg/mod  (default GOPATH on Linux/Mac)
      4. %USERPROFILE%\go\pkg\mod  (default GOPATH on Windows)
    """
    # Explicit GOMODCACHE override
    explicit = os.environ.get("GOMODCACHE", "")
    if explicit and Path(explicit).is_dir():
        return Path(explicit).resolve()

    # $GOPATH/pkg/mod
    gopath_env = os.environ.get("GOPATH", "")
    if gopath_env:
        candidate = Path(gopath_env) / "pkg" / "mod"
        if candidate.is_dir():
            return candidate.resolve()

    # Platform default: ~/go/pkg/mod (Linux/Mac) or %USERPROFILE%\go\pkg\mod (Windows)
    if platform.system() == "Windows":
        home = os.environ.get("USERPROFILE", "")
    else:
        home = os.path.expanduser("~")

    if home:
        candidate = Path(home) / "go" / "pkg" / "mod"
        if candidate.is_dir():
            return candidate.resolve()

    return None


# ---------------------------------------------------------------------------
# 3. Docker Test Execution
# ---------------------------------------------------------------------------

_CONTAINER_WORKDIR = "/workspace"
_TIMEOUT_SECONDS   = 60
_GOMODCACHE_CONTAINER = "/root/go/pkg/mod"


def run_tests_in_docker(
    workspace_path: str,
    test_command: str,
    docker_image: str = "golang:1.22-alpine",
    timeout: int = _TIMEOUT_SECONDS,
) -> SandboxResult:
    """
    Bind-mount the host workspace into an ephemeral, network-isolated Docker
    container and execute the test command.

    External Go packages are resolved by mounting the host's GOMODCACHE read-only
    at /root/go/pkg/mod and setting GOPROXY=off so the toolchain never tries to
    reach the network. This keeps the container isolated while still allowing
    packages already cached on the host (e.g. golang.org/x/crypto) to be used.

    Args:
        workspace_path : Absolute host path (from setup_workspace).
        test_command   : Shell command string, e.g. "go vet ./...".
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
        client.ping()
    except DockerException as exc:
        result.error = f"Docker daemon unreachable: {exc}"
        logger.error(result.error)
        return result

    host_path = str(Path(workspace_path).resolve())

    # Workspace mount (read-write so the Go build cache can be written)
    # AFTER:
    workspace_mount = Mount(
        target=_CONTAINER_WORKDIR,
        source=host_path,
        type="bind",
        read_only=False,
    )

    # Mount host Go module cache so deps resolve without network access.
    # Covers Windows (C:\Users\<user>\go\pkg\mod) and Linux/Mac (~/go/pkg/mod).
    _GO_MOD_CACHE_HOST = os.path.join(os.path.expanduser("~"), "go", "pkg", "mod")
    _GO_MOD_CACHE_HOST = str(Path(_GO_MOD_CACHE_HOST).resolve())
    _GO_MOD_CACHE_CONTAINER = "/root/go/pkg/mod"

    mounts = [workspace_mount]
    if os.path.isdir(_GO_MOD_CACHE_HOST):
        mounts.append(Mount(
            target=_GO_MOD_CACHE_CONTAINER,
            source=_GO_MOD_CACHE_HOST,
            type="bind",
            read_only=False,   # container must not modify the host cache
        ))
        logger.info("Mounting host Go module cache: %s → %s", _GO_MOD_CACHE_HOST, _GO_MOD_CACHE_CONTAINER)
    else:
        logger.warning("Go module cache not found at %s — go mod download will fail offline", _GO_MOD_CACHE_HOST)

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
            mounts=mounts,
            environment={
                "GONOSUMCHECK": "*",        # skip checksum DB (no network)
                "GOFLAGS": "-mod=mod",      # allow go to use the cache freely
                "GOPATH": "/root/go",       # must match the mount target parent
            },
            network_disabled=False,
            read_only=False,
            mem_limit="512m",
            nano_cpus=1_000_000_000,
            labels={"managed_by": "devops_sandbox"},
            detach=True,
        )
        container.start()
        logger.debug("Container started: %s", container.short_id)

        wait_response = container.wait(timeout=timeout)
        result.exit_code = wait_response.get("StatusCode", -1)
        result.timed_out = False

    except Exception as timeout_exc:
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
                    pass
        else:
            result.exit_code = -1
            result.error = f"Unexpected error during container execution: {timeout_exc}"
            logger.exception(result.error)

    finally:
        if container:
            try:
                raw_logs = container.logs(stdout=True, stderr=True, stream=False)
                combined = raw_logs.decode("utf-8", errors="replace") if isinstance(raw_logs, bytes) else str(raw_logs)
                try:
                    result.stdout = container.logs(stdout=True, stderr=False, stream=False).decode("utf-8", errors="replace")
                    result.stderr = container.logs(stdout=False, stderr=True, stream=False).decode("utf-8", errors="replace")
                except Exception:
                    result.stdout = combined
                    result.stderr = ""
            except Exception as log_exc:
                logger.warning("Could not capture container logs: %s", log_exc)
                result.stderr = f"[Log capture failed: {log_exc}]"

            try:
                container.remove(force=True)
                logger.debug("Container %s removed.", container.short_id)
            except APIError as rm_exc:
                logger.warning("Container removal failed (non-fatal): %s", rm_exc)

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
    Permanently delete the workspace directory and all its contents.
    Call ONLY after the 3-round fix loop is complete.
    """
    resolved = str(Path(workspace_path).resolve())

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