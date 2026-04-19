"""
test_request.py — Simulated PR review pipeline test.
Updated to include new state fields required by the PR Router node.
"""

import sys
import os
from dotenv import load_dotenv

load_dotenv()

from graph.builder import app

print("\n[START] Starting Simulated PR Review Pipeline...")

MOCK_DIR  = "test_apps/backend_login_go"
REPO_NAME = "backend_pandhi"

current_files = {}
try:
    for root, dirs, files in os.walk(MOCK_DIR):
        for file in files:
            if file.endswith(".go"):
                filepath = os.path.join(root, file)
                normalized_path = filepath.replace("\\", "/")
                with open(filepath, "r", encoding="utf-8") as f:
                    current_files[normalized_path] = f.read()
except Exception as e:
    print(f"Error reading mock directory {MOCK_DIR}: {e}")
    sys.exit(1)

initial_state = {
    "pr_url":   f"https://github.com/fake/{REPO_NAME}/pull/1",
    "pr_title": "",   # In production, sourced from WebhookPayload.pull_request.title
    "pr_body":  "",   # In production, sourced from WebhookPayload.pull_request.body
    "uac_context": "",  # Inject from Jira/ADO ticket when available

    # Code under review
    "current_files": current_files,
    "repo_name":     REPO_NAME,

    # Iteration control
    "iteration_count": 0,
    "ast_is_valid":    True,

    # Shadow env (router node resets this; set False here as a safe default)
    "shadow_passed": False,

    # Dynamic flags (router node will overwrite these with real values)
    "pr_type":                  "unknown",
    "pr_has_tests":             True,   # default True = run QA (safe default)
    "is_bugfix_or_refactor":    False,
    "needs_api_contract_check": True,

    # Specialist votes
    "domain_approvals": {
        "security":     "pending",
        "architecture": "pending",
        "code_quality": "pending",
        "qa":           "pending",
        "frontend":     "pending",
    },

    # Critique logs
    "active_critiques": [],
    "full_history":     [],
}

print(f"[TEST] Simulating PR review for repository: {REPO_NAME}\n")

for output in app.stream(initial_state):
    for node_name, result in output.items():
        print(f"\n[OK] {node_name} Finished Processing.")

print("\n[DONE] Full testing simulation complete!")