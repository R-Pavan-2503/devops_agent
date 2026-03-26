import hmac
import hashlib
from fastapi import FastAPI, status, Request, HTTPException, Depends
from api.models import WebhookPayload

from worker.celery_app import process_pull_request_task

app = FastAPI(title="10-Agent DevOps Pipeline")

async def verify_github_signature(request: Request):
    # *  Verifies the HMAC signature sent by GitHub.
    # !  this shld be frm the env has of now fr testing i have added like this
    secret = b"my_super_secret_key" 
    
    github_signature = request.headers.get("x-hub-signature-256")
    if not github_signature:
        raise HTTPException(status_code=401, detail="Missing signature header")
    
    body = await request.body()
    
    mac = hmac.new(secret, msg=body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + mac.hexdigest()
    
    if not hmac.compare_digest(expected_signature, github_signature):
        raise HTTPException(status_code=401, detail="Signatures do not match")

@app.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(
    payload: WebhookPayload, 
    request: Request,
    _=Depends(verify_github_signature) 
):
    print(f"Securely received PR #{payload.number}: {payload.pull_request.title}")
    
    process_pull_request_task.delay(payload.model_dump())
    
    return {"message": "Webhook received. Processing started."}