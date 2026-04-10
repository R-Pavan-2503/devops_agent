from typing import Annotated, TypedDict
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