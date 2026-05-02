"""
CodeSentinel V2 graph builder.
"""

from langgraph.graph import END, StateGraph

from agents.nodes import (
    architecture_agent_node,
    backend_analyst_node,
    code_quality_agent_node,
    critique_resolve_agent_node,
    development_agent_node,
    documentation_summarizer_node,
    frontend_agent_node,
    qa_agent_node,
    security_agent_node,
)
from agents.policy_nodes import pr_triage_node, rule_engine_node, verdict_aggregator_node
from agents.router_node import pr_router_node
from graph.edges import (
    route_after_aggregator,
    route_after_backend,
    route_after_frontend_gate,
    route_after_rules,
    route_after_security,
    route_after_shadow,
    route_after_triage,
)
from graph.state import AgentState
from sandbox.shadow_node import shadow_env_node


def human_fallback_node(state: AgentState):
    print("[FALLBACK] Iteration limit reached. Escalating to human reviewer.")
    return {"requires_human_review": True}


def _frontend_gate_passthrough(state: AgentState):
    return {}


workflow = StateGraph(AgentState)

workflow.add_node("pr_triage_node", pr_triage_node)
workflow.add_node("rule_engine_node", rule_engine_node)
workflow.add_node("security_agent_node", security_agent_node)
workflow.add_node("pr_router_node", pr_router_node)
workflow.add_node("code_quality_agent_node", code_quality_agent_node)
workflow.add_node("backend_analyst_node", backend_analyst_node)
workflow.add_node("frontend_agent_node", frontend_agent_node)
workflow.add_node("architecture_agent_node", architecture_agent_node)
workflow.add_node("qa_agent_node", qa_agent_node)
workflow.add_node("verdict_aggregator_node", verdict_aggregator_node)
workflow.add_node("critique_resolve_agent_node", critique_resolve_agent_node)
workflow.add_node("development_agent_node", development_agent_node)
workflow.add_node("shadow_env_node", shadow_env_node)
workflow.add_node("human_fallback_node", human_fallback_node)
workflow.add_node("documentation_summarizer_node", documentation_summarizer_node)
workflow.add_node("frontend_gate_node", _frontend_gate_passthrough)

workflow.set_entry_point("pr_triage_node")

workflow.add_conditional_edges("pr_triage_node", route_after_triage)
workflow.add_conditional_edges("rule_engine_node", route_after_rules)
workflow.add_edge("pr_router_node", "security_agent_node")
workflow.add_conditional_edges("security_agent_node", route_after_security)

workflow.add_edge("code_quality_agent_node", "backend_analyst_node")
workflow.add_conditional_edges("backend_analyst_node", route_after_backend)
workflow.add_conditional_edges("frontend_gate_node", route_after_frontend_gate)
workflow.add_edge("frontend_agent_node", "architecture_agent_node")
workflow.add_edge("architecture_agent_node", "qa_agent_node")
workflow.add_edge("qa_agent_node", "verdict_aggregator_node")

workflow.add_conditional_edges("verdict_aggregator_node", route_after_aggregator)
workflow.add_edge("critique_resolve_agent_node", "development_agent_node")
workflow.add_edge("development_agent_node", "pr_triage_node")

workflow.add_conditional_edges("shadow_env_node", route_after_shadow)
workflow.add_edge("human_fallback_node", "documentation_summarizer_node")
workflow.add_edge("documentation_summarizer_node", END)

app = workflow.compile()
