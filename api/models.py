from pydantic import BaseModel

class PullRequest(BaseModel):
    html_url: str
    title: str
    body: str | None = None  

class WebhookPayload(BaseModel):
    action: str
    number: int
    pull_request: PullRequest