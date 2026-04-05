"""
api/models.py

Pydantic models for the GitHub webhook payload.
Extended to capture merge status, repository identity, and head SHA
required by the incremental vector store sync on PR merge.
"""

from pydantic import BaseModel


class HeadCommit(BaseModel):
    sha: str = ""


class Repository(BaseModel):
    full_name: str          # e.g. "your-org/backend_pandhi"
    name: str               # e.g. "backend_pandhi"


class PullRequest(BaseModel):
    html_url: str
    title: str
    body: str | None = None
    merged: bool = False
    head: HeadCommit = HeadCommit()
    base: HeadCommit = HeadCommit()


class WebhookPayload(BaseModel):
    action: str
    number: int
    pull_request: PullRequest
    repository: Repository = Repository(full_name="unknown/unknown", name="unknown")