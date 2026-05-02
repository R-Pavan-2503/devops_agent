from __future__ import annotations

import re
from pathlib import Path


LOGIC_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".go"}


def _is_test_file(path: Path) -> bool:
    n = path.name.lower()
    return (
        n.endswith(".test.js")
        or n.endswith(".test.jsx")
        or n.endswith(".test.ts")
        or n.endswith(".test.tsx")
        or n.endswith(".spec.js")
        or n.endswith(".spec.ts")
        or n.endswith("_test.py")
        or n.endswith("_test.go")
        or "test" in n
    )


def _logic_changed(changed_files: list[str]) -> list[str]:
    out = []
    for raw in changed_files:
        p = Path(raw)
        if p.suffix.lower() in LOGIC_EXTS and not _is_test_file(p):
            out.append(raw.replace("\\", "/"))
    return out


def _candidate_tokens(path_str: str) -> set[str]:
    p = Path(path_str)
    stem = p.stem.lower()
    parts = [x.lower() for x in p.with_suffix("").parts if x and x not in {".", ".."}]
    tokens = {stem}
    tokens.update(parts[-3:])
    return {t for t in tokens if len(t) >= 3}


def evaluate_test_quality(changed_files: list[str], workspace_path: str) -> tuple[float, str, dict[str, list[str]]]:
    changed_logic = _logic_changed(changed_files)
    if not changed_logic:
        return 1.0, "HIGH", {}

    root = Path(workspace_path)
    if not root.exists():
        changed_tests = sum(1 for p in changed_files if _is_test_file(Path(p)))
        score = min(changed_tests / max(len(changed_logic), 1), 1.0)
        if score >= 0.8:
            return score, "HIGH", {}
        if score >= 0.4:
            return score, "MEDIUM", {}
        return score, "LOW", {}

    import os
    test_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prevent traversal into heavy/system directories
        dirnames[:] = [d for d in dirnames if d not in {"node_modules", ".git", ".venv", "__pycache__"}]
        for f in filenames:
            p = Path(dirpath) / f
            try:
                if p.is_file() and _is_test_file(p):
                    test_files.append(p)
            except OSError:
                continue
    if not test_files:
        return 0.0, "LOW", {}

    coverage_map: dict[str, list[str]] = {}
    for rel_logic in changed_logic:
        tokens = _candidate_tokens(rel_logic)
        hits: list[str] = []
        for test_path in test_files:
            try:
                content = test_path.read_text(encoding="utf-8", errors="replace").lower()
            except Exception:
                continue
            if any(re.search(rf"\b{re.escape(tok)}\b", content) for tok in tokens):
                hits.append(test_path.as_posix())
        coverage_map[rel_logic] = hits

    covered = sum(1 for _, tests in coverage_map.items() if tests)
    score = covered / max(len(changed_logic), 1)
    if score >= 0.8:
        label = "HIGH"
    elif score >= 0.4:
        label = "MEDIUM"
    else:
        label = "LOW"
    return score, label, coverage_map
