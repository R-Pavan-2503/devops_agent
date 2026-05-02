"""
agents/router_node.py

PR Router Node — classifies the incoming PR and sets dynamic invocation flags.

Runs FIRST in the pipeline before any specialist agent.

Sets in AgentState:
  pr_has_tests       : bool — True if test files exist in the PR (enables QA Agent)
  is_bugfix_or_refactor: bool — True if PR is a bugfix/refactor with no UAC (skips Scrum)
  pr_type            : str  — "backend" | "frontend" | "mixed" | "unknown"
  needs_api_contract_check: bool — True when cross-discipline check is needed

No LLM call is made — purely deterministic heuristics so zero tokens are spent.
"""

import re
from pathlib import Path
from graph.state import AgentState
from core.feedback_store import record_coverage_signal
from core.test_quality import evaluate_test_quality

# ---------------------------------------------------------------------------
# File-type heuristics
# ---------------------------------------------------------------------------

_BACKEND_EXTENSIONS  = {".go", ".py", ".java", ".rs", ".rb", ".php", ".cs"}
_FRONTEND_EXTENSIONS = {".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte", ".css", ".scss", ".html"}

_TEST_PATTERNS = re.compile(
    r"(_test\.go|\.test\.(ts|tsx|js|jsx)|_test\.py|spec\.(ts|js)|\.spec\.(ts|js)|test_.*\.py)$",
    re.IGNORECASE,
)

_BUGFIX_PATTERNS = re.compile(
    r"\b(fix|bugfix|hotfix|patch|refactor|chore|cleanup|typo|lint|style)\b",
    re.IGNORECASE,
)

_FEATURE_PATTERNS = re.compile(
    r"\b(feat|feature|add|implement|new|enhance|support)\b",
    re.IGNORECASE,
)


def _extract_pr_number(pr_url: str) -> int:
    match = re.search(r"/pull/(\d+)", pr_url or "")
    if not match:
        return 0
    return int(match.group(1))


def _classify_pr_type(files_dict: dict[str, str]) -> str:
    """Determine if the PR is backend, frontend, or mixed based on file extensions."""
    has_backend  = any(Path(p).suffix in _BACKEND_EXTENSIONS  for p in files_dict)
    has_frontend = any(Path(p).suffix in _FRONTEND_EXTENSIONS for p in files_dict)

    if has_backend and has_frontend:
        return "mixed"
    elif has_backend:
        return "backend"
    elif has_frontend:
        return "frontend"
    return "unknown"


def _has_test_files(files_dict: dict[str, str]) -> bool:
    """Return True if any file in the PR looks like a test file."""
    return any(_TEST_PATTERNS.search(p) for p in files_dict)


def _is_bugfix_or_refactor(pr_title: str, pr_body: str, uac_context: str) -> bool:
    """
    Return True when the PR is a documented bugfix/refactor that genuinely
    has no User Story UAC.  Both conditions must hold:
      1. Title/body signals a bugfix/refactor (not a feature).
      2. No UAC context was injected from Jira/ADO.
    """
    if uac_context.strip():
        # A UAC was provided — regardless of title, treat as feature PR
        return False

    combined = f"{pr_title} {pr_body}"
    is_fix    = bool(_BUGFIX_PATTERNS.search(combined))
    is_feat   = bool(_FEATURE_PATTERNS.search(combined))

    # If it smells like a fix AND does NOT smell like a feature, skip Scrum check
    return is_fix and not is_feat


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def pr_router_node(state: AgentState) -> dict:
    """
    Classifies the PR and sets routing flags in AgentState.
    Zero LLM calls — fast, free, deterministic.
    """
    files_dict  = state.get("current_files", {})
    pr_url      = state.get("pr_url", "")
    uac_context = state.get("uac_context", "")

    # Extract PR title/body hints from pr_url (in real webhook flow these come
    # from WebhookPayload; in test_request.py they're not available so we default)
    pr_title = state.get("pr_title", "")
    pr_body  = state.get("pr_body",  "")

    pr_type      = _classify_pr_type(files_dict)
    has_tests    = _has_test_files(files_dict)
    is_bugfix    = _is_bugfix_or_refactor(pr_title, pr_body, uac_context)

    # Cross-discipline check is needed whenever the PR touches only ONE discipline
    # (a mixed PR already contains both sides — no cross-check needed)
    needs_api_contract_check = pr_type in ("backend", "frontend")
    changed_paths = list(files_dict.keys())
    workspace_path = state.get("sandbox_workspace_path", "")
    coverage_score, quality_label, coverage_map = evaluate_test_quality(changed_paths, workspace_path)
    pr_number = _extract_pr_number(pr_url)
    try:
        record_coverage_signal(pr_number, state.get("repo_name", "unknown"), coverage_score, quality_label)
    except Exception as exc:
        print(f" PR Router: coverage signal persistence failed (non-fatal): {exc}")

    covered_count = sum(1 for tests in coverage_map.values() if tests)
    print(
        " PR Router: "
        f"type={pr_type} | has_tests={has_tests} | is_bugfix={is_bugfix} "
        f"| cross_check={needs_api_contract_check} | test_quality={quality_label} ({coverage_score:.2f}, covered={covered_count}/{max(len(coverage_map),1)})"
    )

    return {
        "pr_type":                  pr_type,
        "pr_has_tests":             has_tests,
        "is_bugfix_or_refactor":    is_bugfix,
        "needs_api_contract_check": needs_api_contract_check,
        "test_coverage_signal":     coverage_score,
        "test_quality_label":       quality_label,
        # Initialise shadow_passed to False for this run
        "shadow_passed": False,
    }
