"""
api/main.py

FastAPI webhook endpoint for GitHub PR events.

Responsibilities:
1. Verify the GitHub HMAC-SHA256 signature on every request.
2. On PR *open/synchronize*: dispatch the LangGraph AI review pipeline via Celery.
3. On PR *merged*: perform incremental vector store sync —
      a. Fetch the list of files changed in the PR from GitHub API.
      b. Delete stale vectors for each changed file.
      c. Fetch new file contents and re-ingest into ChromaDB.

Environment variables (in .env):
    GITHUB_WEBHOOK_SECRET  — used to verify the GitHub signature
    GITHUB_TOKEN           — Personal Access Token for GitHub API calls
"""

import hmac
import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, status, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import asyncio
from dotenv import load_dotenv

from api.models import WebhookPayload
from core.feedback_store import get_latest_verdict_id, save_correction
from api.github_client import create_commit_status, post_pr_comment
from config import KNOWLEDGE_MAP_PROJECTS_FOLDER, OBSIDIAN_VAULT_ROOT
from agents.runtime_config import (
    apply_session_settings,
    build_model_catalog,
    get_defaults,
    get_agent_verdict_policy,
    get_live_rate_limits,
    get_session_settings,
    get_usage_summary,
    reset_session,
)
from core.llm_router import get_circuit_status
from worker.celery_app import celery_app as worker_celery_app, process_pull_request_task

load_dotenv()

app = FastAPI(title="10-Agent DevOps Pipeline")
_FORCE_REVIEW_PRS: set[int] = set()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_github_headers() -> dict:
    token = os.getenv("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ---------------------------------------------------------------------------
# Security: Verify GitHub Webhook Signature
# ---------------------------------------------------------------------------

async def verify_github_signature(request: Request):
    """Verifies the HMAC-SHA256 signature sent by GitHub."""
    secret_str = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret_str:
        raise RuntimeError(
            "GITHUB_WEBHOOK_SECRET environment variable is required but not set. "
            "Add it to your .env file or deployment environment."
        )
    secret = secret_str.encode()

    github_signature = request.headers.get("x-hub-signature-256")
    if not github_signature:
        raise HTTPException(status_code=401, detail="Missing signature header")

    body = await request.body()

    mac = hmac.new(secret, msg=body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + mac.hexdigest()

    if not hmac.compare_digest(expected_signature, github_signature):
        raise HTTPException(status_code=401, detail="Signatures do not match")


# ---------------------------------------------------------------------------
# Incremental Vector Store Sync (called on PR merge)
# ---------------------------------------------------------------------------

async def _sync_vector_store_on_merge(payload: WebhookPayload) -> None:
    """
    When a PR is merged:
      1. Fetch the list of modified files from GitHub Files API.
      2. Delete stale vectors for each modified file.
      3. Fetch new file contents from GitHub raw API.
      4. Re-ingest fresh vectors into ChromaDB.

    This keeps the vector store in sync with the main branch.
    """
    # Late imports to avoid loading ChromaDB/sentence-transformers at startup
    # (they take a few seconds for the model download on first run)
    from context_engine.chunking_engine import chunk_file
    from context_engine.vector_store import add_chunks, delete_by_file
    import tempfile
    import os as _os

    repo_full_name = payload.repository.full_name   # e.g. "your-org/backend_pandhi"
    repo_name      = payload.repository.name         # e.g. "backend_pandhi"
    pr_number      = payload.number
    head_sha       = payload.pull_request.head.sha

    print(f"[webhook] Incremental sync triggered for PR #{pr_number} in '{repo_full_name}'")

    github_api_base = f"https://api.github.com/repos/{repo_full_name}"
    headers = _get_github_headers()

    async with httpx.AsyncClient(timeout=30.0) as client:
        # ------------------------------------------------------------------ #
        # Step 1: Get the list of files changed in this PR
        # ------------------------------------------------------------------ #
        files_url = f"{github_api_base}/pulls/{pr_number}/files"
        resp = await client.get(files_url, headers=headers)

        if resp.status_code != 200:
            print(f"[webhook] Could not fetch PR files: {resp.status_code} — {resp.text[:200]}")
            return

        changed_files = resp.json()   # list of {filename, status, raw_url, ...}

        print(f"[webhook] {len(changed_files)} file(s) changed in PR #{pr_number}")

        for file_info in changed_files:
            file_path  = file_info.get("filename", "")
            file_status = file_info.get("status", "")   # added | modified | removed | renamed

            # ---------------------------------------------------------------- #
            # Step 2: Delete stale vectors for this file
            # ---------------------------------------------------------------- #
            deleted = delete_by_file(file_path=file_path, repo_name=repo_name)
            print(f"[webhook]   Deleted {deleted} stale vectors for '{file_path}'")

            # If the file was removed, nothing more to do
            if file_status == "removed":
                continue

            # ---------------------------------------------------------------- #
            # Step 3: Fetch new content from GitHub raw API
            # ---------------------------------------------------------------- #
            raw_url = file_info.get("raw_url", "")
            if not raw_url:
                # Fallback: construct raw URL from head SHA
                raw_url = f"https://raw.githubusercontent.com/{repo_full_name}/{head_sha}/{file_path}"

            raw_resp = await client.get(raw_url, headers=headers)
            if raw_resp.status_code != 200:
                print(f"[webhook]   Could not fetch raw content for '{file_path}': {raw_resp.status_code}")
                continue

            # ---------------------------------------------------------------- #
            # Step 4: Write to a temp file, chunk it, re-ingest
            # ---------------------------------------------------------------- #
            suffix = "." + file_path.rsplit(".", 1)[-1] if "." in file_path else ""
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode="wb") as tmp:
                tmp.write(raw_resp.content)
                tmp_path = tmp.name

            try:
                chunks = chunk_file(file_path=tmp_path, repo_name=repo_name)
                # Restore original file_path in metadata (not the temp path)
                for chunk in chunks:
                    chunk["metadata"]["file_path"] = file_path
                count = add_chunks(chunks)
                print(f"[webhook]   Re-ingested {count} chunks for '{file_path}'")
            finally:
                _os.unlink(tmp_path)   # clean up temp file

    print(f"[webhook] Incremental sync complete for PR #{pr_number}.")


# ---------------------------------------------------------------------------
# Webhook Endpoint
# ---------------------------------------------------------------------------

def _parse_pr_url(pr_url: str) -> tuple[str, int]:
    match = re.search(r"https://github\.com/([^/]+/[^/]+)/pull/(\d+)", pr_url or "")
    if not match:
        return "", 0
    return match.group(1), int(match.group(2))


def _fetch_pr_head_sha(repo_full_name: str, pr_number: int) -> str:
    if not repo_full_name or pr_number <= 0:
        return ""
    try:
        url = f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}"
        resp = httpx.get(url, headers=_get_github_headers(), timeout=10.0)
        if resp.status_code != 200:
            return ""
        payload = resp.json()
        return str((payload.get("head") or {}).get("sha") or "")
    except Exception:
        return ""


