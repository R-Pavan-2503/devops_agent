"""
scripts/bulk_ingest.py

One-time CLI script to populate the ChromaDB vector store with an entire repository.
Run this once per repository before using the DevOps pipeline to gain full context.

Usage:
    python scripts/bulk_ingest.py --repo-path /path/to/your/repo --repo-name my_repo_name

Example:
    python scripts/bulk_ingest.py --repo-path ../backend_pandhi --repo-name backend_pandhi
    python scripts/bulk_ingest.py --repo-path ../frontend_react --repo-name frontend_react

The script walks every file in the directory, skips unsupported or irrelevant paths,
runs each file through the AST chunking engine, and upserts all code blocks into ChromaDB.
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Allow running from project root with: python scripts/bulk_ingest.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from context_engine.chunking_engine import chunk_file
from context_engine.vector_store import add_chunks, collection_stats

# ---------------------------------------------------------------------------
# Directories and file patterns to skip during traversal
# ---------------------------------------------------------------------------
SKIP_DIRS = {
    ".git",
    "node_modules",
    "vendor",
    "__pycache__",
    ".venv",
    "venv",
    ".env",
    "dist",
    "build",
    ".next",
    "target",           # Rust/Java build output
    "chroma_db",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}

SUPPORTED_EXTENSIONS = {".py", ".go", ".js", ".jsx", ".ts", ".tsx"}

# Files larger than this limit are skipped (avoid ingesting huge generated files)
MAX_FILE_SIZE_BYTES = 512 * 1024   # 512 KB


def should_skip_dir(dir_name: str) -> bool:
    return dir_name in SKIP_DIRS or dir_name.startswith(".")


def ingest_repository(repo_path: str, repo_name: str) -> dict:
    """
    Walk the repository, chunk each supported file, and upsert into ChromaDB.

    Returns a summary dict with counts of files processed, chunks created, etc.
    """
    repo_path = str(Path(repo_path).resolve())

    if not os.path.isdir(repo_path):
        print(f"[ERROR] Not a directory: {repo_path}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Bulk Ingest: '{repo_name}'")
    print(f"  Source:      {repo_path}")
    print(f"{'='*60}\n")

    stats = {
        "files_found":    0,
        "files_skipped":  0,
        "files_chunked":  0,
        "chunks_total":   0,
        "errors":         0,
    }

    start_time = time.time()

    for root, dirs, files in os.walk(repo_path):
        # Prune skip-dirs in-place so os.walk doesn't descend into them
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]

        for filename in files:
            filepath = os.path.join(root, filename)
            ext = Path(filename).suffix.lower()

            # Skip unsupported extensions
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            stats["files_found"] += 1

            # Skip oversized files
            try:
                file_size = os.path.getsize(filepath)
            except OSError:
                stats["errors"] += 1
                continue

            if file_size > MAX_FILE_SIZE_BYTES:
                print(f"  [SKIP] Too large ({file_size // 1024}KB): {filepath}")
                stats["files_skipped"] += 1
                continue

            # Chunk the file
            try:
                chunks = chunk_file(filepath, repo_name)
            except Exception as exc:
                print(f"  [ERROR] Chunking failed for {filepath}: {exc}")
                stats["errors"] += 1
                continue

            if not chunks:
                stats["files_skipped"] += 1
                continue

            # Upsert into ChromaDB
            try:
                count = add_chunks(chunks)
                stats["files_chunked"] += 1
                stats["chunks_total"] += count
                print(f"  [OK] {filepath}  ({count} chunks)")
            except Exception as exc:
                print(f"  [ERROR] Upsert failed for {filepath}: {exc}")
                stats["errors"] += 1

    elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print(f"  Ingestion Complete in {elapsed:.1f}s")
    print(f"  Files found:   {stats['files_found']}")
    print(f"  Files chunked: {stats['files_chunked']}")
    print(f"  Files skipped: {stats['files_skipped']}")
    print(f"  Total chunks:  {stats['chunks_total']}")
    print(f"  Errors:        {stats['errors']}")
    print(f"{'='*60}\n")

    # Print vector store stats after ingestion
    vs_stats = collection_stats()
    print(f"  Vector store now has {vs_stats['total_vectors']} total vectors.")
    print(f"  Data stored at: {vs_stats['chroma_path']}\n")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Bulk ingest a repository into the ChromaDB codebase vector store.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest a Go backend repo
  python scripts/bulk_ingest.py --repo-path ../backend_pandhi --repo-name backend_pandhi

  # Ingest this very project as a smoke test
  python scripts/bulk_ingest.py --repo-path . --repo-name devops_agent

  # Ingest a React frontend
  python scripts/bulk_ingest.py --repo-path ../frontend_react --repo-name frontend_react
        """
    )
    parser.add_argument(
        "--repo-path",
        required=True,
        help="Absolute or relative path to the repository root folder."
    )
    parser.add_argument(
        "--repo-name",
        required=True,
        help="A short identifier for the repository (used as the filter key in searches)."
    )

    args = parser.parse_args()
    ingest_repository(repo_path=args.repo_path, repo_name=args.repo_name)


if __name__ == "__main__":
    main()
