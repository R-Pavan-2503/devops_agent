from typing import Annotated, TypedDict, Optional
import operator

# Custom reducer: an empty list [] acts as a 'wipe' signal for short-term memory
def wipeable_add(existing: list, new: list) -> list:
    if new == []:
        return []
    return existing + new

# Custom reducer to merge specialist votes 
def merge_votes(dict1: dict, dict2: dict) -> dict:
    if not dict1:
        return dict2
    return {**dict1, **dict2}

# Custom reducer: only update if new value is non-empty (preserves cached context across rounds)
def preserve_if_set(existing: str, new: str) -> str:
    if new:
        return new
    return existing

class AgentState(TypedDict):
    # Ingestion Inputs
    pr_url: str
    ado_ticket_id: str
    uac_context: str 
    current_code: str
    repo_name: str          # The repo identifier used in vector store lookups
    
    # Smart Routing Flags
    pr_type: str 
    needs_api_contract_check: bool 
    
    # Anti-Bloat & Validation
    document_ids: list[str] 
    ast_is_valid: bool 
    
    # Specialist Matrix Votes
    domain_approvals: Annotated[dict, merge_votes] 
    
    # Execution & Negotiation Logs
    active_critiques: Annotated[list[str], wipeable_add]  # Short-term: current round only, wipeable
    full_history: Annotated[list[str], operator.add]      # Long-term: entire journey, never erased
    human_readable_summary: str 
    
    # Cyclic Control & Mitigations
    iteration_count: int
    requires_summarization: bool 
    tie_breaker_invoked: bool
    # Set to True when the iteration limit (3 rounds) is hit without consensus.
    # Signals the dashboard/webhook consumer to escalate to a human reviewer.
    requires_human_review: bool

    # Codebase context cache: Architecture Agent fetches this ONCE in Round 1.
    # Subsequent rounds reuse it without re-querying ChromaDB.
    # reducer: only update when a non-empty value is returned (preserve_if_set)
    arch_codebase_context: Annotated[str, preserve_if_set]