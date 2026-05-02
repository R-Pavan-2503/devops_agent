from pathlib import Path
import re

from config import KNOWLEDGE_MAP_PROJECTS_FOLDER, OBSIDIAN_VAULT_ROOT


def _extract_source_commit(index_text: str) -> str:
    # Try YAML frontmatter first
    frontmatter_match = re.match(r"^---\n(.*?)\n---\n", index_text, re.DOTALL)
    if frontmatter_match:
        fm = frontmatter_match.group(1)
        for line in fm.splitlines():
            if line.strip().startswith("source_commit:"):
                return line.split(":", 1)[1].strip()
    # Fallback to body marker
    fallback = re.search(r"source_commit:\s*([A-Za-z0-9._-]+)", index_text)
    return fallback.group(1) if fallback else ""


def load_knowledge_context(repo_name: str, commit_sha: str) -> dict:
    """
    Load index.md + up to 2 pattern notes for repo.
    Returns: {knowledge_context_str, source_commit, map_exists}
    """
    repo_dir = OBSIDIAN_VAULT_ROOT / KNOWLEDGE_MAP_PROJECTS_FOLDER / repo_name
    index_path = repo_dir / "index.md"
    if not index_path.exists():
        print(f"[Knowledge Map] Missing index: {index_path}")
        return {"knowledge_context_str": "", "source_commit": "", "map_exists": False}

    index_text = index_path.read_text(encoding="utf-8", errors="replace")
    source_commit = _extract_source_commit(index_text)
    current_short = (commit_sha or "")[:8]
    if source_commit and current_short and source_commit != current_short:
        print(
            f"[Knowledge Map] source_commit differs from current commit ({source_commit} -> {current_short})."
        )

    pattern_dir = repo_dir / "patterns"
    pattern_texts = []
    if pattern_dir.exists():
        for p in sorted(pattern_dir.glob("*.md"))[:2]:
            pattern_texts.append(f"\n[Pattern File: {p.name}]\n{p.read_text(encoding='utf-8', errors='replace')}")

    context = (
        f"[Knowledge Index: {index_path}]\n{index_text}\n"
        + "\n".join(pattern_texts)
    ).strip()
    if len(context) > 12000:
        omitted = len(context) - 12000
        context = f"[TRUNCATED: {omitted} chars omitted]\n{context[:12000]}"
    print(f"[Knowledge Map] Loaded: {index_path}")
    return {
        "knowledge_context_str": context,
        "source_commit": source_commit,
        "map_exists": True,
    }
