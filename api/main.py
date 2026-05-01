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

import httpx
from fastapi import FastAPI, status, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import asyncio
from dotenv import load_dotenv

from api.models import WebhookPayload
from worker.celery_app import process_pull_request_task

load_dotenv()

app = FastAPI(title="10-Agent DevOps Pipeline")

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

@app.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(
    payload: WebhookPayload,
    request: Request,
    _=Depends(verify_github_signature)
):
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
        process_pull_request_task.delay(payload.model_dump())
        return {"message": f"Webhook received. PR #{payload.number} queued for AI review."}

    # --- Any other action (assigned, labeled, etc.) — acknowledge but skip ---
    return {"message": f"Event '{action}' acknowledged. No action taken."}


# ---------------------------------------------------------------------------
# Dashboard Endpoints
# ---------------------------------------------------------------------------

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