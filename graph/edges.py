"""
Routing logic for CodeSentinel V2 pipeline.
"""

from core.verdicts import AGENT_POLICY
from graph.state import AgentState


def route_after_triage(state: AgentState) -> str:
    if state.get("skip_pipeline", False):
        return "documentation_summarizer_node"
    return "rule_engine_node"


def route_after_rules(state: AgentState) -> str:
    if state.get("rule_auto_reject", False):
        return "verdict_aggregator_node"
    return "pr_router_node"


def route_after_security(state: AgentState) -> str:
    details = state.get("verdict_details", {}) or {}
    security = details.get("security", {}) or {}
    vote = (security.get("vote") or state.get("domain_approvals", {}).get("security", "pending")).lower()
    severity = str(security.get("severity", "")).upper()
    if vote == "rejected" and severity == "CRITICAL":
        return "verdict_aggregator_node"
    if state.get("lightweight_review", False):
        return "architecture_agent_node"
    return "code_quality_agent_node"


def route_after_frontend_gate(state: AgentState) -> str:
    pr_type = str(state.get("pr_type", "unknown"))
    if pr_type == "backend":
        return "architecture_agent_node"
    return "frontend_agent_node"


def route_after_backend(state: AgentState) -> str:
    approvals = state.get("domain_approvals", {}) or {}
    total_weight = sum(float(v.get("weight", 0.0)) for v in AGENT_POLICY.values())
    approved_weight = 0.0
    unresolved_weight = 0.0
    for agent, cfg in AGENT_POLICY.items():
        vote = approvals.get(agent, "pending")
        w = float(cfg.get("weight", 0.0))
        if vote == "approved":
            approved_weight += w
        elif vote not in {"rejected"}:
            unresolved_weight += w
    max_possible = (approved_weight + unresolved_weight) / total_weight if total_weight else 0.0
    if max_possible < 0.65:
        return "verdict_aggregator_node"
    return "frontend_gate_node"


def route_after_aggregator(state: AgentState) -> str:
    if state.get("rule_auto_reject", False):
        return "documentation_summarizer_node"

    if state.get("final_verdict", "rejected") == "approved":
        return "shadow_env_node"

    if state.get("iteration_count", 0) >= 3:
        return "human_fallback_node"
    return "critique_resolve_agent_node"


def route_after_shadow(state: AgentState) -> str:
    shadow_passed = state.get("shadow_passed", False)
    iteration = state.get("iteration_count", 0)

    if not shadow_passed:
        if iteration >= 3:
            return "human_fallback_node"
        return "critique_resolve_agent_node"

    if iteration > 0:
        return "pr_triage_node"
    return "documentation_summarizer_node"
