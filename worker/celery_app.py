"""
worker/celery_app.py

Celery worker that receives GitHub PR webhook payloads and executes the
LangGraph multi-agent review pipeline in a background process.

The worker:
  1. Reconstructs initial AgentState from the raw webhook payload dict.
  2. Fetches the changed files from the GitHub API (PR diff only, not full repo).
  3. Invokes the compiled LangGraph app.
  4. Returns a structured result dict (logged by Celery; visible in Flower).
"""

import logging
import os
import shutil
import subprocess
import tempfile

import httpx
import contextlib
import sys
from celery import Celery

# Ensure project root is in path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

class TeeStream:
    def __init__(self, stream1, stream2):
        self.stream1 = stream1
        self.stream2 = stream2
        self.flush_count = 0
    def write(self, data):
        self.stream1.write(data)
        self.stream2.write(data)
        if self.flush_count % 10 == 0 or "\n" in data:
            self.stream2.flush()
            self.stream1.flush()
        self.flush_count += 1
    def flush(self):
        self.stream1.flush()
        self.stream2.flush()

    def isatty(self):
        # Fallback to the original stream's isatty status
        return getattr(self.stream1, 'isatty', lambda: False)()

@contextlib.contextmanager
def tee_stdout_stderr(filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        sys.stdout = TeeStream(original_stdout, f)
        sys.stderr = TeeStream(original_stderr, f)
        try:
            yield
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Celery application — connects to Redis broker/backend
# ---------------------------------------------------------------------------
celery_app = Celery(
    "devops_worker",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
)


def _fetch_pr_files(repo_full_name: str, pr_number: int, github_token: str) -> tuple[dict[str, str], dict[str, str]]:
    """
    Fetch only the files changed in this PR from the GitHub API.

    Returns a tuple of (current_files, diff_files). Files that are deleted or too
    large to fetch are silently skipped.

    Using PR diff (not a full repo walk) reduces token usage by 80–90% for
    large repos and prevents context-window truncation on large PRs.
    """
    headers = {"Accept": "application/vnd.github+json"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    base_url = f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}/files"
    current_files: dict[str, str] = {}
    diff_files: dict[str, str] = {}

    ALLOWED_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".cpp", ".c", ".h", ".rs", ".rb", ".php"}

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(base_url, headers=headers)
            if resp.status_code != 200:
                logger.warning(
                    "[worker] Could not fetch PR files for %s#%s: %s",
                    repo_full_name, pr_number, resp.status_code
                )
                return current_files, diff_files

            changed_files = resp.json()  # list of {filename, status, raw_url, ...}
            logger.info("[worker] %d file(s) changed in PR #%s", len(changed_files), pr_number)

            for file_info in changed_files:
                file_path = file_info.get("filename", "")
                file_status = file_info.get("status", "")

                if file_status == "removed":
                    continue  # Skip deleted files — no content to review

                ext = os.path.splitext(file_path)[1].lower()
                if ext not in ALLOWED_EXTS or "package-lock" in file_path or "yarn.lock" in file_path:
                    logger.info("[worker] Skipping non-code file for AI: %s", file_path)
                    continue

                diff_files[file_path] = file_info.get("patch", "No patch available")

                raw_url = file_info.get("raw_url", "")
                if not raw_url:
                    # Skip if we can't find a way to download the file
                    continue
                
                try:
                    # follow_redirects=True is the key to fixing the 302 errors
                    raw_resp = client.get(raw_url, headers=headers, follow_redirects=True)
                    if raw_resp.status_code == 200:
                        current_files[file_path] = raw_resp.text
                        print(f"📄 [worker] Fetched: {file_path}")
                    else:
                        logger.warning("[worker] Could not fetch %s (status %s)", file_path, raw_resp.status_code)
                except Exception as fetch_err:
                    logger.warning("[worker] Failed to fetch content of %s: %s", file_path, fetch_err)

    except Exception as e:
        logger.error("[worker] GitHub API call failed: %s", e)

    return current_files, diff_files


