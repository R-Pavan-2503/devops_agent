"""
graph/builder.py

Full pipeline graph definition.

Node execution order:
  pr_router_node
    ↓
  backend_analyst_node → security_agent_node → code_quality_agent_node
    → architecture_agent_node → qa_agent_node* → frontend_agent_node
    ↓
  consensus_node
    ↓ (route_negotiation)
  development_agent_node  ← [loop back here on rejection, max 3 rounds]
    ↓
  shadow_env_node
    ↓ (route_after_shadow)
  backend_analyst_node (re-review pass if dev agent ran)
    OR
  documentation_summarizer_node (clean first pass)

*qa_agent_node self-skips when pr_has_tests=False
"""

from langgraph.graph import StateGraph, END

from graph.state   import AgentState
from graph.edges   import route_negotiation, route_after_shadow

from agents.nodes import (
    security_agent_node,
    backend_analyst_node,
    development_agent_node,
    documentation_summarizer_node,
    code_quality_agent_node,
    architecture_agent_node,
    qa_agent_node,
    frontend_agent_node,
    critique_resolve_agent_node
)
from agents.router_node import pr_router_node
from sandbox.shadow_node import shadow_env_node


# ---------------------------------------------------------------------------
# Utility nodes
# ---------------------------------------------------------------------------

def environment_sandbox_node(state: AgentState):
    """Kept for backward compat — actual sandbox is shadow_env_node now."""
    print(" Deployment: Consensus reached — routing to shadow environment.")
    return {}


def human_fallback_node(state: AgentState):
    """
    Reached when the pipeline exhausts all 3 review iterations without
    consensus or when the shadow build fails on the final attempt.
    Stamps requires_human_review=True so the dashboard can tag a Senior Dev.
    """
    print(" [FALLBACK] Iteration limit reached. Escalating to human reviewer.")
    return {"requires_human_review": True}


def consensus_node(state: AgentState):
    """
    Fan-in point — collects all specialist votes.

    Fix #1 — Memory Wipe Bug:
        active_critiques are NO LONGER wiped here. The Critique Resolve
        Agent is the primary consumer of these critiques; it must read
        them BEFORE they are cleared.

        The wipe happens inside development_agent_node, after the CRA
        has already synthesized them into a master_directive.

    Fix #11 — Always persist critiques to full_history:
        Previously critiques were only written to full_history on rejection.
        Now ALL active_critiques are persisted regardless of vote outcome
        so the doc agent accumulates the complete decision trail across rounds.
    """
    votes = state.get("domain_approvals", {})
    print(f" Consensus Node: All agents finished. Votes: {votes}")

    # Always persist the current round's critiques to long-term history,
    # even if all agents approved (empty list is a valid historical record).
    current_critiques = state.get("active_critiques", [])
    if current_critiques:
        print(f" → {len(current_critiques)} critiques archived to full_history.")

    return {"full_history": current_critiques}


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

workflow = StateGraph(AgentState)

# --- Nodes ---
workflow.add_node("pr_router_node",               pr_router_node)
workflow.add_node("backend_analyst_node",          backend_analyst_node)
workflow.add_node("security_agent_node",           security_agent_node)
workflow.add_node("code_quality_agent_node",       code_quality_agent_node)
workflow.add_node("architecture_agent_node",       architecture_agent_node)
workflow.add_node("qa_agent_node",                 qa_agent_node)
workflow.add_node("frontend_agent_node",           frontend_agent_node)
workflow.add_node("critique_resolve_agent_node", critique_resolve_agent_node)
workflow.add_node("consensus_node",                consensus_node)
workflow.add_node("development_agent_node",        development_agent_node)
workflow.add_node("shadow_env_node",               shadow_env_node)
workflow.add_node("human_fallback_node",           human_fallback_node)
workflow.add_node("documentation_summarizer_node", documentation_summarizer_node)

# --- Entry point ---
workflow.set_entry_point("pr_router_node")

# --- PR Router → Pipeline start ---
workflow.add_edge("pr_router_node", "backend_analyst_node")

# --- Sequential specialist chain ---
workflow.add_edge("backend_analyst_node",    "security_agent_node")
workflow.add_edge("security_agent_node",     "code_quality_agent_node")
workflow.add_edge("code_quality_agent_node", "architecture_agent_node")
workflow.add_edge("architecture_agent_node", "qa_agent_node")
workflow.add_edge("qa_agent_node",           "frontend_agent_node")
workflow.add_edge("frontend_agent_node",     "consensus_node")

# --- Consensus → dev agent / shadow / fallback ---
workflow.add_conditional_edges("consensus_node", route_negotiation)
workflow.add_edge("critique_resolve_agent_node", "development_agent_node")
workflow.add_edge("development_agent_node", "backend_analyst_node")

# --- Shadow env → re-review loop OR docs ---
workflow.add_conditional_edges("shadow_env_node", route_after_shadow)

# --- Terminal paths ---
workflow.add_edge("human_fallback_node",           "documentation_summarizer_node")
workflow.add_edge("documentation_summarizer_node", END)

# --- Compile ---
app = workflow.compile()


# ---------------------------------------------------------------------------
# Quick local test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os

    MOCK_DIR  = "test_apps/backend_login_go"
    REPO_NAME = "backend_pandhi"

    current_files = {}
    for root, dirs, files in os.walk(MOCK_DIR):
        for file in files:
            if file.endswith(".go"):
                filepath = os.path.join(root, file).replace("\\", "/")
                with open(filepath, encoding="utf-8") as f:
                    current_files[filepath] = f.read()

    initial_state = {
        "pr_url":       f"https://github.com/fake/{REPO_NAME}/pull/1",
        "current_files": current_files,
        "iteration_count": 0,
        "ast_is_valid":  True,
        "shadow_passed": False,
        "repo_name":     REPO_NAME,
        "uac_context":   "",
        "pr_title":      "",
        "pr_body":       "",
        "domain_approvals": {
            "security": "pending", "architecture": "pending",
            "code_quality": "pending", "qa": "pending", "frontend": "pending",
        },
        "active_critiques": [],
        "full_history":     [],
    }

    for output in app.stream(initial_state):
        for node_name in output:
            print(f"\n[OK] {node_name} finished.")

    print("\n[DONE] Pipeline test complete!")