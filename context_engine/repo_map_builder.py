import subprocess
import re
from pathlib import Path

from config import REPO_MAPS_DIR


def _estimate_tokens(text: str) -> int:
    # Conservative rough estimate for budget enforcement.
    return max(len(text) // 4, 0)


def _truncate_with_header(text: str, token_cap: int) -> str:
    if _estimate_tokens(text) <= token_cap:
        return text
    approx_chars = token_cap * 4
    trimmed = text[:approx_chars]
    omitted = max(len(text) - len(trimmed), 0)
    return f"[TRUNCATED: {omitted} chars omitted]\n{trimmed}"


def _resolve_one_hop_imports(workspace_path: str, changed_files: list[str]) -> list[str]:
    root = Path(workspace_path)
    resolved: set[str] = set()
    for changed in changed_files:
        abs_path = root / changed
        if not abs_path.exists():
            continue
        suffix = abs_path.suffix.lower()
        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        if suffix in {".js", ".jsx", ".ts", ".tsx"}:
            for rel in re.findall(r"from\s+['\"](\.[^'\"]+)['\"]", content):
                base = (abs_path.parent / rel).resolve()
                candidates = [base, base.with_suffix(".ts"), base.with_suffix(".tsx"), base.with_suffix(".js"), base.with_suffix(".jsx"), base / "index.ts", base / "index.js"]
                for c in candidates:
                    try:
                        if c.exists() and c.is_file() and str(c).startswith(str(root)):
                            resolved.add(c.relative_to(root).as_posix())
                    except Exception:
                        continue

        if suffix == ".py":
            for mod in re.findall(r"^\s*(?:from|import)\s+([a-zA-Z0-9_\.]+)", content, flags=re.MULTILINE):
                candidate = root / Path(*mod.split("."))
                for c in (candidate.with_suffix(".py"), candidate / "__init__.py"):
                    try:
                        if c.exists() and c.is_file() and str(c).startswith(str(root)):
                            resolved.add(c.relative_to(root).as_posix())
                    except Exception:
                        continue
    return sorted(resolved)


def filter_by_pr_scope(repo_map: str, changed_files: list[str], imported_files: list[str] | None = None) -> str:
    """
    Keep only sections that mention changed paths directly.
    If no section matches, fallback to the original map.
    """
    if not repo_map:
        return ""
    if not changed_files:
        return repo_map
    sections = repo_map.split("\n\n")
    keys = [f.replace("\\", "/").lower() for f in changed_files]
    if imported_files:
        keys.extend(f.replace("\\", "/").lower() for f in imported_files)
    filtered = []
    for section in sections:
        low = section.lower()
        if any(k in low for k in keys):
            filtered.append(section)
    if not filtered:
        return repo_map
    return "\n\n".join(filtered)


def build_repo_map(repo_name: str, workspace_path: str, commit_sha: str, changed_files: list[str] | None = None) -> dict:
    """
    Build or load deterministic repo map from Repomix.
    Returns: {repo_map_str, cache_path, cache_hit}
    """
    commit_short = (commit_sha or "unknown")[:8]
    safe_repo = (repo_name or "unknown").replace("/", "_").replace("\\", "_")
    REPO_MAPS_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = REPO_MAPS_DIR / f"{safe_repo}_{commit_short}.txt"

    if cache_path.exists():
        repo_map_str = cache_path.read_text(encoding="utf-8", errors="replace")
        print(f"[Repo Map] Cache HIT: {cache_path}")
        one_hop_imports = _resolve_one_hop_imports(workspace_path, changed_files or [])
        scoped = filter_by_pr_scope(repo_map_str, changed_files or [], imported_files=one_hop_imports)
        scoped = _truncate_with_header(scoped, token_cap=6000)
        return {
            "repo_map_str": scoped,
            "cache_path": str(cache_path),
            "cache_hit": True,
        }

    import os
    npx_exec = "npx.cmd" if os.name == "nt" else "npx"
    cmd = [
        npx_exec,
        "--yes",
        "repomix",
        "--compress",
        "--style",
        "plain",
        "--stdout",
        "--ignore",
        "node_modules,.venv,__pycache__,.git,chroma_db,repo_maps",
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=workspace_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "[Repo Map] npx is unavailable. Install Node.js/npm and ensure `npx` is in PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("[Repo Map] Repomix command timed out after 120s.") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(
            "[Repo Map] Repomix failed. "
            f"Exit code={result.returncode}. "
            f"stderr={stderr[:500]}"
        )

    repo_map_str = (result.stdout or "").strip()
    if not repo_map_str:
        raise RuntimeError("[Repo Map] Repomix returned empty output.")

    cache_path.write_text(repo_map_str, encoding="utf-8")
    print(f"[Repo Map] Built from Repomix and cached: {cache_path}")
    one_hop_imports = _resolve_one_hop_imports(workspace_path, changed_files or [])
    scoped = filter_by_pr_scope(repo_map_str, changed_files or [], imported_files=one_hop_imports)
    scoped = _truncate_with_header(scoped, token_cap=6000)
    return {
        "repo_map_str": scoped,
        "cache_path": str(cache_path),
        "cache_hit": False,
    }
