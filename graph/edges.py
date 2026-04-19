"""
graph/edges.py

Routing logic for the multi-agent DevOps pipeline.

Key routing decisions:
  route_after_routing_node  — decides if QA runs or is skipped
  route_negotiation         — post-consensus: dev agent, shadow env, or docs
  route_after_shadow        — post-shadow: loop back or terminate
"""

from graph.state import AgentState


# ---------------------------------------------------------------------------
# 1. Post-Router-Node: decide whether to include QA this round
# ---------------------------------------------------------------------------

def route_after_router(state: AgentState) -> str:
    """
    Called immediately after the PR-type router node.
    If the PR has no test files, we skip the QA Agent entirely (saves tokens).
    If it IS a bugfix/refactor with no UAC, Scrum Agent is already bypassed
    upstream — this function handles the QA gate only.
    """
    if state.get("pr_has_tests", False):
        return "backend_analyst_node"   # full pipeline including QA
    else:
        # Jump straight to specialist pipeline; QA node will self-skip via state flag
        return "backend_analyst_node"   # same entry; QA node checks flag internally


# ---------------------------------------------------------------------------
# 2. Post-Consensus: dev agent, shadow env, or docs
# ---------------------------------------------------------------------------

def route_negotiation(state: AgentState) -> str:
    """
    Fan-in routing from consensus_node.

    Priority order:
      1. Iteration limit hit          → human_fallback_node
      2. AST/shadow build invalid     → development_agent_node
      3. All agents approved          → shadow_env_node  (validate before final merge)
      4. Any agent rejected           → development_agent_node
      5. Fallback                     → development_agent_node
    """
    iteration = state.get("iteration_count", 0)

    # Hard stop after 3 rounds
    if iteration >= 3:
        return "human_fallback_node"

    # Syntactic / shadow build failure → fix first
    if not state.get("ast_is_valid", True):
        return "development_agent_node"

    votes = state.get("domain_approvals", {})

    if votes and all(v == "approved" for v in votes.values()):
        # All specialists agree → run shadow environment before declaring success
        return "shadow_env_node"

    if votes and any(v == "rejected" for v in votes.values()):
        return "development_agent_node"

    return "development_agent_node"


# ---------------------------------------------------------------------------
# 3. Post-Shadow Environment: loop or terminate
# ---------------------------------------------------------------------------

def route_after_shadow(state: AgentState) -> str:
    """
    Called after shadow_env_node completes.

    - Shadow PASSED:
        • Dev Agent was NOT invoked this round (iteration_count == 0 or
          no active critiques before shadow ran) → go straight to docs
        • Dev Agent WAS invoked → loop back to specialist agents for re-review
    - Shadow FAILED:
        • iteration_count < 3 → send to Dev Agent with build critique
        • iteration_count >= 3 → human fallback
    """
    shadow_passed = state.get("shadow_passed", False)
    iteration     = state.get("iteration_count", 0)

    if not shadow_passed:
        if iteration >= 3:
            return "human_fallback_node"
        # Build/test failure → Dev Agent will pick up the shadow critique
        return "development_agent_node"

    # Shadow passed — decide if we loop for re-review or go to docs
    # If iteration_count > 0, the Dev Agent touched the code; do one final review pass.
    # If iteration_count == 0, code was clean first time — go straight to docs.
    if iteration > 0:
        # Re-run specialists on the Dev-Agent-fixed code that just passed shadow
        # Reset approvals for a clean re-vote
        return "backend_analyst_node"

    # Clean first pass: no dev agent called, shadow passed → done
    return "documentation_summarizer_node"