"""
agents/tools.py

LangGraph-compatible @tool for semantic codebase context retrieval.
The Architecture and Security agents use this tool to query the ChromaDB
vector store for relevant code patterns before reviewing a PR.

Usage (within a LangGraph node):
    from agents.tools import search_codebase_context
    llm_with_tools = llm.bind_tools([search_codebase_context])
"""

from langchain_core.tools import tool

from context_engine.vector_store import search


@tool
def search_codebase_context(search_query: str, repo_name: str) -> str:
    """
    Search the enterprise codebase vector database for code relevant to a query.

    Use this tool BEFORE giving a final verdict on a pull request to understand:
    - How similar functions or patterns are implemented elsewhere in the repo
    - What architectural conventions already exist
    - How authentication, config, or security-sensitive code is normally handled

    Args:
        search_query: A natural-language description of what you are looking for.
                      Examples:
                        "how is database connection initialized"
                        "authentication middleware pattern"
                        "error handling in HTTP handlers"
        repo_name:    The name of the repository to restrict the search to.
                      Must match the repo_name used during ingestion.

    Returns:
        A formatted string of the top 3 most semantically relevant code blocks,
        each prefixed with its file path and language metadata.
    """
    results = search(query=search_query, repo_name=repo_name, n_results=3)

    if not results:
        return (
            f"No relevant code found in repository '{repo_name}' "
            f"for query: '{search_query}'. "
            "The repository may not have been ingested yet — run "
            "`python scripts/bulk_ingest.py` to populate the vector store."
        )

    separator = "\n\n" + "=" * 60 + "\n\n"
    return separator.join(results)
