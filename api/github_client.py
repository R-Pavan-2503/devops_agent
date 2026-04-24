"""
api/github_client.py

GitHub API helper for the DevOps pipeline.

Responsibilities:
  - post_pr_comment()  — Add a PR review comment via the GitHub Issues Comments API.
  - create_check_run() — Create/update a GitHub Check Run to surface pass/fail status
                         directly on the PR's Checks tab.

Environment variables required:
  GITHUB_TOKEN — Personal Access Token (or GitHub App token) with repo scope.

Usage from documentation_summarizer_node:
    from api.github_client import post_pr_comment, create_check_run

    post_pr_comment(repo_full_name, pr_number, report_md)
    create_check_run(
        repo=repo_full_name,
        sha=commit_sha,
        name="AI Review",
        conclusion="success" if approved else "failure",
        output={"title": "AI Review Complete", "summary": report_md[:65535]},
    )
"""

import logging
import os
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

_GITHUB_API_BASE = "https://api.github.com"
_GITHUB_ACCEPT   = "application/vnd.github+json"


def _auth_headers() -> dict[str, str]:
    """Build standard GitHub API auth headers from the environment token."""
    token = os.getenv("GITHUB_TOKEN", "")
    headers = {"Accept": _GITHUB_ACCEPT, "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ---------------------------------------------------------------------------
# Post PR comment
# ---------------------------------------------------------------------------

def post_pr_comment(repo_full_name: str, pr_number: int, body: str) -> bool:
    """
    Post a markdown comment on a pull request.

    Args:
        repo_full_name : e.g. "your-org/backend_pandhi"
        pr_number      : The PR number (integer).
        body           : Markdown text for the comment body (max 65535 chars).

    Returns:
        True on success, False if the API call fails (non-fatal; logged).
    """
    url = f"{_GITHUB_API_BASE}/repos/{repo_full_name}/issues/{pr_number}/comments"
    payload = {"body": body[:65535]}

    try:
        resp = httpx.post(url, json=payload, headers=_auth_headers(), timeout=15.0)
        if resp.status_code == 201:
            comment_url = resp.json().get("html_url", "")
            logger.info("[github_client] PR comment posted: %s", comment_url)
            return True
        else:
            logger.warning(
                "[github_client] post_pr_comment failed: %s — %s",
                resp.status_code, resp.text[:300]
            )
            return False
    except Exception as exc:
        logger.error("[github_client] post_pr_comment exception: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Create / update a GitHub Check Run
# ---------------------------------------------------------------------------

CheckConclusion = Literal["success", "failure", "neutral", "cancelled", "timed_out", "action_required"]


def create_check_run(
    repo: str,
    sha: str,
    name: str,
    conclusion: CheckConclusion,
    output: dict | None = None,
) -> bool:
    """
    Create a GitHub Check Run on a specific commit SHA.

    The check run surfaces directly on the PR's "Checks" tab and can
    block merges if branch protection rules require it.

    Args:
        repo       : Full repo name, e.g. "your-org/backend_pandhi".
        sha        : The head commit SHA of the PR.
        name       : Display name for the check (e.g. "AI Review").
        conclusion : One of the GitHub-accepted conclusion values.
        output     : Optional dict with keys "title" and "summary" (markdown).
                     summary is capped at 65535 chars by the GitHub API.

    Returns:
        True on success, False on failure (non-fatal; logged).
    """
    url = f"{_GITHUB_API_BASE}/repos/{repo}/check-runs"

    payload: dict = {
        "name":        name,
        "head_sha":    sha,
        "status":      "completed",
        "conclusion":  conclusion,
    }

    if output:
        payload["output"] = {
            "title":   output.get("title", name),
            "summary": output.get("summary", "")[:65535],
        }

    try:
        resp = httpx.post(url, json=payload, headers=_auth_headers(), timeout=15.0)
        if resp.status_code in (200, 201):
            check_url = resp.json().get("html_url", "")
            logger.info("[github_client] Check run created: %s (conclusion=%s)", check_url, conclusion)
            return True
        else:
            logger.warning(
                "[github_client] create_check_run failed: %s — %s",
                resp.status_code, resp.text[:300]
            )
            return False
    except Exception as exc:
        logger.error("[github_client] create_check_run exception: %s", exc)
        return False
