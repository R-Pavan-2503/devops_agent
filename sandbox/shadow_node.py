"""
sandbox/shadow_node.py

LangGraph node wrapper for the Shadow Environment Validator.

Drop this into graph/builder.py:
    from sandbox.shadow_node import shadow_env_node
    workflow.add_node("shadow_env_node", shadow_env_node)

Routing after shadow_env_node:
    - success=True  AND dev agent was NOT called this round → END of loop → doc agent
    - success=True  AND dev agent WAS called              → loop back to specialist agents
    - success=False AND iteration_count < 3               → development_agent_node (with build critique)
    - success=False AND iteration_count >= 3              → human_fallback_node
"""

from graph.state import AgentState
from sandbox.shadow_env import run_shadow_validation


def shadow_env_node(state: AgentState) -> dict:
    """
    Runs the shadow Docker environment.

    Injects shadow build failures as a new critique so the Dev Agent
    can fix compile/test errors on the next iteration, just like any
    other specialist rejection.
    """
    print(" Shadow Env: Spinning up Docker container for validation…")

    files_dict = state.get("current_files", {})
    repo_name  = state.get("repo_name", "pr_sandbox")

    result = run_shadow_validation(files_dict, repo_name=repo_name)

    if result.success:
        print(f"  [shadow] ✅ All steps passed for {result.project_type} project.")
        return {
            "shadow_passed": True,
            # Clear any stale shadow critique so it doesn't linger in the log
            "active_critiques": [],
        }
    else:
        print(f"  [shadow] ❌ Failed: {result.error}")
        critique_entry = (
            f"[Round {state.get('iteration_count', 0)}] "
            f"Shadow: {result.critique}"
        )
        return {
            "shadow_passed": False,
            "active_critiques": [critique_entry],
            "full_history":     [critique_entry],
            # Mark ast_is_valid=False so route_negotiation sends to dev agent
            "ast_is_valid": False,
        }