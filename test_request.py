import sys
from dotenv import load_dotenv

load_dotenv()

# We can directly invoke our compiled LangGraph workflow to test it
from graph.builder import app

print("\n[START] Starting Simulated PR Review Pipeline...")

import os

MOCK_DIR = "test_apps/backend_login_go"
REPO_NAME = "backend_pandhi"

current_files = {}

try:
    for root, dirs, files in os.walk(MOCK_DIR):
        for file in files:
            if file.endswith(".go"):
                filepath = os.path.join(root, file)
                # Normalize path separators for dict keys
                normalized_path = filepath.replace("\\", "/")
                with open(filepath, "r", encoding="utf-8") as f:
                    current_files[normalized_path] = f.read()
except Exception as e:
    print(f"Error reading mock directory {MOCK_DIR}: {e}")
    sys.exit(1)

# This initial state mimics what the webhook + Celery worker would pass in
initial_state = {
    "pr_url": f"https://github.com/fake/{REPO_NAME}/pull/1",
    # The production source code to be reviewed (multi-file)
    "current_files": current_files,
    "iteration_count": 0,
    "ast_is_valid": True,
    # Tells the Architect agent which vector store repo to query
    "repo_name": REPO_NAME,
    "domain_approvals": {
        "security": "pending",
        "architecture": "pending",
        "code_quality": "pending",
        "qa": "pending",
        "frontend": "pending"
    },
    "active_critiques": [],
    "full_history": []
}

print(f"[TEST] Simulating an incoming pull request for repository: {initial_state['repo_name']}\n")

# Stream the output of every agent as they work
for output in app.stream(initial_state):
    for node_name, result in output.items():
        print(f"\n[OK] {node_name} Finished Processing.")
        
print("\n[DONE] Full testing simulation complete!")