def _handle_cosentinel_comment(payload: dict) -> dict:
    comment = ((payload.get("comment") or {}).get("body") or "").strip()
    pr = payload.get("pull_request") or {}
    pr_url = pr.get("html_url", "")
    repo = ((payload.get("repository") or {}).get("full_name") or "")
    owner = ((payload.get("comment") or {}).get("user") or {}).get("login", "")
    pr_number = int(payload.get("number") or 0)

    if "/cosentinel force-review" in comment:
        if pr_number > 0:
            _FORCE_REVIEW_PRS.add(pr_number)
        return {"message": f"Force-review override recorded for PR #{pr_number}.", "repo": repo, "pr_url": pr_url}

    if comment.lower().startswith("/cosentinel override reason:"):
        reason = comment.split(":", 1)[1].strip() if ":" in comment else ""
        verdict_id = get_latest_verdict_id(pr_number=pr_number, repo=repo)
        if verdict_id is None:
            return {"message": "No verdict found yet for this PR; correction not saved.", "repo": repo, "pr_url": pr_url}
        save_correction(verdict_id=verdict_id, corrected_by=owner, correction="false_positive", note=reason)
        head_sha = _fetch_pr_head_sha(repo, pr_number)
        if head_sha:
            create_commit_status(
                repo=repo,
                sha=head_sha,
                state="success",
                description=f"Override by @{owner}: {reason}"[:140],
                context="CodeSentinel / AI Review"
            )
        post_pr_comment(repo, pr_number, f"CodeSentinel override accepted by @{owner}. Reason: {reason}")
        return {"message": f"Override correction logged on verdict {verdict_id} and PR status overridden.", "repo": repo, "pr_url": pr_url}

    if comment.lower().startswith("/cosentinel learn:"):
        pattern_text = comment.split(":", 1)[1].strip() if ":" in comment else ""
        repo_name = (payload.get("repository") or {}).get("name", "unknown")
        repo_dir = OBSIDIAN_VAULT_ROOT / KNOWLEDGE_MAP_PROJECTS_FOLDER / repo_name / "patterns"
        repo_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"learned_pattern_{stamp}.md"
        target = repo_dir / filename
        target.write_text(f"# Learned Pattern\n\n{pattern_text}\n", encoding="utf-8")
        return {"message": f"Learned pattern saved to {target}", "repo": repo, "pr_url": pr_url}

    return {"message": "No cosentinel command found in comment."}


def _active_pipeline_count() -> int:
    try:
        inspector = worker_celery_app.control.inspect()
        active = inspector.active() or {}
        queued = inspector.reserved() or {}
        return sum(len(v or []) for v in active.values()) + sum(len(v or []) for v in queued.values())
    except Exception:
        return 0


