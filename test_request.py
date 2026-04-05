import sys
from dotenv import load_dotenv
import asyncio

load_dotenv()

# We can directly invoke our compiled LangGraph workflow to test it
from graph.builder import app

print("\n[START] Starting Simulated PR Review Pipeline...")

# This initial state mimics what the webhook + Celery worker would pass in
initial_state = {
    "pr_url": "https://github.com/fake/repo/pull/1",
    # Here we simulate an incoming piece of code
    "current_code": "def connect_to_database():\n    password = 'admin'\n    db.connect('root', password)",
    "iteration_count": 0,
    "ast_is_valid": True,
    # 🔑 This is the key piece! We tell the agents which vector store repo to query:
    "repo_name": "backend_pandhi",
    "domain_approvals": {
        "security": "pending",
        "architecture": "pending",
        "code_quality": "pending",
        "qa": "pending"
    }
}

print(f"[TEST] Simulating an incoming pull request for repository: {initial_state['repo_name']}\n")

# Stream the output of every agent as they work
for output in app.stream(initial_state):
    for node_name, result in output.items():
        print(f"\n[OK] {node_name} Finished Processing.")
        
print("\n[DONE] Full testing simulation complete!")