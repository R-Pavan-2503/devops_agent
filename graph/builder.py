from langgraph.graph import StateGraph, END
from graph.state import AgentState
from graph.edges import route_negotiation

from agents.nodes import (
    security_agent_node,
    backend_analyst_node,
    development_agent_node,
    documentation_summarizer_node,
    code_quality_agent_node,
    architecture_agent_node,
    qa_agent_node,
    frontend_agent_node
)

# -----------------------------
# Sandbox Node
# -----------------------------
def environment_sandbox_node(state: AgentState):
    print(" Deployment: Consensus reached! Deploying to sandbox.")
    return {}


# -----------------------------
#  NEW: Consensus Node (FAN-IN)
# -----------------------------
def consensus_node(state: AgentState):
    votes = state.get("domain_approvals", {})
    print(f" Consensus Node: All agents finished.")
    print(f" Votes: {votes}")

    if any(vote == "rejected" for vote in votes.values()):
        current_critiques = state.get("active_critiques", [])
        print(f" → {len(current_critiques)} critiques moving to long-term history. Wiping short-term.")
        return {
            "full_history": current_critiques,  # Appends to long-term memory
            "active_critiques": [],             # WIPES short-term for next round
        }
    return {}


# -----------------------------
# Initialize Graph
# -----------------------------
workflow = StateGraph(AgentState)

# -----------------------------
# Add Nodes
# -----------------------------
workflow.add_node("development_agent_node", development_agent_node)
workflow.add_node("backend_analyst_node", backend_analyst_node)

workflow.add_node("security_agent_node", security_agent_node)
workflow.add_node("code_quality_agent_node", code_quality_agent_node)
workflow.add_node("architecture_agent_node", architecture_agent_node)
workflow.add_node("qa_agent_node", qa_agent_node)
workflow.add_node("frontend_agent_node", frontend_agent_node)

workflow.add_node("consensus_node", consensus_node)

workflow.add_node("documentation_summarizer_node", documentation_summarizer_node)
workflow.add_node("environment_sandbox_node", environment_sandbox_node)

# -----------------------------
# Entry Point
# -----------------------------
workflow.set_entry_point("backend_analyst_node")

# -----------------------------
# Routing (ONLY from consensus)
# -----------------------------
workflow.add_conditional_edges("consensus_node", route_negotiation)
workflow.add_edge("development_agent_node", "backend_analyst_node")

# -----------------------------
# FAN-OUT handled by route_negotiation
# -----------------------------

# -----------------------------
# FAN-IN: All agents → consensus
# -----------------------------
workflow.add_edge("backend_analyst_node", "security_agent_node")
workflow.add_edge("security_agent_node", "code_quality_agent_node")
workflow.add_edge("code_quality_agent_node", "architecture_agent_node")
workflow.add_edge("architecture_agent_node", "qa_agent_node")
workflow.add_edge("qa_agent_node", "frontend_agent_node")
workflow.add_edge("frontend_agent_node", "consensus_node")

# -----------------------------
# Final Flow
# -----------------------------
workflow.add_edge("environment_sandbox_node", "documentation_summarizer_node")
workflow.add_edge("documentation_summarizer_node", END)

# -----------------------------
# Compile
# -----------------------------
app = workflow.compile()


# -----------------------------
# TESTING
# -----------------------------
if __name__ == "__main__":
    print("Starting the 10-Agent Pipeline Test...\n")

    initial_state = {
        "pr_url": "https://github.com/fake/repo/pull/1",
        "current_code": "def login():\n    password = 'super_secret_password'\n    return True",
        "iteration_count": 0,
        "ast_is_valid": False,
        "domain_approvals": {
            "security": "pending",
            "architecture": "pending",
            "code_quality": "pending",
            "qa": "pending",
            "frontend": "pending"
        }
    }

    for output in app.stream(initial_state):
        for key, value in output.items():
            print(f"Finished: {key}\n")