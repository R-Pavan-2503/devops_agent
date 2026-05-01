import requests
import hmac
import hashlib
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
WEBHOOK_URL = "http://localhost:8000/webhook"
SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "my_super_secret_key")

payload = {
    "action": "opened",
    "number": 42,
    "pull_request": {
        "html_url": "https://github.com/test-user/test-repo/pull/42",
        "title": "Feature: Add new dashboard component",
        "body": "This PR adds a new component to the dashboard.",
        "merged": False,
        "head": {"sha": "head_sha_abc123"},
        "base": {"sha": "base_sha_789"}
    },
    "repository": {
        "full_name": "test-user/test-repo",
        "name": "test-repo"
    }
}

# Generate GitHub-style signature
import json
body = json.dumps(payload).encode()
mac = hmac.new(SECRET.encode(), msg=body, digestmod=hashlib.sha256)
signature = "sha256=" + mac.hexdigest()

headers = {
    "Content-Type": "application/json",
    "x-hub-signature-256": signature
}

print(f"🚀 Sending simulated PR #42 webhook to {WEBHOOK_URL}...")
response = requests.post(WEBHOOK_URL, data=body, headers=headers)

if response.status_code == 202:
    print("✅ Webhook accepted! Check the worker terminal and the Dashboard.")
else:
    print(f"❌ Webhook failed: {response.status_code}")
    print(response.text)
