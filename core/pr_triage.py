from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


TRIAGE_SKIP = "SKIP"
TRIAGE_LIGHTWEIGHT = "LIGHTWEIGHT"
TRIAGE_FULL = "FULL"

_SKIP_TITLE_PREFIXES = ("chore:", "docs:", "style:", "typo:", "wip:")
_FORCE_TITLE_TOKENS = ("fix:", "feat:", "security:", "breaking:")

_LOGIC_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".go"}
_INFRA_FILES = (
    "dockerfile",
    "docker-compose",
    ".github/workflows/",
    ".env.example",
)
_AUTH_PATH_TOKENS = ("auth", "authorization", "payment", "checkout", "jwt", "oauth")
_DOC_FILE_PREFIXES = ("readme", "changelog", "license")
_DOC_DIR_TOKENS = ("/docs/", "\\docs\\")

_SKIP_EXTENSIONS = {
    ".css",
    ".scss",
    ".md",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
}
_LOCK_EXACT = {"package-lock.json", "yarn.lock", "uv.lock", "pnpm-lock.yaml"}


@dataclass(frozen=True)
class TriageResult:
    mode: str
    reason: str
    skip_comment: str
    lightweight_only: bool


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lower().strip()


def _is_test_file(path: str) -> bool:
    p = _normalize(path)
    return (
        p.endswith(".test.js")
        or p.endswith(".test.jsx")
        or p.endswith(".test.ts")
        or p.endswith(".test.tsx")
        or p.endswith("_test.py")
        or p.endswith("_test.go")
        or p.endswith(".spec.js")
        or p.endswith(".spec.ts")
    )


def _is_logic_file(path: str) -> bool:
    return Path(path).suffix.lower() in _LOGIC_EXTENSIONS


def classify_pr(
    changed_files: list[str],
    pr_title: str,
    diff_stats: dict[str, int] | None = None,
    force_full_review: bool = False,
) -> TriageResult:
    title = (pr_title or "").strip().lower()
    files = [f for f in changed_files if f]
    normalized = [_normalize(f) for f in files]
    total_lines = int((diff_stats or {}).get("total_lines_changed", 0))

    if force_full_review:
        return TriageResult(
            mode=TRIAGE_FULL,
            reason="Force review override command present.",
            skip_comment="",
            lightweight_only=False,
        )

    if any(token in title for token in _FORCE_TITLE_TOKENS):
        return TriageResult(
            mode=TRIAGE_FULL,
            reason="PR title indicates logic-impacting change.",
            skip_comment="",
            lightweight_only=False,
        )

    if any(_is_logic_file(path) for path in files):
        if total_lines > 0 and total_lines <= 30:
            return TriageResult(
                mode=TRIAGE_LIGHTWEIGHT,
                reason="Small logic-only change (<=30 lines).",
                skip_comment="",
                lightweight_only=True,
            )
        return TriageResult(
            mode=TRIAGE_FULL,
            reason="Logic file change detected.",
            skip_comment="",
            lightweight_only=False,
        )

    if any(any(flag in path for flag in _INFRA_FILES) for path in normalized):
        return TriageResult(
            mode=TRIAGE_FULL,
            reason="Infrastructure or deployment file changed.",
            skip_comment="",
            lightweight_only=False,
        )

    if any(any(token in path for token in _AUTH_PATH_TOKENS) for path in normalized):
        return TriageResult(
            mode=TRIAGE_FULL,
            reason="Auth/authorization/payment path changed.",
            skip_comment="",
            lightweight_only=False,
        )

    if total_lines > 0 and total_lines <= 10:
        return TriageResult(
            mode=TRIAGE_SKIP,
            reason="Very small diff (<=10 total lines).",
            skip_comment=(
                "CodeSentinel triage: this PR has a very small change set, so the full "
                "AI pipeline was skipped to conserve review budget."
            ),
            lightweight_only=False,
        )

    if title.startswith(_SKIP_TITLE_PREFIXES):
        return TriageResult(
            mode=TRIAGE_SKIP,
            reason="Conventional title indicates non-logic work.",
            skip_comment=(
                "CodeSentinel triage: title indicates docs/style/chore work, "
                "so full AI review was skipped."
            ),
            lightweight_only=False,
        )

    if files and all(_is_test_file(path) for path in files):
        return TriageResult(
            mode=TRIAGE_LIGHTWEIGHT,
            reason="Only test files changed.",
            skip_comment="",
            lightweight_only=True,
        )

    if files and all(Path(path).name.lower() in _LOCK_EXACT or path.lower().endswith(".lock") for path in files):
        return TriageResult(
            mode=TRIAGE_SKIP,
            reason="Only lock files changed.",
            skip_comment=(
                "CodeSentinel triage: lockfile-only PR detected, skipping full AI "
                "pipeline to conserve tokens."
            ),
            lightweight_only=False,
        )

    if files and all(
        (
            Path(path).suffix.lower() in _SKIP_EXTENSIONS
            or Path(path).name.lower().startswith(_DOC_FILE_PREFIXES)
            or any(token in _normalize(path) for token in _DOC_DIR_TOKENS)
            or Path(path).name.lower().endswith(".json")
        )
        for path in files
    ):
        return TriageResult(
            mode=TRIAGE_SKIP,
            reason="Only docs/style/static assets/config changed.",
            skip_comment=(
                "CodeSentinel triage: this PR contains only docs/style/static changes. "
                "Skipping AI pipeline to conserve review budget."
            ),
            lightweight_only=False,
        )

    return TriageResult(
        mode=TRIAGE_FULL,
        reason="Default full review path.",
        skip_comment="",
        lightweight_only=False,
    )