def _clone_repo_for_pr(repo_full_name: str, head_sha: str, github_token: str) -> str:
    """Clones the full repo into a temp directory and checks out the PR head SHA."""
    temp_dir = tempfile.mkdtemp(prefix="devops_sandbox_")
    url = f"https://oauth2:{github_token}@github.com/{repo_full_name}.git" if github_token else f"https://github.com/{repo_full_name}.git"
    
    try:
        logger.info("[worker] Cloning full repo %s to %s", repo_full_name, temp_dir)
        subprocess.run(["git", "clone", url, temp_dir], check=True, capture_output=True)
        subprocess.run(["git", "checkout", head_sha], cwd=temp_dir, check=True, capture_output=True)
        return temp_dir
    except subprocess.CalledProcessError as e:
        logger.error("[worker] git clone/checkout failed: %s\n%s", e, e.stderr.decode('utf-8', errors='replace'))
        shutil.rmtree(temp_dir, ignore_errors=True)
        return ""

@celery_app.task(bind=True, max_retries=2, default_retry_delay=10)
def process_pull_request_task(self, payload_dict: dict):
    pr_number     = payload_dict.get("number", 0)
    
    log_file = os.path.join(os.path.dirname(__file__), "..", "logs", f"pr_{pr_number}.log")
    with tee_stdout_stderr(log_file):
        repo_info     = payload_dict.get("repository", {})
        repo_full_name = repo_info.get("full_name", "")
        
        print(f"\n🚀 [worker] [PR #{pr_number}] Task received! Initializing pipeline...")
        
        # --- Late import ---
        from graph.builder import app as pipeline_app
        print(f"📦 [worker] [PR #{pr_number}] Pipeline graph loaded successfully.")

        repo_name     = repo_info.get("name", "")
        pr_info       = payload_dict.get("pull_request", {})
        pr_title      = pr_info.get("title", "")
        pr_body       = pr_info.get("body", "") or ""
        pr_url        = pr_info.get("html_url", "")
        head_info     = pr_info.get("head", {})
        head_sha      = head_info.get("sha", "")
        uac_context   = "" 

        print(f"🔍 [worker] [PR #{pr_number}] Fetching PR diff from GitHub...")
        github_token = os.getenv("GITHUB_TOKEN", "")
        current_files, diff_files = _fetch_pr_files(repo_full_name, pr_number, github_token)

        if not current_files and not diff_files:
            logger.warning("[worker] No files fetched for PR #%s — pipeline aborted.", pr_number)
            return {
                "pr_number": pr_number,
                "status": "aborted",
                "reason": "No reviewable files found in PR diff",
            }

        # Clone the full repo so the Sandbox has all context
        print(f"📥 [worker] [PR #{pr_number}] Cloning full repository for sandbox context...")
        cloned_workspace = _clone_repo_for_pr(repo_full_name, head_sha, github_token)
        print(f"✅ [worker] [PR #{pr_number}] Workspace ready at {cloned_workspace}")

        initial_state = {
            "pr_url":           pr_url,
            "pr_title":         pr_title,
            "pr_body":          pr_body,
            "current_files":    current_files,
            "diff_files":       diff_files,
            "iteration_count":  0,
            "ast_is_valid":     True,
            "shadow_passed":    False,
            "repo_name":        repo_name,
            "commit_sha":       head_sha,
            "uac_context":      uac_context,
            "sandbox_workspace_path": cloned_workspace,
            "domain_approvals": {
                "security": "pending",
                "architecture": "pending",
                "code_quality": "pending",
                "qa": "pending",
                "frontend": "pending",
                "backend": "pending",
            },
            "active_critiques": [],
            "full_history":     [],
        }

        try:
            final_state = None
            for output in pipeline_app.stream(initial_state):
                for node_name in output:
                    logger.info("[worker] [OK] %s finished (PR #%s)", node_name, pr_number)
                    final_state = output[node_name]

            result = {
                "pr_number":   pr_number,
                "repo_name":   repo_name,
                "status":      "completed",
                "iterations":  (final_state or {}).get("iteration_count", 0),
                "human_review_required": (final_state or {}).get("requires_human_review", False),
            }
            logger.info("[worker] Pipeline complete for PR #%s: %s", pr_number, result)
            return result

        except Exception as exc:
            logger.exception("[worker] Pipeline failed for PR #%s: %s", pr_number, exc)
            try:
                raise self.retry(exc=exc)
            except self.MaxRetriesExceededError:
                return {
                    "pr_number": pr_number,
                    "status": "error",
                    "error": str(exc),
                }