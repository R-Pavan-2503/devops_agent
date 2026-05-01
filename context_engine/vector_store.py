"""
context_engine/vector_store.py

ChromaDB Vector Store Wrapper using local sentence-transformers embeddings.
No API key required â€” completely offline via all-MiniLM-L6-v2.
DEPRECATION NOTICE:
As of 2026-05-01 this module is rollback-only for one week while the
deterministic RepoMap + KnowledgeMap engine is active in production.
Planned cleanup: remove Chroma dependencies and this module after rollback window.


Exposes three public functions used throughout the system:
    - add_chunks(chunks)             â†’ bulk upsert
    - delete_by_file(file, repo)     â†’ remove stale vectors on PR merge
    - search(query, repo, n)         â†’ semantic similarity search
"""

import os
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

# ---------------------------------------------------------------------------
# Client & Collection Initialization
# ---------------------------------------------------------------------------

# Resolve chroma_db path relative to this file's project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CHROMA_PATH  = str(_PROJECT_ROOT / "chroma_db")

_COLLECTION_NAME  = "enterprise_codebase"
_EMBEDDING_MODEL  = "all-MiniLM-L6-v2"    # ~90MB, downloads once, then cached

# Build embedding function (sentence-transformers, fully local)
_embedding_fn = SentenceTransformerEmbeddingFunction(
    model_name=_EMBEDDING_MODEL,
    device="cpu",           # change to "cuda" if you have a GPU
)

# Persistent client â€” data survives restarts in ./chroma_db/
_client = chromadb.PersistentClient(path=_CHROMA_PATH)

# Create or reuse the collection
_collection = _client.get_or_create_collection(
    name=_COLLECTION_NAME,
    embedding_function=_embedding_fn,
    metadata={"hnsw:space": "cosine"},   # cosine distance for semantic search
)

print(f"[vector_store] ChromaDB ready at: {_CHROMA_PATH}")
print(f"[vector_store] Collection '{_COLLECTION_NAME}' â€” {_collection.count()} vectors loaded.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_chunks(chunks: list[dict]) -> int:
    """
    Embed and upsert a list of code chunks into the vector store.

    Each chunk must have the shape produced by chunk_file():
        {"id": str, "text": str, "metadata": {"repo_name": ..., "file_path": ..., ...}}

    Returns the number of chunks upserted.
    """
    if not chunks:
        return 0

    ids        = [c["id"]       for c in chunks]
    documents  = [c["text"]     for c in chunks]
    metadatas  = [c["metadata"] for c in chunks]

    # ChromaDB upsert: inserts new, updates existing (matched by id)
    _collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )

    return len(chunks)


def delete_by_file(file_path: str, repo_name: str) -> int:
    """
    Delete all vectors whose metadata matches both file_path AND repo_name.
    Used during the incremental webhook sync to flush stale chunks before re-ingesting.

    Returns the number of deleted vectors (approximate â€” ChromaDB returns None on delete).
    """
    results = _collection.get(
        where={
            "$and": [
                {"repo_name":  {"$eq": repo_name}},
                {"file_path":  {"$eq": file_path}},
            ]
        },
        include=[],   # only need IDs
    )

    ids_to_delete = results.get("ids", [])
    if ids_to_delete:
        _collection.delete(ids=ids_to_delete)
        print(f"[vector_store] Deleted {len(ids_to_delete)} vectors for '{file_path}' in '{repo_name}'")

    return len(ids_to_delete)


def search(query: str, repo_name: str, n_results: int = 3) -> list[str]:
    """
    Semantic search restricted to a specific repository.

    Returns a list of raw code-text strings (up to n_results items),
    ordered by cosine similarity to the query.
    """
    results = _collection.query(
        query_texts=[query],
        n_results=n_results,
        where={"repo_name": {"$eq": repo_name}},
        include=["documents", "metadatas", "distances"],
    )

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    # Format each result with a header so agents can quickly orient themselves
    formatted: list[str] = []
    for doc, meta in zip(documents, metadatas):
        header = (
            f"# File: {meta.get('file_path', 'unknown')}\n"
            f"# Language: {meta.get('language', 'unknown')} | "
            f"Block: {meta.get('block_type', 'unknown')}\n"
        )
        formatted.append(header + doc)

    return formatted


def collection_stats() -> dict:
    """Return basic stats about the vector store (useful for debugging)."""
    return {
        "collection": _COLLECTION_NAME,
        "total_vectors": _collection.count(),
        "chroma_path": _CHROMA_PATH,
        "embedding_model": _EMBEDDING_MODEL,
    }
