from __future__ import annotations

from dataclasses import dataclass


AGENT_POLICY = {
    "security": {"weight": 3.0, "has_veto": True, "veto_on": {"CRITICAL", "HIGH"}},
    "architecture": {"weight": 2.0, "has_veto": True, "veto_on": {"CRITICAL"}},
    "backend": {"weight": 1.5, "has_veto": False, "veto_on": set()},
    "code_quality": {"weight": 1.0, "has_veto": False, "veto_on": set()},
    "frontend": {"weight": 1.0, "has_veto": False, "veto_on": set()},
    "qa": {"weight": 1.0, "has_veto": False, "veto_on": set()},
}


@dataclass(frozen=True)
class AggregationResult:
    final_verdict: str
    weighted_score: float
    vetoed_by: str
    veto_reason: str
    quality_scores: dict[str, int]


def aggregate_weighted_verdict(verdict_details: dict, approvals: dict) -> AggregationResult:
    details = verdict_details or {}
    votes = approvals or {}

    for agent, cfg in AGENT_POLICY.items():
        if not cfg.get("has_veto"):
            continue
        agent_vote = votes.get(agent, "pending")
        agent_severity = str((details.get(agent, {}) or {}).get("severity", ""))
        if agent_vote == "rejected" and agent_severity in cfg.get("veto_on", set()):
            return AggregationResult(
                final_verdict="rejected",
                weighted_score=0.0,
                vetoed_by=agent,
                veto_reason=f"{agent} veto due to {agent_severity}",
                quality_scores=_build_quality_scores(details),
            )

    total_weight = 0.0
    approved_weight = 0.0
    for agent, cfg in AGENT_POLICY.items():
        w = float(cfg["weight"])
        total_weight += w
        if votes.get(agent) == "approved":
            approved_weight += w
    weighted_score = approved_weight / total_weight if total_weight else 0.0
    final_verdict = "approved" if weighted_score >= 0.65 else "rejected"
    return AggregationResult(
        final_verdict=final_verdict,
        weighted_score=weighted_score,
        vetoed_by="",
        veto_reason="",
        quality_scores=_build_quality_scores(details),
    )


def _build_quality_scores(verdict_details: dict) -> dict[str, int]:
    buckets = {
        "security": [],
        "architecture": [],
        "code_quality": [],
    }
    for agent, detail in (verdict_details or {}).items():
        conf = float((detail or {}).get("confidence", 0.0))
        vote = str((detail or {}).get("vote", "pending"))
        score = int(round(100 * conf)) if vote == "approved" else int(round(100 * (1 - conf)))
        if agent in buckets:
            buckets[agent].append(max(min(score, 100), 0))
    out: dict[str, int] = {}
    for key, vals in buckets.items():
        out[key] = int(round(sum(vals) / len(vals))) if vals else 0
    return out

