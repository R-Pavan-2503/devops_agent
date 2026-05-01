"""
agents/tools.py

Deprecated ChromaDB tool path kept temporarily for rollback compatibility.
The architecture flow now uses deterministic RepoMap + KnowledgeMap context.
"""

from langchain_core.tools import tool


@tool
def search_codebase_context(search_query: str, repo_name: str) -> str:
    raise NotImplementedError(
        "search_codebase_context is retired. "
        "Use deterministic context via repo_map_builder + knowledge_map_loader."
    )
