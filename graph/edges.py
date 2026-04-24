"""
graph/edges.py

Routing logic for the multi-agent DevOps pipeline.

Key routing decisions:
  route_negotiation  — post-consensus: dev agent, shadow env, or docs
  route_after_shadow — post-shadow: loop back to specialists or terminate
"""

from graph.state import AgentState




# ---------------------------------------------------------------------------
# 2. Post-Consensus: dev agent, shadow env, or docs
# ---------------------------------------------------------------------------

def route_negotiation(state: AgentState) -> str:
    """
    Fan-in routing from consensus_node.

    Priority order:
      1. Syntactic / shadow build failure → critique_resolve_agent_node
      2. All agents approved              → shadow_env_node  (validate before final merge)
      3. Iteration limit hit              → human_fallback_node
      4. Any agent rejected               → critique_resolve_agent_node
      5. Fallback                         → critique_resolve_agent_node
    """
    iteration = state.get("iteration_count", 0)

    # Syntactic / shadow build failure → fix first
    if not state.get("ast_is_valid", True):
        if iteration >= 3:
            return "human_fallback_node"
        return "critique_resolve_agent_node"

    votes = state.get("domain_approvals", {})

    if votes and all(v == "approved" for v in votes.values()):
        # All specialists agree → run shadow environment before declaring success
        return "shadow_env_node"
        
    # Hard stop after 3 rounds. Placed AFTER approvals check so that if
    # the 3rd iteration fixes everything, it goes to shadow_env.
    if iteration >= 3:
        return "human_fallback_node"

    if state.get("domain_approvals") and any(vote == "rejected" for vote in state["domain_approvals"].values()):
        return "critique_resolve_agent_node"

    # Fallback to CRA if approvals are somehow missing/invalid
    return "critique_resolve_agent_node"


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
        • iteration_count < 3 → send to Critique Resolve Agent with build critique
        • iteration_count >= 3 → human fallback
    """
    shadow_passed = state.get("shadow_passed", False)
    iteration     = state.get("iteration_count", 0)

    if not shadow_passed:
        if iteration >= 3:
            return "human_fallback_node"
        # Build/test failure → CRA will pick up the shadow critique
        return "critique_resolve_agent_node"

    # Shadow passed — decide if we loop for re-review or go to docs
    # If iteration_count > 0, the Dev Agent touched the code; do one final review pass.
    # If iteration_count == 0, code was clean first time — go straight to docs.
    if iteration > 0:
        # Re-run specialists on the Dev-Agent-fixed code that just passed shadow
        # Reset approvals for a clean re-vote
        return "backend_analyst_node"

    # Clean first pass: no dev agent called, shadow passed → done
    return "documentation_summarizer_node"