@app.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(
    request: Request,
    _=Depends(verify_github_signature),
):
    payload_dict = await request.json()
    event_name = request.headers.get("x-github-event", "")
    action = payload_dict.get("action", "")

    if event_name in {"issue_comment", "pull_request_review_comment"}:
        return _handle_cosentinel_comment(payload_dict)

    payload = WebhookPayload.model_validate(payload_dict)
    """
    Main webhook handler.

    - PR opened / synchronized  →  dispatch AI review via Celery
    - PR closed + merged        →  incremental vector store sync, then dispatch
    """
    pr     = payload.pull_request
    action = payload.action

    print(f"[webhook] Received event: action='{action}' PR #{payload.number}: '{pr.title}'")

    # --- Merged PR: sync vector store first ---
    if action == "closed" and pr.merged:
        print(f"[webhook] PR #{payload.number} was MERGED — starting incremental vector store sync.")
        await _sync_vector_store_on_merge(payload)

    # --- Dispatch AI review for new/updated/merged PRs ---
    if action in ("opened", "synchronize", "reopened") or (action == "closed" and pr.merged):
        max_concurrent = int(os.getenv("MAX_CONCURRENT_PIPELINES", "3"))
        active = _active_pipeline_count()
        outgoing = payload.model_dump()
        outgoing["runtime_settings"] = get_session_settings()
        forced = payload.number in _FORCE_REVIEW_PRS
        outgoing["force_full_review"] = forced
        outgoing["merged_event"] = bool(action == "closed" and pr.merged)
        if forced:
            _FORCE_REVIEW_PRS.discard(payload.number)
        process_pull_request_task.delay(outgoing)
        if active >= max_concurrent:
            return {"message": f"CodeSentinel: Review queued ({active} active). You are in line."}
        return {"message": f"Webhook received. PR #{payload.number} queued for AI review."}

    # --- Any other action (assigned, labeled, etc.) — acknowledge but skip ---
    return {"message": f"Event '{action}' acknowledged. No action taken."}


# ---------------------------------------------------------------------------
# Dashboard Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/settings")
async def get_settings():
    """Return default + current session settings and model availability info."""
    return {
        "defaults": get_defaults(),
        "current": get_session_settings(),
        **build_model_catalog(),
    }


@app.post("/api/settings/save")
async def save_settings(payload: dict):
    """
    Save session-only settings in memory.
    Expected shape: { "agents": { ... } }
    """
    agents_payload = payload.get("agents", {}) if isinstance(payload, dict) else {}
    updated = apply_session_settings(agents_payload)
    return {"message": "Settings saved for this session", "current": updated}


@app.post("/api/settings/reset")
async def reset_settings():
    """Reset session-only settings + usage counters to defaults."""
    reset_session()
    return {"message": "Session settings reset"}


@app.get("/api/settings/usage")
async def get_settings_usage():
    """Return per-model and total token/credit usage for this server session."""
    return get_usage_summary()


@app.get("/api/settings/rate-limits")
async def get_rate_limits():
    """Return current Groq key rate-limit window usage from x-ratelimit-* headers."""
    return get_live_rate_limits()


@app.get("/api/settings/provider-status")
async def get_provider_status():
    """Return provider circuit breaker status and verdict weighting policy."""
    return {
        "circuit_status": get_circuit_status(),
        "verdict_policy": get_agent_verdict_policy(),
    }


@app.get("/api/prs")
async def list_prs():
    """List available PR logs from the logs directory."""
    logs_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
    if not os.path.exists(logs_dir):
        return {"prs": []}
    
    prs = []
    for file in os.listdir(logs_dir):
        if file.startswith("pr_") and file.endswith(".log"):
            pr_num = file[3:-4]
            prs.append(pr_num)
    # Sort descending by PR number if possible
    return {"prs": sorted(prs, key=lambda x: int(x) if x.isdigit() else 0, reverse=True)}

@app.get("/api/prs/{pr_id}/logs")
async def get_pr_logs(pr_id: str):
    """Get the full historical log for a PR."""
    log_path = os.path.join(os.path.dirname(__file__), "..", "logs", f"pr_{pr_id}.log")
    if not os.path.exists(log_path):
        raise HTTPException(status_code=404, detail="Logs not found for this PR.")
    
    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"logs": content}

async def log_generator(log_path: str):
    """Yields log lines as SSE. If EOF, wait for new content."""
    with open(log_path, "r", encoding="utf-8") as f:
        while True:
            line = f.readline()
            if not line:
                await asyncio.sleep(0.5)
                continue
            # Format as Server-Sent Event
            yield f"data: {line}\n\n"

@app.get("/api/prs/{pr_id}/logs/stream")
async def stream_pr_logs(pr_id: str):
    """Stream logs for a PR using Server-Sent Events."""
    log_path = os.path.join(os.path.dirname(__file__), "..", "logs", f"pr_{pr_id}.log")
    
    # If the file doesn't exist yet, we create an empty one so it can be tail-ed
    if not os.path.exists(log_path):
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"Waiting for PR #{pr_id} logs to start...\n")

    return StreamingResponse(log_generator(log_path), media_type="text/event-stream")
