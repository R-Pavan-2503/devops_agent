import sys
from dotenv import load_dotenv

load_dotenv()

# We can directly invoke our compiled LangGraph workflow to test it
from graph.builder import app

print("\n[START] Starting Simulated PR Review Pipeline...")

TEST_FILE_PATH      = "test_files/login.go"
TEST_FILE_TEST_PATH = "test_files/login_test.go"   # Companion unit test file
REPO_NAME           = "frontend_pandhi"

try:
    with open(TEST_FILE_PATH, "r", encoding="utf-8") as f:
        code_content = f.read()
except Exception as e:
    print(f"Error reading {TEST_FILE_PATH}: {e}")
    sys.exit(1)

# This initial state mimics what the webhook + Celery worker would pass in
initial_state = {
    "pr_url": f"https://github.com/fake/{REPO_NAME}/pull/1",
    # The production source code to be reviewed
    "current_code": code_content,
    # Path to companion unit tests — QA agent uses this to estimate coverage
    "test_file_path": TEST_FILE_TEST_PATH,
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