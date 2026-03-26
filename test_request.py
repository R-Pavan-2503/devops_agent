import hmac
import hashlib
import json
import requests

# *  The exact same secret 
SECRET = b"my_super_secret_key"

#  * A fake GitHub PR payload 
payload_dict = {
    "action": "opened",
    "number": 99,
    "pull_request": {
        "html_url": "https://github.com/fake/repo/pull/99",
        "title": "Fix memory leak in production",
        "body": "This PR fixes the issue."
    }
}

payload_bytes = json.dumps(payload_dict).encode("utf-8")

mac = hmac.new(SECRET, msg=payload_bytes, digestmod=hashlib.sha256)
signature = "sha256=" + mac.hexdigest()

# Send the request to our local FastAPI server
headers = {
    "Content-Type": "application/json",
    "x-hub-signature-256": signature
}

print("Sending secure webhook to FastAPI...")
response = requests.post("http://localhost:8000/webhook", data=payload_bytes, headers=headers)

print(f"Response Status: {response.status_code}")
print(f"Response Body: {response.json()}")