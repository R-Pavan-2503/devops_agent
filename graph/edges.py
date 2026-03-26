from graph.state import AgentState

def route_negotiation(state: AgentState):
    
    # Summarization Timeout
    if state["iteration_count"] >= 3:
        return "documentation_summarizer_node"
        
    # Syntactic Failure
    if not state["ast_is_valid"]:
        return "backend_dev_node"
    
    # Consensus Reached
    if state.get("domain_approvals") and all(vote == "approved" for vote in state["domain_approvals"].values()):
        return "environment_sandbox_node"
    
    if state.get("domain_approvals") and any(vote == "rejected" for vote in state["domain_approvals"].values()):
        return "backend_dev_node"
    
    # Send to the parallel specialists
    return "security_agent_node"