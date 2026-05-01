from datetime import datetime, timezone
import os
import re
import subprocess
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from config import KNOWLEDGE_MAP_PROJECTS_FOLDER, OBSIDIAN_VAULT_ROOT


WIKI_BUILDER_PROMPT = """You are a senior software architect generating an Obsidian knowledge map.
Using the repository structure summary and selected core source files:
1. Write index.md with frontmatter keys (type, repo, source_commit, generated_at). CRITICAL: BELOW the frontmatter, you MUST write a detailed markdown body that includes a high-level summary of the repository's purpose and architecture, and a bulleted list of [[wiki-links]] pointing to the pattern notes you create.
2. Create 4-6 pattern notes under patterns/*.md.
3. Use [[wiki-links]] between notes.
4. Each note must include: Summary, Tags, The Rule, Key Files / Classes, Anti-Patterns, Related Notes.
5. Return ONLY blocks in this strict format:
[FILE: index.md]
```markdown
...
```
[FILE: patterns/<name>.md]
```markdown
...
```
No extra prose.
"""


def _get_commit_id(workspace_path: str, fallback: str) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace_path,
            capture_output=True,
            text=True,
            check=False,
        )
        commit = (out.stdout or "").strip()
        if commit:
            return commit
    except Exception:
        pass
    return fallback


def _pick_top_source_files(workspace_path: str, limit: int = 5) -> list[Path]:
    exts = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".cs", ".rs"}
    roots = [Path(workspace_path) / "api", Path(workspace_path) / "agents", Path(workspace_path) / "graph"]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in exts:
                files.append(p)
    if len(files) < limit:
        for p in Path(workspace_path).rglob("*"):
            if p.is_file() and p.suffix.lower() in exts:
                files.append(p)
    uniq = []
    seen = set()
    for p in files:
        s = str(p)
        if s not in seen:
            seen.add(s)
            uniq.append(p)
    return uniq[:limit]


def _extract_file_blocks(text: str) -> list[tuple[str, str]]:
    return re.findall(r"\[FILE:\s*(.*?)\s*\]\n```(?:\w+)?\n(.*?)```", text, re.DOTALL)


def _default_index(repo_name: str, commit_id: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        "---\n"
        "type: knowledge-map-index\n"
        f"repo: {repo_name}\n"
        f"source_commit: {commit_id}\n"
        f"generated_at: {ts}\n"
        "---\n\n"
        f"# Knowledge Map: {repo_name}\n\n"
        "## Patterns\n\n"
        "- [[patterns/auth]]\n- [[patterns/db]]\n- [[patterns/api_contracts]]\n- [[patterns/error_handling]]\n"
    )


def generate_knowledge_map(
    repo_name: str,
    workspace_path: str,
    repo_map_str: str,
    commit_sha: str,
    wiki_builder_llm,
) -> dict:
    """
    Generates Obsidian knowledge map files for a repo.
    Returns: {written_files, knowledge_context_str}
    """
    commit_id = _get_commit_id(workspace_path, commit_sha)
    top_files = _pick_top_source_files(workspace_path, limit=5)
    file_snippets = []
    for path in top_files:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            rel = os.path.relpath(path, workspace_path).replace("\\", "/")
            file_snippets.append(f"[FILE: {rel}]\n{content[:5000]}")
        except Exception:
            continue

    human_content = (
        f"Repository: {repo_name}\n"
        f"Commit: {commit_id}\n\n"
        f"Repo map:\n{repo_map_str[:40000]}\n\n"
        f"Top files:\n{chr(10).join(file_snippets)}"
    )
    messages = [
        SystemMessage(content=WIKI_BUILDER_PROMPT),
        HumanMessage(content=human_content),
    ]
    response = wiki_builder_llm.invoke(messages)
    raw = (response.content or "").strip()
    blocks = _extract_file_blocks(raw)

    repo_dir = OBSIDIAN_VAULT_ROOT / KNOWLEDGE_MAP_PROJECTS_FOLDER / repo_name
    patterns_dir = repo_dir / "patterns"
    repo_dir.mkdir(parents=True, exist_ok=True)
    patterns_dir.mkdir(parents=True, exist_ok=True)

    written_files = []
    if not blocks:
        index_path = repo_dir / "index.md"
        index_path.write_text(_default_index(repo_name, commit_id), encoding="utf-8")
        written_files.append(str(index_path))
    else:
        for rel_path, content in blocks:
            rel_path = rel_path.strip().replace("\\", "/")
            if rel_path.startswith("/"):
                rel_path = rel_path[1:]
            target = repo_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            body = content.strip()
            if rel_path == "index.md" and "source_commit:" not in body:
                body = body + f"\n\n> source_commit: {commit_id}\n"
            target.write_text(body, encoding="utf-8")
            written_files.append(str(target))

    index_path = repo_dir / "index.md"
    context = ""
    if index_path.exists():
        context = index_path.read_text(encoding="utf-8", errors="replace")
        for p in sorted(patterns_dir.glob("*.md"))[:2]:
            context += f"\n\n[Pattern File: {p.name}]\n{p.read_text(encoding='utf-8', errors='replace')}"

    print(f"[Wiki Builder] Generated knowledge map for {repo_name}: {len(written_files)} files")
    return {"written_files": written_files, "knowledge_context_str": context}
