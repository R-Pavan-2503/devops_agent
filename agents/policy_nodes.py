from __future__ import annotations

import re

from api.github_client import post_pr_comment
from core.pr_triage import TRIAGE_LIGHTWEIGHT, TRIAGE_SKIP, classify_pr
from core.rule_engine import run_hard_rules
from core.verdicts import aggregate_weighted_verdict
from graph.state import AgentState


def _extract_pr_context(pr_url: str) -> tuple[str, int]:
    match = re.match(r"https://github\.com/([^/]+/[^/]+)/pull/(\d+)", pr_url or "")
    if not match:
        return "", 0
    return match.group(1), int(match.group(2))


def _line_count_from_diff(diff_files: dict[str, str]) -> int:
    total = 0
    for patch in (diff_files or {}).values():
        if not isinstance(patch, str):
            continue
        for line in patch.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                total += 1
            elif line.startswith("-") and not line.startswith("---"):
                total += 1
    return total


def pr_triage_node(state: AgentState) -> dict:
    iteration = state.get("iteration_count", 0) + 1
    print("\n" + "═" * 60)
    print(f"🔄 [worker] STARTING PIPELINE ITERATION {iteration}")
    print("═" * 60 + "\n")
    changed_files = sorted(set(list((state.get("current_files") or {}).keys()) + list((state.get("diff_files") or {}).keys())))
    total_lines = _line_count_from_diff(state.get("diff_files", {}))
    result = classify_pr(
        changed_files=changed_files,
        pr_title=state.get("pr_title", ""),
        diff_stats={"total_lines_changed": total_lines},
        force_full_review=bool(state.get("force_full_review", False)),
    )

    out = {
        "triage_mode": result.mode,
        "triage_reason": result.reason,
        "lightweight_review": result.mode == TRIAGE_LIGHTWEIGHT,
        "skip_pipeline": result.mode == TRIAGE_SKIP,
    }

    if result.mode == TRIAGE_SKIP:
        repo, pr_num = _extract_pr_context(state.get("pr_url", ""))
        if repo and pr_num and result.skip_comment:
            post_pr_comment(repo, pr_num, result.skip_comment)

    return out


def rule_engine_node(state: AgentState) -> dict:
    report = run_hard_rules(state.get("current_files", {}))
    findings = [
        {
            "rule_id": f.rule_id,
            "severity": f.severity,
            "file_path": f.file_path,
            "line": f.line,
            "message": f.message,
            "evidence": f.evidence,
        }
        for f in report.findings
    ]
    critiques = []
    if report.auto_reject:
        preview = findings[:3]
        for item in preview:
            critiques.append(
                f"[RuleEngine:{item['severity']}] {item['file_path']}:{item['line']} {item['message']}"
            )

    return {
        "rule_report": findings,
        "rule_max_severity": report.max_severity,
        "rule_auto_reject": report.auto_reject,
        "active_critiques": critiques,
    }


def verdict_aggregator_node(state: AgentState) -> dict:
    agg = aggregate_weighted_verdict(
        verdict_details=state.get("verdict_details", {}),
        approvals=state.get("domain_approvals", {}),
    )
    return {
        "final_verdict": agg.final_verdict,
        "weighted_score": agg.weighted_score,
        "vetoed_by": agg.vetoed_by,
        "veto_reason": agg.veto_reason,
        "quality_scores": agg.quality_scores,
        "full_history": state.get("active_critiques", []),
    }

