from langgraph.graph import StateGraph, END
from graph.state import AgentState
from graph.edges import route_negotiation
from agents.nodes import security_agent_node


#  Define Dummy Nodes 
def backend_dev_node(state: AgentState):
    print("Backend Dev: Writing/Fixing code...")
    # Increase iteration count
    current_count = state.get("iteration_count", 0)
    return {
        "iteration_count": current_count + 1,
        "ast_is_valid": True
    }


def documentation_summarizer_node(state: AgentState):
    print("Doc Agent: Summarizing the long argument to save memory...")
    return {}


def environment_sandbox_node(state: AgentState):
    print("Deployment: Consensus reached! Deploying to sandbox.")
    return {}


#  Initialize the Graph 
workflow = StateGraph(AgentState)

#  Add Nodes
workflow.add_node("backend_dev_node", backend_dev_node)

workflow.add_node("security_agent_node", security_agent_node)

workflow.add_node("documentation_summarizer_node", documentation_summarizer_node)
workflow.add_node("environment_sandbox_node", environment_sandbox_node)

#  Entry Point
workflow.set_entry_point("backend_dev_node")

#  Routing Logic
workflow.add_conditional_edges("backend_dev_node", route_negotiation)

workflow.add_conditional_edges("security_agent_node", route_negotiation)

#  Final Edges
workflow.add_edge("documentation_summarizer_node", END)
workflow.add_edge("environment_sandbox_node", END)

#  Compile Graph
app = workflow.compile()


# --- TESTING BLOCK ---
if __name__ == "__main__":
    print("Starting the 10-Agent Pipeline Test...\n")

    initial_state = {
        "pr_url": "https://github.com/fake/repo/pull/1",
        "iteration_count": 0,
        "ast_is_valid": False,  # triggers first guardrail
        "domain_approvals": {}
    }

    for output in app.stream(initial_state):
        for key, value in output.items():
            print(f"Finished: {key}\n")