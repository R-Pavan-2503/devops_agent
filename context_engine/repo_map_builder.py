import subprocess
from pathlib import Path

from config import REPO_MAPS_DIR


def build_repo_map(repo_name: str, workspace_path: str, commit_sha: str) -> dict:
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
        return {
            "repo_map_str": repo_map_str,
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
    return {
        "repo_map_str": repo_map_str,
        "cache_path": str(cache_path),
        "cache_hit": False,
    }
