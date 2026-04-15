from graph.state import AgentState

def route_negotiation(state: AgentState):

    # ── Iteration Limit (Fix #3) ──────────────────────────────────────────────
    # When 3 rounds pass without consensus, stamp the state as requiring human
    # review before routing to the Documentation Agent for the failure report.
    if state.get("iteration_count", 0) >= 3:
        return "human_fallback_node"

    # Syntactic Failure
    if not state["ast_is_valid"]:
        return "development_agent_node"

    # Consensus Reached
    if state.get("domain_approvals") and all(vote == "approved" for vote in state["domain_approvals"].values()):
        return "environment_sandbox_node"

    if state.get("domain_approvals") and any(vote == "rejected" for vote in state["domain_approvals"].values()):
        return "development_agent_node"

    # Fallback to development if approvals are somehow missing/invalid
    return "development_agent_node"