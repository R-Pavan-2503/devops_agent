"""verify_fixes.py — quick sanity check for all applied fixes."""
import typing, sys

errors = []
passes = []

# 1. pr_title / pr_body in AgentState
try:
    from graph.state import AgentState
    hints = typing.get_type_hints(AgentState)
    assert "pr_title" in hints and "pr_body" in hints
    passes.append("pr_title / pr_body fields present in AgentState")
except Exception as e:
    errors.append(f"AgentState fields: {e}")

# 2. consensus_node always persists critiques
try:
    import inspect
    from graph.builder import consensus_node
    src = inspect.getsource(consensus_node)
    assert "full_history" in src
    assert "if any(" not in src  # old conditional-only branch gone
    passes.append("consensus_node always writes to full_history")
except Exception as e:
    errors.append(f"consensus_node: {e}")

# 3. route_after_router dead code removed
try:
    import importlib
    mod = importlib.import_module("graph.edges")
    assert not hasattr(mod, "route_after_router"), "dead function still present"
    passes.append("route_after_router dead code removed")
except Exception as e:
    errors.append(f"edges.py dead code: {e}")

# 4. hardcoded secret removed from api.main
try:
    import inspect
    import api.main as main_mod
    src = inspect.getsource(main_mod.verify_github_signature)
    assert "my_super_secret_key" not in src
    assert "GITHUB_WEBHOOK_SECRET" in src
    passes.append("hardcoded webhook secret removed")
except Exception as e:
    errors.append(f"api.main secret: {e}")

# 5. Celery worker is real (not a stub)
try:
    import inspect
    from worker.celery_app import process_pull_request_task
    src = inspect.getsource(process_pull_request_task)
    assert "pipeline_app" in src or "graph.builder" in src
    assert "AI Processing Complete" not in src  # stub string gone
    passes.append("Celery worker wired to real pipeline")
except Exception as e:
    errors.append(f"celery_app: {e}")

# 6. github_client module exists and exposes correct API
try:
    from api.github_client import post_pr_comment, create_check_run
    passes.append("api.github_client exports post_pr_comment and create_check_run")
except Exception as e:
    errors.append(f"github_client: {e}")

# 7. agents.nodes imports clean (no circular import, correct prompt module)
try:
    import agents.nodes
    passes.append("agents.nodes imports cleanly (no circular import)")
except Exception as e:
    errors.append(f"agents.nodes: {e}")

# --- Report ---
print("\n" + "=" * 55)
print("  VERIFICATION REPORT")
print("=" * 55)
for p in passes:
    print(f"  [PASS]  {p}")
for err in errors:
    print(f"  [FAIL]  {err}")
print("=" * 55)
print(f"  {len(passes)} passed  |  {len(errors)} failed")
print("=" * 55 + "\n")

sys.exit(1 if errors else 0)
