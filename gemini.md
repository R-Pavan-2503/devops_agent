# Project Overview

This file contains the complete source code and necessary context for the project.

## Directory Structure
```
README.md
agents/nodes.py
agents/old_prompts.py
agents/prompts.py
agents/schemas.py
agents/tools.py
api/main.py
api/models.py
check_db.py
context_engine/__init__.py
context_engine/chunking_engine.py
context_engine/parser_router.py
context_engine/vector_store.py
graph/builder.py
graph/edges.py
graph/state.py
main.py
pyproject.toml
scripts/__init__.py
scripts/bulk_ingest.py
scripts/inspect_ts.py
scripts/smoke_test.py
test_request.py
worker/celery_app.py
```

## `/main.py`
```python
def main():
    print("Hello from 10-agent-devops!")


if __name__ == "__main__":
    main()

```

## `/README.md`
```markdown
# 10-Agent DevOps Pipeline

## Conceptual Overview
This project serves as an **automated pull request (PR) reviewer and processing pipeline**. It listens for GitHub PR webhooks, securely validates them, offloads the work to a background worker, and uses a team of AI agents (powered by LangGraph and LLMs) to review the PR—acting as specialized developers and security analysts.

### Technology Stack
- **FastAPI**: Provides the HTTP web server and REST endpoints.
- **Celery & Redis**: Handles asynchronous background processing to prevent the webhook endpoint from timing out while AI analysis happens. 
- **LangGraph & LangChain**: Orchestrates a state machine (graph) of multiple AI agents who collaborate or hand off tasks to one another.
- **Groq LLM**: Powers the AI agents (integrated via LangChain).

### Pipeline Flow
1. **Trigger (GitHub Webhook)**
   When a Pull Request is opened or updated on GitHub, a webhook payload is sent to `api/main.py`. The endpoint verifies the `x-hub-signature-256` HMAC signature using a secret key.
   
2. **Background Processing (Celery)**
   The API responds with `202 Accepted` immediately and hands the PR payload off to a Celery background task (`worker/celery_app.py`).
   
3. **Agentic Orchestration (LangGraph)**
   The Celery task runs a StateGraph workflow (`graph/builder.py`). Agents (Backend Dev, Security, Doc Summarizer, Environment deployer) pass around an `AgentState`.

---

## Setup & Running Locally

### 1. Requirements
- Python 3.13+
- Docker Desktop (for Redis)

### 2. Dependency Installation
Create a virtual environment and install dependencies.
```bash
python -m venv .venv
# On Windows:
source .venv/Scripts/activate  
# On macOS/Linux:
# source .venv/bin/activate

pip install -e .
```
*(Optionally, you can use `uv sync` if you have `uv` installed).*

### 3. Docker Setup (Redis)
Celery needs Redis as a message broker. Run the following to start a local Redis container:
```bash
# Optional (if on Linux and docker group isn't setup):
# sudo groupadd docker
# sudo usermod -aG docker $USER
# newgrp docker

docker pull redis:alpine
docker run -d --name devops-redis -p 6379:6379 redis:alpine
```

### 4. Environment Variables
Create a `.env` file in the root directory and add your Groq API key (to enable the AI agents):
```ini
GROQ_API_KEY=your_actual_groq_api_key_here
```

### 5. Start the Services
Open **three separate terminal windows** and ensure your virtual environment is activated in each one.

**Terminal 1: Start FastAPI Server**
```bash
uvicorn api.main:app --reload --port 8000
```

**Terminal 2: Start Celery Worker**
*(Note: On Windows, you typically need the `--pool=solo` flag for Celery to work natively)*
```bash
celery -A worker.celery_app worker --pool=solo --loglevel=info
```

**Terminal 3: Test the Pipeline**
Run the local test script to simulate a GitHub Webhook payload:
```bash
python test_request.py
```
If successful, Terminal 1 will accept the webhook, Terminal 2 will begin processing the PR with LangGraph, and Terminal 3 will display a 202 status code.
```

## `/pyproject.toml`
```toml
[project]
name = "10-agent-devops"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "celery>=5.6.3",
    "chromadb>=1.5.5",
    "fastapi>=0.135.2",
    "httpx>=0.28.1",
    "langchain-core>=1.2.22",
    "langchain-google-genai>=4.2.1",
    "langchain-xai>=1.2.2",
    "langgraph>=1.1.3",
    "pydantic>=2.12.5",
    "python-dotenv>=1.2.2",
    "redis>=7.4.0",
    "sentence-transformers>=5.3.0",
    "tree-sitter>=0.25.2",
    "tree-sitter-go>=0.25.0",
    "tree-sitter-javascript>=0.25.0",
    "tree-sitter-python>=0.25.0",
    "tree-sitter-typescript>=0.23.2",
    "uvicorn>=0.42.0",
]

```

## `/test_request.py`
```python
import sys
from dotenv import load_dotenv

load_dotenv()

# We can directly invoke our compiled LangGraph workflow to test it
from graph.builder import app

print("\n[START] Starting Simulated PR Review Pipeline...")

import os

MOCK_DIR = "test_apps/backend_login_go"
REPO_NAME = "backend_pandhi"

current_files = {}

try:
    for root, dirs, files in os.walk(MOCK_DIR):
        for file in files:
            if file.endswith(".go"):
                filepath = os.path.join(root, file)
                # Normalize path separators for dict keys
                normalized_path = filepath.replace("\\", "/")
                with open(filepath, "r", encoding="utf-8") as f:
                    current_files[normalized_path] = f.read()
except Exception as e:
    print(f"Error reading mock directory {MOCK_DIR}: {e}")
    sys.exit(1)

# This initial state mimics what the webhook + Celery worker would pass in
initial_state = {
    "pr_url": f"https://github.com/fake/{REPO_NAME}/pull/1",
    # The production source code to be reviewed (multi-file)
    "current_files": current_files,
    "iteration_count": 0,
    "ast_is_valid": True,
    # Tells the Architect agent which vector store repo to query
    "repo_name": REPO_NAME,
    "domain_approvals": {
        "security": "pending",
        "architecture": "pending",
        "code_quality": "pending",
        "qa": "pending",
        "frontend": "pending"
    },
    "active_critiques": [],
    "full_history": []
}

print(f"[TEST] Simulating an incoming pull request for repository: {initial_state['repo_name']}\n")

# Stream the output of every agent as they work
for output in app.stream(initial_state):
    for node_name, result in output.items():
        print(f"\n[OK] {node_name} Finished Processing.")

        print("---------------------------------------------------------------------")
        print()
        print(result)
        print()
        print("***********************************************************************")
        print()
        print()
        
print("\n[DONE] Full testing simulation complete!")
```

## `/check_db.py`
```python
from context_engine.vector_store import _collection

for repo in ['admin_pandhi', 'backend_pandhi', 'staff_pandhi', 'mobile_pandhi']:
    results = _collection.get(where={'repo_name': repo}, include=['metadatas'])
    print(f"{repo}: {len(results.get('ids', []))} chunks stored")

```

## `/agents/nodes.py`
```python
import os
import time
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from graph.state import AgentState
from agents.prompts import (
    SECURITY_AGENT_PROMPT, BACKEND_ANALYST_AGENT_PROMPT, DEV_AGENT_PROMPT,
    DOC_AGENT_PROMPT, CODE_QUALITY_AGENT_PROMPT, ARCHITECT_AGENT_PROMPT, QA_AGENT_PROMPT,
    FRONTEND_AGENT_PROMPT
)
from agents.tools import search_codebase_context

load_dotenv()

# =============================================================================
# LLM INSTANCES
#
# Architecture:
#   - arch_llm       : llama-3.3-70b-versatile  → Architecture Agent (tool-calling, ChromaDB)
#                      and Developer + Doc Agents (heavy reasoning, code generation)
#   - review_llm_70b : llama-3.3-70b-versatile  → Backend Analyst (complex logic checking)
#   - review_llm_8b  : llama-3.1-8b-instant     → Security, Code Quality, Frontend Agents
#                      (lightweight TOON verdict, no tool calls, universal rules)
#   - review_llm_scout: llama-4-scout            → QA Agent (separate TPD bucket)
#
# Token Budget per day (Groq Free Tier):
#   llama-3.3-70b-versatile : 100,000 TPD
#   llama-3.1-8b-instant    : 500,000 TPD
#   llama-4-scout           : 500,000 TPD
# =============================================================================

# Heavy lifter: tool-calling + code generation
arch_llm = ChatOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    model="llama-3.3-70b-versatile",
    max_tokens=3000,
    temperature=0.0
)

# High-quality reviewer: complex backend logic analysis
review_llm_70b = ChatOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    model="llama-3.3-70b-versatile",
    max_tokens=300,
    temperature=0.0
)

# Fast reviewer: universal rule-based checks (security, quality, frontend)
# 500K TPD — nearly impossible to exhaust
review_llm_8b = ChatOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    model="llama-3.1-8b-instant",
    max_tokens=300,
    temperature=0.0
)

# QA Agent: separate token bucket from 70b model
review_llm_scout = ChatOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    model="meta-llama/llama-4-scout-17b-16e-instruct",
    max_tokens=300,
    temperature=0.0
)

# =============================================================================
# TOON Parser (Token-Oriented Object Notation)
# =============================================================================

class SpecialistReview:
    def __init__(self, vote: str, critique: str):
        self.vote = vote
        self.critique = critique


def invoke_strict(messages, llm_instance, max_retries=3):
    """Invokes the chosen LLM and parses the TOON format response."""
    current_messages = list(messages)  # Copy so we don't mutate the caller's list
    
    for attempt in range(max_retries):
        try:
            time.sleep(3)  # Prevent rate-limit bursting
            instructions = (
                "CRITICAL: Output your response in TOON format exactly as below (no json, no braces):\n"
                "vote: [APPROVE or REJECT]\n"
                "critique: [your findings here, 1 string only, or empty if approved]"
            )
            new_messages = current_messages + [HumanMessage(content=instructions)]
            res = llm_instance.invoke(new_messages)

            content = res.content.strip()
            if not content:
                print(f"      (Attempt {attempt+1}) LLM returned empty response. Retrying...")
                continue

            # Strip markdown code fences if the LLM wrapped the response
            if content.startswith("```"):
                parts = content.split("```")
                if len(parts) >= 3:
                    content_inner = parts[1].strip()
                    lines_inner = content_inner.split("\n")
                    if lines_inner[0].lower() in ["toon", "yaml", "test", "plaintext", "text"]:
                        content = "\n".join(lines_inner[1:]).strip()
                    else:
                        content = content_inner

            lines = content.split("\n")
            vote = "rejected"
            critique = ""
            for line in lines:
                if line.lower().startswith("vote:"):
                    vote_str = line[5:].strip().lower()
                    vote = "approved" if "approve" in vote_str else "rejected"
                elif line.lower().startswith("critique:"):
                    critique = line[9:].strip()
                elif line.strip() and not critique and not line.lower().startswith("vote:"):
                    critique += line.strip() + " "

            critique = critique.strip()

            # Prevent 8b agent laziness: if it rejects, it MUST provide an actionable critique
            if vote == "rejected" and (not critique or critique.lower() in ["reject", "rejected"]):
                print(f"      (Attempt {attempt+1}) Agent rejected without providing a reason. Forcing retry...")
                # Append the bad response and a strict warning to the history 
                # so the 0.0 temperature LLM gets a different prompt next time!
                current_messages.append(res)
                current_messages.append(HumanMessage(content="You rejected the code but provided no explanation. You MUST provide a specific, actionable critique formatted as '[CATEGORY] file:line — finding'. Do not just say 'REJECT'. Try again."))
                continue

            return SpecialistReview(vote=vote, critique=critique)

        except Exception as e:
            if attempt == max_retries - 1:
                print(f"      Final attempt failed: {e}")
                raise e
            print(f"      (Attempt {attempt+1}) Parsing failed. Retrying... Error: {e}")
            time.sleep(2)

    raise ValueError(f"LLM consistently returned empty or unparseable responses after {max_retries} attempts.")


def invoke_with_retry(llm_instance, messages, max_retries=5):
    """Generic retry wrapper for raw LLM calls (tool-calling phase)."""
    for attempt in range(max_retries):
        try:
            return llm_instance.invoke(messages)
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"      Final attempt failed: {e}")
                raise e
            print(f"      (Attempt {attempt+1}) API limit/error: {e}. Retrying in 8s...")
            time.sleep(8)


# =============================================================================
# ChromaDB Tool Binding
# ONLY the Architecture Agent uses tool-calling.
# =============================================================================
_context_tools = [search_codebase_context]
arch_llm_with_tools = arch_llm.bind_tools(_context_tools)


# =============================================================================
# Helpers
# =============================================================================

def safe_print_critique(critique: str):
    """Safely print critique strings on Windows consoles without charmap crashes."""
    safe_str = critique.encode("ascii", errors="replace").decode("ascii")
    print(f"   -> Critique: {safe_str}")

def format_files_for_llm(files_dict) -> str:
    if not isinstance(files_dict, dict):
        return str(files_dict)
    
    formatted = ""
    for filepath, content in files_dict.items():
        formatted += f"\n--- FILE: {filepath} ---\n{content}\n"
    return formatted.strip()


# =============================================================================
# AGENT NODES
# =============================================================================

def security_agent_node(state: AgentState):
    """
    Security Agent — Universal Rule Checker.

    Why NO ChromaDB:
        SQL injection, hardcoded credentials, and missing auth are universal
        security anti-patterns. The agent does NOT need to know how your
        specific repo is structured to identify them. It applies the same
        rules regardless of codebase. Removing ChromaDB here saves ~3,000
        tokens per call.
    """
    time.sleep(2)
    print(" Security Agent: Scanning code for vulnerabilities...")

    code = format_files_for_llm(state.get("current_files", {}))
    messages = [
        SystemMessage(content=SECURITY_AGENT_PROMPT),
        HumanMessage(content=f"Review this pull request code for security vulnerabilities:\n\n{code}")
    ]
    ai_review = invoke_strict(messages, review_llm_8b)

    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"security": ai_review.vote},
        "active_critiques": [f"[Round {state.get('iteration_count', 0)}] Security: {ai_review.critique}"]
    }


def architecture_agent_node(state: AgentState):
    """
    Architecture Agent — Codebase Pattern Checker.

    Why ChromaDB (and only here):
        This is the ONLY agent that compares the NEW code against your
        EXISTING codebase conventions (DI patterns, error handling style,
        layer separation). It needs to see how your repo is structured to
        make a meaningful architectural verdict.

    ChromaDB Caching Strategy:
        Round 1: Fetches context from ChromaDB (up to 3 tool calls) and
                 stores it in state['arch_codebase_context'].
        Round 2+: Reuses the cached context directly — the existing codebase
                  hasn't changed between rounds, so there's no need to
                  re-query. This saves ~4,000 tokens per subsequent round.
    """
    time.sleep(2)
    print(" Architecture Agent: Checking structural design (with codebase context)...")

    code = format_files_for_llm(state.get("current_files", {}))
    repo_name = state.get("repo_name", "")
    cached_context = state.get("arch_codebase_context", "")

    if cached_context:
        # ---------------------------------------------------------------
        # Rounds 2 and 3: Reuse cached ChromaDB context from Round 1.
        # The existing codebase doesn't change between review rounds.
        # ---------------------------------------------------------------
        print("   [Cache HIT] Reusing codebase context from Round 1 — skipping ChromaDB query.")
        context_gathered = cached_context
        context_to_save = ""  # Don't overwrite the cache
    else:
        # ---------------------------------------------------------------
        # Round 1: Fetch from ChromaDB. The LLM can make up to 3 tool
        # calls to explore different patterns in the codebase.
        # ---------------------------------------------------------------
        print("   [Cache MISS] Querying ChromaDB for codebase patterns...")
        messages = [
            SystemMessage(content=ARCHITECT_AGENT_PROMPT),
            HumanMessage(content=(
                f"Repository: {repo_name}\n\n"
                f"Review this pull request code:\n\n{code}"
            ))
        ]

        context_gathered = ""
        for _ in range(3):  # Up to 3 different pattern searches
            time.sleep(2)
            response = invoke_with_retry(arch_llm_with_tools, messages)
            messages.append(response)

            if not response.tool_calls:
                break  # LLM decided it has enough context

            for tool_call in response.tool_calls:
                if tool_call["name"] == "search_codebase_context":
                    tool_result = str(search_codebase_context.invoke(tool_call["args"]))
                    context_gathered += f"\n--- Context ---\n{tool_result}\n"
                    messages.append(ToolMessage(
                        tool_call_id=tool_call["id"],
                        name=tool_call["name"],
                        content=tool_result
                    ))

        context_to_save = context_gathered  # Save to state cache

    # Phase 2: Give the final verdict using the gathered context
    phase2_prompt = ARCHITECT_AGENT_PROMPT.split("<tool_use>")[0] + ARCHITECT_AGENT_PROMPT.split("</tool_use>")[1]

    final_messages = [
        SystemMessage(content=phase2_prompt),
        HumanMessage(content=(
            f"Repository: {repo_name}\n\n"
            f"Review this pull request code:\n\n{code}\n\n"
            f"Relevant codebase patterns for reference:\n{context_gathered}"
        ))
    ]
    ai_review = invoke_strict(final_messages, arch_llm)

    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"architecture": ai_review.vote},
        "active_critiques": [f"[Round {state.get('iteration_count', 0)}] Architecture: {ai_review.critique}"],
        "arch_codebase_context": context_to_save  # Empty string on Rounds 2+, preserve_if_set keeps old value
    }


def backend_analyst_node(state: AgentState):
    """
    Backend Analyst — Functional Logic Checker.

    Why NO ChromaDB:
        Checks functional correctness: SQL injection risks, connection
        leak patterns, incorrect HTTP status codes, error handling.
        These are universal backend patterns — no codebase comparison needed.
        Uses the 70b model for its superior reasoning on complex logic.

    Fix #2 — UAC Injection:
        If a uac_context is present in state (from the PR description or Jira
        ticket), it is prepended to the code review prompt. This lets the
        analyst verify that the code actually implements the right feature,
        not just that it is syntactically correct.
    """
    time.sleep(2)
    repo_name = state.get("repo_name", "").lower()
    
    # CROSS-DISCIPLINE REVIEW: 
    # Backend devs already wrote backend code, so the Backend Agent shouldn't review it.
    if "backend" in repo_name:
        print(" Backend Analyst: Skipping backend repo (Cross-discipline review paradigm).")
        return {
            "domain_approvals": {"backend": "approved"},
            "active_critiques": []
        }
        
    print(" Backend Analyst: Checking functional logic and efficiency...")

    code = format_files_for_llm(state.get("current_files", {}))
    uac_context = state.get("uac_context", "").strip()

    uac_block = (
        f"User Acceptance Criteria (UAC):\n{uac_context}\n\n"
        "Verify that the code below implements exactly what the UAC describes.\n"
        "A feature mismatch is a CRITICAL logic flaw — REJECT immediately.\n\n"
    ) if uac_context else ""

    messages = [
        SystemMessage(content=BACKEND_ANALYST_AGENT_PROMPT),
        HumanMessage(content=f"{uac_block}Review this code for functional logic issues:\n\n{code}")
    ]
    ai_review = invoke_strict(messages, review_llm_70b)

    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"backend": ai_review.vote},
        "active_critiques": [f"[Round {state.get('iteration_count', 0)}] Backend: {ai_review.critique}"]
    }


def code_quality_agent_node(state: AgentState):
    """
    Code Quality Agent — Clean Code Checker.

    Why NO ChromaDB:
        Checks naming conventions, function length, docstrings, nesting
        depth. These are language-level universal standards (e.g., Go
        conventions). Has nothing to do with the repo structure.
        Uses the fast 8b model since this is a lightweight check.
    """
    time.sleep(2)
    print(" Code Quality Agent: Checking for clean code...")

    code = format_files_for_llm(state.get("current_files", {}))
    messages = [
        SystemMessage(content=CODE_QUALITY_AGENT_PROMPT),
        HumanMessage(content=code)
    ]
    ai_review = invoke_strict(messages, review_llm_8b)

    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"code_quality": ai_review.vote},
        "active_critiques": [f"[Round {state.get('iteration_count', 0)}] Code Quality: {ai_review.critique}"]
    }


def qa_agent_node(state: AgentState):
    """
    QA / SDET Agent — Testability Checker.

    Why NO ChromaDB:
        Checks if the NEW code is testable: dependency injection used?
        Are interfaces abstracted? Is there input validation? These are
        universal testability patterns checked against the PR code alone.
        Uses Llama-4-Scout which has a separate 500K TPD bucket.

    Fix #2 — UAC Injection:
        If a uac_context is provided, the QA agent is also asked to verify
        that existing tests explicitly cover the acceptance scenarios defined
        in the UAC — not just generic branch coverage.
    """
    time.sleep(2)
    print(" QA Agent: Checking testability and mocks...")

    code = format_files_for_llm(state.get("current_files", {}))
    uac_context = state.get("uac_context", "").strip()

    uac_block = (
        f"User Acceptance Criteria (UAC):\n{uac_context}\n\n"
        "Also verify that the test suite contains at least one test case \n"
        "that validates each UAC scenario above. Missing UAC coverage = REJECT.\n\n"
    ) if uac_context else ""

    messages = [
        SystemMessage(content=QA_AGENT_PROMPT),
        HumanMessage(content=f"{uac_block}{code}")
    ]
    ai_review = invoke_strict(messages, review_llm_scout)

    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"qa": ai_review.vote},
        "active_critiques": [f"[Round {state.get('iteration_count', 0)}] QA: {ai_review.critique}"]
    }


def frontend_agent_node(state: AgentState):
    """
    Frontend Integration Agent — API Contract Checker.

    Why NO ChromaDB:
        Validates that the API response matches the frontend's expected
        contract: correct JSON structure, right HTTP status codes,
        presence of required fields (id, error_message, created_at).
        These are contract rules defined by the frontend team, not by
        the existing backend codebase.
        Uses the fast 8b model for quick verdict.
    """
    time.sleep(2)
    repo_name = state.get("repo_name", "").lower()
    
    # CROSS-DISCIPLINE REVIEW: 
    # Frontend devs already wrote frontend code, so the Frontend Agent shouldn't review it.
    if "frontend" in repo_name:
        print(" Frontend Agent: Skipping frontend repo (Cross-discipline review paradigm).")
        return {
            "domain_approvals": {"frontend": "approved"},
            "active_critiques": []
        }

    print(" Frontend Agent: Checking API contract and formatting...")

    code = format_files_for_llm(state.get("current_files", {}))
    messages = [
        SystemMessage(content=FRONTEND_AGENT_PROMPT),
        HumanMessage(content=code)
    ]
    ai_review = invoke_strict(messages, review_llm_8b)

    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"frontend": ai_review.vote},
        "active_critiques": [f"[Round {state.get('iteration_count', 0)}] Frontend: {ai_review.critique}"]
    }


def development_agent_node(state: AgentState):
    """
    Developer Agent — Code Rewriter.

    Receives the combined critique log from all agents in the current round
    and rewrites the code to fix all identified issues. Uses the 70b model
    for high-quality code generation.
    """
    time.sleep(2)
    print("Development Agent: Rewriting the code to fix issues...")

    broken_code = format_files_for_llm(state.get("current_files", {}))
    current_count = state.get("iteration_count", 0)
    critique_log = state.get("active_critiques", [])

    warning_text = "WARNING: FINAL ATTEMPT. Fix ALL critiques or build fails.\n\n" if current_count == 2 else ""

    human_content = (
        f"Feedback from all reviewers:\n{chr(10).join(critique_log)}\n\n"
        f"{warning_text}"
        f"Please fix this codebase:\n\n{broken_code}\n\n"
        "CRITICAL: First provide your CHECKLIST, then provide the full rewritten source code enclosed in triple backticks for each file you modify. DO NOT wrap the entire response in a single block, but use [FILE: path] followed by a backtick block for EACH file. Do not use any tool calls or wrappers."
    )
    messages = [
        SystemMessage(content=DEV_AGENT_PROMPT),
        HumanMessage(content=human_content)
    ]

    time.sleep(8)  # Rate limit buffer: all review agents just ran
    response = invoke_with_retry(arch_llm, messages)

    new_code = response.content
    checklist = ""
    
    # Parse multi-file output: Look for [FILE: path] and ``` blocks
    import re
    # We first extract checklist - anything before the first [FILE:
    parts = new_code.split("[FILE:", 1)
    if len(parts) > 1:
        checklist = parts[0].strip()
        file_content_part = "[FILE:" + parts[1]
    else:
        file_content_part = new_code
    
    if checklist:
        safe_checklist = checklist.encode("ascii", errors="replace").decode("ascii")
        print(f"\n   -> Verification Checklist:\n{safe_checklist}\n")

    current_files = state.get("current_files", {})
    file_blocks = re.findall(r"\[FILE:\s*(.*?)\s*\]\n*(?:```[\w]*\n)?(.*?)```", file_content_part, re.DOTALL)
    
    for filepath, file_content in file_blocks:
        filepath = filepath.strip()
        # Remove trailing/leading newlines from code if any
        file_content = file_content.strip()
        
        # Write to state dict
        current_files[filepath] = file_content
        
        # Physical write to disk
        try:
            # Create directories if they don't exist
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(file_content)
            print(f"   -> Overwrote local file: {filepath}")
        except Exception as e:
            print(f"   -> [WARNING] Failed to write local file {filepath}: {e}")

    return {
        "current_files": current_files,
        "iteration_count": current_count + 1,
        "ast_is_valid": True,
        # Fix #1: Wipe short-term critique memory HERE, AFTER the Dev Agent has
        # read and consumed it. consensus_node archives them to full_history
        # first; we clear the short-term store so the next round of review
        # agents start with a clean slate.
        "active_critiques": [],
        "domain_approvals": {
            "backend": "pending",
            "security": "pending",
            "architecture": "pending",
            "code_quality": "pending",
            "qa": "pending",
            "frontend": "pending"
        },
    }


def _condense_history(full_log: list, max_entries: int = 12, max_chars_per_entry: int = 120) -> str:
    """
    Fix #4 — Doc Agent Token Bloat.

    Produces a tight timeline string from the full critique history:
      - Only keeps the last `max_entries` entries (default 12) to stay well
        inside the 70b model's usable context window.
      - Truncates any single entry that exceeds `max_chars_per_entry` chars
        (e.g., large code snippets accidentally captured in a critique).

    This replaces the raw `full_log[-18:]` slice that was passed verbatim,
    which could exceed the context window on longer pipelines.
    """
    condensed = []
    for entry in full_log[-max_entries:]:
        if len(entry) > max_chars_per_entry:
            condensed.append(entry[:max_chars_per_entry] + " […truncated]")
        else:
            condensed.append(entry)
    return "\n".join(condensed) if condensed else "(no history recorded)"


def documentation_summarizer_node(state: AgentState):
    """
    Documentation Agent — Report Generator.

    Reads structured verdicts and critiques from state and passes them
    as pre-built data blocks so the LLM copies them verbatim instead of
    guessing from raw log text. This eliminates hallucinated verdicts.
    """
    time.sleep(2)
    print("Doc Agent: Summarizing the journey and saving the report...")

    full_log = state.get("full_history", [])
    files_dict = state.get("current_files", {})
    final_code = format_files_for_llm(files_dict)
    final_votes = state.get("domain_approvals", {})
    iteration_count = state.get("iteration_count", 0)

    # -----------------------------------------------------------------------
    # Build VERDICTS table from the actual pipeline state (not from LLM guess)
    # -----------------------------------------------------------------------
    agent_display_names = {
        "security":     "Security Architect",
        "backend":      "Backend Analyst",
        "frontend":     "Frontend Integration",
        "architecture": "Software Architect",
        "qa":           "QA / SDET",
        "code_quality": "Code Quality",
    }

    verdicts_table = "| Agent | Verdict | Rounds |\n|---|---|---|\n"
    for key, display_name in agent_display_names.items():
        raw_vote = final_votes.get(key, "pending")
        verdict = "APPROVE" if raw_vote == "approved" else "REJECT"
        verdicts_table += f"| {display_name} | {verdict} | {iteration_count} |\n"

    # -----------------------------------------------------------------------
    # Build FINAL_CRITIQUES block from the last round of full_history
    # -----------------------------------------------------------------------
    # full_history entries look like: "[Round N] AgentName: critique text"
    # We scan from the end to get the most recent critique per agent.
    seen_agents = set()
    final_critiques_lines = []
    for entry in reversed(full_log):
        for key, display_name in agent_display_names.items():
            if key not in seen_agents and f"] {display_name.split()[0]}" in entry:
                seen_agents.add(key)
                final_critiques_lines.append(f"- **{display_name}**: {entry.split(': ', 1)[-1]}")
            # Also match by short name variants in the log
            agent_keywords = {
                "security": "Security",
                "backend": "Backend",
                "frontend": "Frontend",
                "architecture": "Architecture",
                "qa": "QA",
                "code_quality": "Code Quality",
            }
            if key not in seen_agents and agent_keywords.get(key, "") in entry:
                seen_agents.add(key)
                final_critiques_lines.append(f"- **{display_name}**: {entry.split(': ', 1)[-1]}")

    final_critiques_block = "\n".join(final_critiques_lines) if final_critiques_lines else "- No critiques recorded."

    # -----------------------------------------------------------------------
    # Compose the human message with all structured data blocks
    # -----------------------------------------------------------------------
    # -----------------------------------------------------------------------
    # Fix #4: Condense the history before building the human message.
    # _condense_history() trims the log to max 12 entries, each capped at
    # 120 chars, so the Doc Agent gets a tight timeline rather than a
    # potentially massive blob of verbose critiques or code snippets.
    # -----------------------------------------------------------------------
    condensed_history = _condense_history(full_log)
    requires_human_review = state.get("requires_human_review", False)

    human_content = (
        f"VERDICTS:\n{verdicts_table}\n\n"
        f"FINAL_CRITIQUES:\n{final_critiques_block}\n\n"
        f"HISTORY (condensed timeline):\n{condensed_history}\n\n"
        f"REQUIRES_HUMAN_REVIEW: {requires_human_review}\n\n"
        f"FINAL_CODE:\n{final_code}"
    )

    messages = [
        SystemMessage(content=DOC_AGENT_PROMPT),
        HumanMessage(content=human_content)
    ]

    report_md = ""
    for attempt in range(3):
        try:
            response = arch_llm.invoke(messages)
            report_md = response.content.strip()
            if report_md:
                break
            print(f"      (Attempt {attempt+1}) Doc Agent returned empty response. Retrying...")
            time.sleep(3)
        except Exception as e:
            print(f"      (Attempt {attempt+1}) Doc Agent error: {e}")
            time.sleep(3)

    if not report_md:
        report_md = "⚠️ Could not generate the report. The LLM returned empty responses after multiple attempts."

    try:
        with open("report.md", "w", encoding="utf-8") as f:
            f.write(report_md)
        print("   -> Success! report.md has been created.")
    except Exception as e:
        print(f"   -> Error saving file: {e}")

    return {"human_readable_summary": report_md}
```

## `/agents/old_prompts.py`
```python
SECURITY_AGENT_PROMPT = """
[ROLE] You are the Lead Security Architect for an enterprise DevOps pipeline.
Your only job is to identify critical vulnerabilities, hardcoded secrets, and authentication bypass risks.

[CONTEXT] You are reviewing a pull request. The code has already passed functional UAC checks.
You are not a developer; do not suggest feature additions. You are strictly a security gatekeeper.

[TOOL USE — MANDATORY FIRST STEP]
Before delivering your verdict, you MUST call the `search_codebase_context` tool at least once.
Use it to retrieve how similar security-sensitive patterns (e.g., authentication, secrets management,
DB connections, API key handling) are implemented elsewhere in this repository.
Compare the PR code against these established patterns to detect deviations.

Example queries to run:
- "how is authentication handled in middleware"
- "how are environment variables and secrets accessed"
- "database connection initialization pattern"

[CONSTRAINTS]
- You must be ruthless but precise. Only flag actual security risks.
- Do not flag code quality issues.
- Never write introductory or concluding text.
"""

BACKEND_ANALYST_AGENT_PROMPT = """
[ROLE] You are a Senior Backend Systems Analyst.
Your job is to identify functional logic flaws, efficiency bottlenecks, and API contract violations.

[TASK] Review the provided code for:
1. **Logic Flaws**: Does the business logic actually achieve the stated goal?
2. **Resource Management**: Are resources (memory, connections, I/O) handled correctly for this language?
3. **Language Idioms**: Is the code using the most efficient patterns for the detected language?


[CONSTRAINTS]
- You are an ANALYST. Do NOT rewrite the code.
- Provide clear, actionable critiques that a developer can follow.
- Do not write introductory or concluding text.
"""

DEVELOPMENT_AGENT_PROMPT = """
[ROLE] You are an expert Senior Backend Developer.
Your job is to write secure, clean, and functional code that resolves all critiques provided by the analyst agents.

[CONTEXT] You submitted a pull request, but the analysts (Backend, Security, QA, Architecture, etc.) rejected it.
You need to rewrite the code to fix the exact issues they found in the critique log.

[CONSTRAINTS]
- Implement proper fixes for every critique log entry.
- Return ONLY the raw source code in its original language. Do not use markdown formatting (no ``` syntax).
- Do not write any introductory or concluding text. Your entire response must be valid, executable code in the original language.
- FORBIDDEN: You must NEVER use placeholder comments like '# rest of code here', '# ... existing code ...', '# TODO', '# implement later', '// ...', or any other comment that omits or truncates actual logic. Every function and method MUST be fully implemented with real, working code.
"""

DOC_AGENT_PROMPT = """
[ROLE] You are a Technical Documentation Specialist.
Your job is to summarize a multi-agent DevOps code review and negotiation process.

[INPUT] You will receive a compiled log of critiques from various specialist agents (Security, Architecture, Code Quality, Backend, QA) and the final approved version of the code.

[TASK] Create a comprehensive Markdown report that includes:
1. **Review Cycle Summary**: A high-level overview of the collaboration between agents and the developer to reach consensus.
2. **Step-by-Step Iteration Flow**: For EACH entry in the critique log, describe:
   - The issue identified by the specific specialist agent (e.g., Security, Architecture, Backend, QA).
   - The technical impact or risk of that issue.
   - How the Development Agent addressed that specific feedback in the next code revision.
3. **Key Improvements & Hardening**: A summarized list of the technical debt, security vulnerabilities, or architectural flaws that were resolved.
4. **Final Validated Code**: The final, optimized version of the code that achieved consensus from all agents.

[FORMAT] Use clear, professional headings, bold text for emphasis, and organized bullet points. Output ONLY the markdown content.
"""

CODE_QUALITY_AGENT_PROMPT = """
[ROLE] Senior Code Quality Engineer.
[OBJECTIVE] Evaluate code strictly for readability, maintainability, and idiomatic correctness.

[CRITERIA]
1. Naming: Descriptive, language-appropriate casing (e.g., snake_case for Python, camelCase for Go).
2. Modularity: Adherence to Single Responsibility Principle; no "God functions."
3. Complexity: Max nesting depth, cognitive load, and logical flow.
4. Documentation: Meaningful docstrings and inline comments for non-obvious logic.

[STRICT OUTPUT FORMAT]
- Output ONLY a bulleted list of specific technical critiques.
- DO NOT provide an introduction ("Here is my review...").
- DO NOT provide a summary or sign-off ("Overall, it looks good...").
- If no issues are found, output: "No quality issues detected."
- Keep each point under 20 words.
"""

ARCHITECTURE_AGENT_PROMPT = """
[ROLE] You are an Expert Software Architect.
Your job is to ensure the code follows structural design patterns and maintains clean system boundaries.

[TOOL USE — MANDATORY FIRST STEP]
Before delivering your verdict, you MUST call the `search_codebase_context` tool at least once.
Use it to understand the existing architectural conventions in this repository — how modules are structured,
how services communicate, and what design patterns are already in use.
Your review must assess whether the PR code is CONSISTENT with these conventions.

Example queries to run:
- "main service initialization and dependency injection pattern"
- "how are HTTP handlers and routes structured"
- "interface and abstraction layer patterns"

[TASK] Review the provided code for design patterns, coupling, scalability, interface integrity, and convention consistency.

[CONSTRAINTS]
- Focus only on high-level structural and architectural integrity.
- Do not flag security bugs or simple linting/formatting issues.
"""

QA_AGENT_PROMPT = """
[ROLE] You are a Senior SDET (Software Development Engineer in Test).
Your job is to ensure the code is testable and robust against edge cases.

[TASK] Review the provided code for:
1. **Testability**: Is the logic easy to unit test? Are dependencies injectable?
2. **Edge Case Handling**: Does the code handle null inputs, empty strings, or invalid data types gracefully?
3. **Mocking**: Are external calls (DB, API) properly abstracted so they can be mocked in a test environment?
4. **Validation**: Is there sufficient input validation to prevent runtime crashes?

[CONSTRAINTS]
- Focus strictly on reliability, testability, and edge cases.
- Do not suggest security or architectural changes.
"""

FRONTEND_AGENT_PROMPT = """
[ROLE] You are a Senior Frontend Integration Engineer.
Your job is to validate that backend code correctly serves the frontend's needs by checking API contracts, response schemas, and data formatting.

[TASK] Review the provided code for:
1. **API Field Completeness**: Does the API response include ALL fields a frontend client would need? Check for missing fields like `id`, `status`, `created_at`, `error_message`, etc.
2. **Data Format Consistency**: Are dates, enums, IDs, and monetary values returned in a consistent, frontend-friendly format? (e.g., ISO 8601 for dates, string enums instead of magic numbers)
3. **Error Response Structure**: Does the API return structured error objects (e.g., `{"error": {"code": 400, "message": "..."}}`) rather than plain strings or unstructured messages?
4. **Null/Empty Handling**: Are nullable fields explicitly set to `null` rather than omitted? Does the API distinguish between "empty list" (`[]`) and "not loaded" (`null`)?
5. **HTTP Status Codes**: Are proper status codes used (e.g., 404 for not found, 422 for validation errors) instead of generic 200/500?

[CONSTRAINTS]
- Focus ONLY on API contract and frontend integration issues.
- Do NOT flag internal implementation details, security, or architecture.
- If the code is purely frontend (React, Vue, etc.), check that it handles all API response states: loading, success, empty, and error.
- Keep each critique under 25 words.
"""
```

## `/agents/prompts.py`
```python
# =============================================================================
# MULTI-AGENT PROMPT SYSTEM — PRODUCTION GRADE
# Target LLM: Claude (claude-sonnet-4-20250514)
# Version: 3.0
# Description: Complete prompt definitions for a DevOps PR review pipeline
#              with 8 specialized agents. Drop-in ready.
# =============================================================================
# AGENT PIPELINE ORDER:
#   1. SECURITY      → finds vulnerabilities
#   2. BACKEND       → finds logic flaws & efficiency issues
#   3. FRONTEND      → validates API contracts & response schemas
#   4. ARCHITECT     → checks structural design
#   5. QA            → checks testability & edge cases
#   6. QUALITY       → checks code style & readability
#   7. DEVELOPER     → fixes all flagged issues
#   8. DOCS          → produces final Markdown report
#
# CRITIQUE LOG FORMAT (enforced across all review agents):
#   - Max 5 lines total
#   - Max 10 words per line
#   - No filler words
#   - Format: [TAG] file:line — finding
# =============================================================================


# 1. SECURITY ARCHITECT AGENT
# -----------------------------------------------------------------------------
# PURPOSE  : Detect vulnerabilities, hardcoded secrets, and auth bypass risks.
# TRIGGERS : Call after each developer revision.
# TOOL REQ : Must call `search_codebase_context` before verdict.
# OUTPUT   : APPROVE or REJECT + critique log.

SECURITY_AGENT_PROMPT = """
<role>
You are the Lead Security Architect for an enterprise DevOps pipeline.
Scope: vulnerabilities, hardcoded secrets, auth bypass, injection risks only.
You are a gatekeeper — not a developer. Do not suggest features or refactors.
</role>

<tool_use>
MANDATORY FIRST STEP — call `search_codebase_context` before any verdict.
Run all three queries below. Compare PR code against existing repo patterns.

Queries:
  1. "authentication middleware pattern"
  2. "secrets and environment variable access"
  3. "database connection initialization"

Flag any deviation from established patterns that introduces a security risk.
</tool_use>

<review_checklist>
Check for:
  - Hardcoded credentials, tokens, API keys, passwords
  - Missing or bypassable authentication / authorization
  - SQL injection, command injection, path traversal
  - Secrets not sourced from environment variables or a vault
  - Insecure defaults (debug=True, weak ciphers, no TLS)
  - Missing input sanitization on untrusted data
  - Improper error handling exposing stack traces or secrets
  - Insecure deserialization or unsafe eval usage
</review_checklist>

<output_rules>
Verdict line: APPROVE or REJECT — one word, first line.

Critique log (REJECT only):
  - Max 5 lines. Max 10 words per line. Zero filler words.
  - Format: [SEVERITY] file:line — finding
  - Severities: CRITICAL | HIGH | MEDIUM

No intro text. No closing text. No explanations beyond the log.
</output_rules>

<behavior>
- Be ruthless but precise. Only flag confirmed, exploitable risks.
- One finding per line. Prioritize CRITICAL first.
</behavior>
"""


# 2. BACKEND ANALYST AGENT
# -----------------------------------------------------------------------------
# PURPOSE  : Identify functional logic flaws, efficiency bottlenecks, API contract violations.
# TRIGGERS : Call in parallel with SECURITY agent (Phase 1).
# OUTPUT   : APPROVE or REJECT + critique log.

BACKEND_ANALYST_AGENT_PROMPT = """
<role>
You are a Senior Backend Systems Analyst reviewing a pull request.
Scope: functional logic flaws, resource management, efficiency bottlenecks, API contract violations.
You are an analyst — do NOT rewrite code or suggest features.
CRITICAL: Do NOT flag security issues (e.g., hardcoded secrets, weak hashes, SQL injection). The Security Agent owns this completely. Ensure you STRICTLY analyse only functional logic and efficiency.
</role>

<uac_gate>
If a User Acceptance Criteria (UAC) block is provided at the start of the message:
  - Your PRIMARY check is: does this code implement what the UAC specifies?
  - If the code implements a DIFFERENT feature than what the UAC describes, REJECT immediately.
  - A feature mismatch is classified as [CRITICAL] regardless of code quality.
  - Format: [CRITICAL] — UAC mismatch: code implements X, UAC requires Y
If no UAC block is present, skip this gate and proceed to the review checklist.
</uac_gate>

<review_checklist>
Check for:
  - Logic flaws — does business logic achieve the stated goal?
  - Incorrect resource handling: memory leaks, unclosed connections, I/O misuse
  - Inefficient patterns — wrong language idioms for detected language
  - Missing or broken API contract — wrong status codes, field mismatches
  - Incorrect error propagation — swallowed exceptions, wrong return types
  - Redundant computation or N+1 query patterns in loops
  - Race conditions or unsafe shared state in concurrent paths
  - Blocking I/O on hot paths without async or offloading
</review_checklist>

<output_rules>
Verdict line: APPROVE or REJECT — one word, first line.

Critique log (REJECT only):
  - Max 5 lines. Max 10 words per line. Zero filler words.
  - Format: [SEVERITY] file:line — finding
  - Severities: CRITICAL | HIGH | MEDIUM

No intro text. No closing text. Actionable critiques only.
</output_rules>

<behavior>
- Flag only issues that cause incorrect behavior or measurable resource misuse.
- If APPROVE: output only "APPROVE" with no other text.
</behavior>
"""


# 3. FRONTEND INTEGRATION AGENT
# -----------------------------------------------------------------------------
# PURPOSE  : Validate backend API contracts, response schemas, and data formatting.
# TRIGGERS : Call in parallel with SECURITY and BACKEND agents (Phase 1).
# OUTPUT   : APPROVE or REJECT + critique log.

FRONTEND_AGENT_PROMPT = """
<role>
You are a Senior Frontend Integration Engineer reviewing a pull request.
Scope: API contracts, response schemas, HTTP status codes, data formatting only.
Do not flag internal implementation details, security, or architecture.
</role>

<review_checklist>
Check for:
  - Missing response fields a frontend client needs (id, status, created_at, error_message)
  - Inconsistent data formats — dates not ISO 8601, enums as magic numbers, IDs as wrong type
  - Unstructured error responses — must be {"error": {"code": N, "error_message": "..."}}
  - Nullable fields omitted instead of explicitly set to null
  - Empty list [] vs null not distinguished for "not loaded" vs "empty" states
  - Wrong HTTP status codes — 422 for validation, 404 for not found, not generic 200/500
  - Frontend response states not handled: loading, success, empty, error
  - Enum values returned as integers instead of descriptive strings
</review_checklist>

<output_rules>
Verdict line: APPROVE or REJECT — one word, first line.

Critique log (REJECT only):
  - Max 5 lines. Max 10 words per line. Zero filler words.
  - Format: [CATEGORY] file:line — finding
  - Categories: CONTRACT | FORMAT | STATUS | NULL_HANDLING | SCHEMA

No intro text. No closing text.
</output_rules>

<behavior>
- Flag only issues that would break or mislead a frontend consumer.
- If APPROVE: output only "APPROVE" with no other text.
</behavior>
"""


# 4. SOFTWARE ARCHITECT AGENT
# -----------------------------------------------------------------------------
# PURPOSE  : Ensure structural design consistency with the existing codebase.
# TRIGGERS : Call in parallel with SECURITY, BACKEND, FRONTEND agents (Phase 1).
# TOOL REQ : Must call `search_codebase_context` before verdict.
# OUTPUT   : APPROVE or REJECT + critique log.

ARCHITECT_AGENT_PROMPT = """
<role>
You are an Expert Software Architect reviewing a pull request.
Scope: design patterns, coupling, scalability, interface integrity, convention consistency.
Do not flag security bugs, linting issues, or code style.
</role>

<tool_use>
MANDATORY FIRST STEP — call `search_codebase_context` before any verdict.
Run all three queries. Assess PR consistency against repo conventions.

Queries:
  1. "service initialization and dependency injection pattern"
  2. "HTTP handler and route structure"
  3. "interface and abstraction layer patterns"
</tool_use>

<review_checklist>
Check for:
  - Violation of existing architectural patterns (layering, service boundaries)
  - Tight coupling — direct instantiation where injection is expected
  - Missing abstraction — business logic leaking into handlers or models
  - God objects / oversized classes with multiple responsibilities
  - Inconsistent module structure vs rest of repo
  - Circular dependencies or broken dependency direction
  - Scalability blockers — global state, singleton misuse, blocking I/O in hot paths
  - Missing or broken interface contracts (ABC violations, protocol mismatches)
</review_checklist>

<output_rules>
Verdict line: APPROVE or REJECT — one word, first line.

Critique log (REJECT only):
  - Max 5 lines. Max 10 words per line. Zero filler words.
  - Format: [SEVERITY] file:line — finding
  - Severities: BLOCKER | MAJOR | MINOR

No intro text. No closing text.
</output_rules>

<behavior>
- Only flag structural issues that would break maintainability or scalability at scale.
- If APPROVE: output only "APPROVE" with no other text.
</behavior>
"""


# 5. QA / SDET AGENT
# -----------------------------------------------------------------------------
# PURPOSE  : Ensure code is testable, validated, and handles edge cases.
# TRIGGERS : Call in parallel with ARCHITECT agent (Phase 1).
# OUTPUT   : APPROVE or REJECT + critique log.
QA_AGENT_PROMPT = """
<role>
You are a Senior SDET (Software Development Engineer in Test).
Scope: test coverage adequacy, testability, edge case handling, mockability, input validation.
Do not flag security issues or architectural patterns — other agents own those.
</role>

<uac_gate>
If a User Acceptance Criteria (UAC) block is provided at the start of the message:
  - Check that the test suite contains at least one test case for EACH UAC scenario.
  - If any UAC acceptance scenario has no corresponding test, REJECT immediately.
  - Format: [UAC] missing test for: [scenario name from UAC]
  - This check takes priority over the coverage gate below.
If no UAC block is present, skip this gate and proceed to the coverage gate.
</uac_gate>

<test_coverage_gate>
You will receive TWO code blocks:
  1. SOURCE CODE — the production implementation (e.g., login.go)
  2. TEST CODE   — the unit test file (e.g., login_test.go)

Your PRIMARY job is to estimate the unit test coverage percentage by:
  - Counting the distinct logical branches in the SOURCE CODE
    (each if/else branch, each return path, each error case = 1 branch).
  - Counting how many of those branches have at least one test case in the TEST CODE.
  - Estimated coverage = (covered branches / total branches) × 100

Coverage Gate (STRICT — no exceptions):
  - coverage < 70%  → REJECT  (reason: COVERAGE_LOW)
  - coverage > 80%  → REJECT  (reason: COVERAGE_HIGH — over-tested / gold-plating)
  - 70% ≤ coverage ≤ 80% → APPROVE

Show your branch count reasoning in the critique field so it is auditable.
</test_coverage_gate>

<review_checklist>
Also check for:
  - Untestable functions — no dependency injection, hidden global state
  - External calls (DB, HTTP, file I/O) not abstracted behind an interface
  - Missing null / empty / boundary input handling in tests
  - No guard against invalid types or malformed payloads
  - Functions doing too much to be unit-tested in isolation
  - Non-deterministic logic (random, time, env) not injectable for tests
</review_checklist>

<output_rules>
Verdict line: APPROVE or REJECT — one word, first line.

Critique log (REJECT only):
  - Line 1: [COVERAGE] estimated X% — reason (LOW, HIGH, or OK)
  - Line 2-5: Max 10 words per line. Zero filler words.
  - Format: [CATEGORY] file:line — finding
  - Categories: COVERAGE | TESTABILITY | EDGE_CASE | MOCK | VALIDATION | UAC

No intro text. No closing text.
</output_rules>

<behavior>
- If coverage is within 70–80%: output only "APPROVE" with no other text.
- If outside the gate: REJECT and clearly state the estimated coverage % and direction.
- Be precise. Count branches, do not guess.
</behavior>
"""



# 6. CODE QUALITY AGENT
# -----------------------------------------------------------------------------
# PURPOSE  : Enforce clean, readable, maintainable Python (PEP 8 + clean code).
# TRIGGERS : Call last — after all Phase 1 agents approve.
# OUTPUT   : APPROVE or REJECT + critique log.

CODE_QUALITY_AGENT_PROMPT = """
<role>
You are a Senior Python Code Quality Engineer.
Scope: naming conventions, modularization, complexity, documentation.
Ignore security flaws and architecture — other agents own those.
</role>

<review_checklist>
Check for:
  - Non-descriptive names (x, tmp, data, flag, val)
  - Non-snake_case variables or functions
  - Functions longer than 20 lines without strong justification
  - Nesting deeper than 3 levels
  - Missing docstrings on public functions, classes, and modules
  - Inline comments stating the obvious instead of explaining why
  - Repeated logic that should be a shared helper
  - Magic numbers / strings — should be named constants
  - Boolean parameters that require reading the function body to understand
  - Unused imports or dead code left in
</review_checklist>

<output_rules>
Verdict line: APPROVE or REJECT — one word, first line.

Critique log (REJECT only):
  - Max 5 lines. Max 10 words per line. Zero filler words.
  - Format: [CATEGORY] file:line — finding
  - Categories: NAMING | STRUCTURE | COMPLEXITY | DOCS | DEAD_CODE

No intro text. No closing text.
</output_rules>

<behavior>
- Flag only issues that meaningfully hurt long-term maintainability.
- If APPROVE: output only "APPROVE" with no other text.
</behavior>
"""


# 7. SENIOR DEVELOPER AGENT
# -----------------------------------------------------------------------------
# PURPOSE  : Fix ALL flagged issues from every specialist agent that rejected.
# TRIGGERS : Call after any REJECT from Security, Backend, Frontend, Architect, QA, or Quality.
# INPUT    : Original code + combined critique log from all rejecting agents.
# OUTPUT   : Raw Python only. No markdown. No commentary.

# DEV_AGENT_PROMPT = """
# <role>
# You are an Expert Senior Backend Developer.
# Your PR was rejected by one or more specialist agents (Security, Backend, Frontend, Architect, QA, Quality).
# Fix every issue in the critique log. Make no other changes.
# </role>

# <fix_guidelines>
# Security fixes:
#   - Passwords       → bcrypt or argon2 hash; never store plaintext
#   - Secrets         → os.environ.get() or secrets manager; never hardcode
#   - DB queries      → parameterized queries only; no string concatenation
#   - Auth checks     → validate on every protected route; no bypasses
#   - Error messages  → generic to caller; log detail server-side only
#   - Input           → validate and sanitize all untrusted data at entry point
#   - Deserialization → use safe parsers; never eval() or pickle untrusted input
#   - TLS/defaults    → enforce TLS; set secure=True; disable debug in production

# Backend fixes:
#   - Logic flaws     → fix business logic to match stated goal exactly
#   - Resources       → close connections, files, and streams in finally or context managers
#   - Efficiency      → replace N+1 patterns; use batch queries or caching where flagged
#   - API contracts   → return correct status codes and field names per spec

# Frontend/API fixes:
#   - Response schema → include all required fields (id, status, created_at, error_message)
#   - Error format    → return {"error": {"code": N, "error_message": "..."}} always
#   - Null handling   → explicitly set nullable fields to null; never omit them
#   - Status codes    → 404 not found, 422 validation, 400 bad request; no generic 200/500

# Architecture fixes:
#   - Coupling        → inject dependencies; do not instantiate services directly
#   - SRP             → split God objects into focused, single-responsibility classes
#   - Abstraction     → move business logic out of handlers and models

# QA fixes:
#   - Testability     → inject external dependencies (DB, HTTP, time) via parameters
#   - Edge cases      → add null, empty, and boundary checks at function entry
#   - Mocking         → abstract all external calls behind an interface or callable

# Quality fixes:
#   - Naming          → replace vague names with descriptive snake_case identifiers
#   - Docstrings      → add to all public functions, classes, and modules
#   - Complexity      → extract deeply nested blocks into named helper functions
#   - Dead code       → remove unused imports and unreachable logic
# </fix_guidelines>

# <constraints>
# - Implement a real, complete fix for every line in the critique log.
# - Do not add features, refactor unrelated code, or change function signatures.
# - Return raw source code in its original language only.
# - No markdown fences. No explanatory comments about the fix. No preamble or closing text.
# - FORBIDDEN: Never use placeholder comments like "# rest of code here",
#   "# ... existing code ...", "# TODO", "# implement later", or "// ...".
#   Every function must be fully implemented with real, working code.
# - Your entire response must be valid, executable code.
# </constraints>

# <input_format>
# You will receive:
#   CRITIQUE LOG: [combined output from all rejecting agents]
#   ORIGINAL CODE: [code block]
# </input_format>
# """

DEV_AGENT_PROMPT = """
[ROLE] You are an expert Senior Backend Developer.
Your job is to write secure, clean, and functional code that resolves all critiques provided by the analyst agents.

[CONTEXT] You submitted a pull request containing MULTIPLE files, but the analysts rejected it. 
You need to rewrite the specific files that need fixes based on the critique log.

[INSTRUCTIONS]
You MUST follow a 2-step process to ensure all critiques are fixed.
STEP 1: Write a brief checklist explaining how you are fixing EACH issue in the critique log. Format this as a list starting underneath "CHECKLIST:"
STEP 2: Output the complete, fixed source code for EVERY file you modify. 
You MUST demarcate each file using the exact format:
[FILE: path/to/file.go]
```go
<entire new file content>
```
(Repeat for every file you need to modify).
DO NOT output files that do not need changes.

[CONSTRAINTS]
- Implement proper fixes for every critique log entry.
- The ONLY text before the code blocks should be your checklist. No introductory preamble.
- FORBIDDEN: You must NEVER use placeholder comments like '# rest of code here', '# ... existing code ...', '# TODO', '# implement later', '// ...'. Every function and method MUST be fully implemented with real, working code.
"""

# 8. DOCUMENTATION AGENT
# -----------------------------------------------------------------------------
# PURPOSE  : Generate the final Markdown review report.
# TRIGGERS : Call once all agents APPROVE and final code is confirmed.
# INPUT    : Full critique log history from all agents + final approved code.
# OUTPUT   : Markdown report only. No preamble. No closing text.

DOC_AGENT_PROMPT = """
<role>
You are a Technical Documentation Specialist.
You will receive structured data blocks: VERDICTS, FINAL_CRITIQUES, HISTORY, REQUIRES_HUMAN_REVIEW, and FINAL_CODE.
Your job is to write a polished Markdown PR review report using that data.
</role>

<output_format>
# PR Review Report

## Summary
[2-3 sentences: what was reviewed, how many agents, how many iterations, overall outcome SUCCESS or FAILED]

## Agent Pipeline Results
[COPY the VERDICTS block verbatim as a Markdown table. Do NOT change any APPROVE/REJECT values.]

## Iteration Log
### Summary of Revisions
[Write 1-2 paragraphs summarizing the key blockers and how the developer tried to fix them. Be concise.]

## Key Improvements & Hardening
| Category | Issue | Fix |
|---|---|---|
| CRITICAL | [finding] | [resolution] |
| HIGH | [finding] | [resolution] |

## Final Code Output
```go
[paste FINAL_CODE here]
```

## Sign-Off
[If REQUIRES_HUMAN_REVIEW is True: write "⚠️ Pipeline failed to converge after maximum iterations. A Senior Developer must review this PR manually before merging."]
[If REQUIRES_HUMAN_REVIEW is False and ALL verdicts are APPROVE: write "✅ All agents approved. Safe to merge."]
[If REQUIRES_HUMAN_REVIEW is False and ANY verdict is REJECT: write "❌ Pipeline failed to converge. Manual review required."]

### Final Agent Verdicts & Reasons
[COPY the FINAL_CRITIQUES block verbatim. One bullet per agent.]
</output_format>

<constraints>
- Output Markdown only. No preamble or extra text outside the format.
- NEVER change any APPROVE/REJECT values — they are computed facts, not your opinion.
- Code block must use ```go fencing.
- Summarize iteration history in short paragraphs only. Do not list every critique.
- REQUIRES_HUMAN_REVIEW is a boolean flag from the pipeline state. Reflect it accurately in the Sign-Off.
</constraints>
"""


# =============================================================================
# SHARED SYSTEM CONTEXT — prepend to every agent call
# =============================================================================
# Inject this as the first message in every API call to ground all agents.
# Replace {PR_DIFF}, {REPO_LANGUAGE}, {FRAMEWORK} at runtime.
# =============================================================================

SHARED_SYSTEM_CONTEXT = """
<pipeline_context>
  Environment  : Enterprise DevOps PR Review Pipeline
  LLM          : Claude (claude-sonnet-4-20250514)
  Repo language: {REPO_LANGUAGE}
  Framework    : {FRAMEWORK}
  PR diff      : {PR_DIFF}
</pipeline_context>

<global_rules>
  - You are one specialized agent in a multi-agent pipeline.
  - Stay strictly within your defined scope. Do not bleed into other agents' domains.
  - Never hallucinate file paths, line numbers, or function names not present in the PR.
  - If the PR diff is empty or unparseable, output: INPUT_ERROR — unparseable diff.
  - Always ground findings in specific file:line references from the PR diff.
  - Treat all code as untrusted until proven otherwise.
</global_rules>

<critique_log_format>
  Max 5 lines. Max 10 words per line. Zero filler words.
  Each line: [TAG] file:line — finding
</critique_log_format>
"""


# =============================================================================
# PIPELINE ORCHESTRATION GUIDE
# =============================================================================
#
# Recommended call order and parallelism:
#
#   PHASE 1 — Parallel review (all 4 at once):
#     → SECURITY_AGENT_PROMPT
#     → BACKEND_ANALYST_AGENT_PROMPT
#     → FRONTEND_AGENT_PROMPT
#     → ARCHITECT_AGENT_PROMPT
#     → QA_AGENT_PROMPT
#
#   PHASE 2 — Fix loop (repeat until all Phase 1 agents approve):
#     → DEV_AGENT_PROMPT  (triggered on any REJECT; receives combined critique log)
#     → Re-run all Phase 1 agents on the revised code
#     → Max recommended iterations: 3
#
#   PHASE 3 — Quality gate (after all Phase 1 agents APPROVE):
#     → CODE_QUALITY_AGENT_PROMPT
#     → DEV_AGENT_PROMPT if REJECT (max 2 iterations)
#
#   PHASE 4 — Report (after all agents APPROVE):
#     → DOC_AGENT_PROMPT
#
# API call structure:
#   messages = [
#     {"role": "user", "content": SHARED_SYSTEM_CONTEXT + "\n" + <AGENT_PROMPT> + "\n" + pr_code}
#   ]
#
# Recommended Claude API params:
#   model       : "claude-sonnet-4-20250514"
#   max_tokens  : 1024  (all review agents) | 4096 (dev + doc agents)
#   temperature : 0.1   (low — deterministic security and quality checks)
#
# =============================================================================
```

## `/agents/schemas.py`
```python
from pydantic import BaseModel, Field

class SpecialistReview(BaseModel):
    vote: str = Field(description="Must be exactly 'approved' or 'rejected'")
    critique: str = Field(description="If rejected, provide the technical reason. If approved, leave empty.")
    line_numbers: list[int] | None = Field(default=None, description="The specific lines of code causing the issue.")
```

## `/agents/tools.py`
```python
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
        A short summary of the single most relevant code block found.
    """
    results = search(query=search_query, repo_name=repo_name, n_results=1)

    if not results:
        return (
            f"No relevant code found in repository '{repo_name}' "
            f"for query: '{search_query}'."
        )

    # Truncate to 500 chars max to keep token usage minimal
    snippet = results[0][:500]
    return f"[Context for '{search_query}']:\n{snippet}"

```

## `/api/main.py`
```python
"""
api/main.py

FastAPI webhook endpoint for GitHub PR events.

Responsibilities:
1. Verify the GitHub HMAC-SHA256 signature on every request.
2. On PR *open/synchronize*: dispatch the LangGraph AI review pipeline via Celery.
3. On PR *merged*: perform incremental vector store sync —
      a. Fetch the list of files changed in the PR from GitHub API.
      b. Delete stale vectors for each changed file.
      c. Fetch new file contents and re-ingest into ChromaDB.

Environment variables (in .env):
    GITHUB_WEBHOOK_SECRET  — used to verify the GitHub signature
    GITHUB_TOKEN           — Personal Access Token for GitHub API calls
"""

import hmac
import hashlib
import os

import httpx
from fastapi import FastAPI, status, Request, HTTPException, Depends
from dotenv import load_dotenv

from api.models import WebhookPayload
from worker.celery_app import process_pull_request_task

load_dotenv()

app = FastAPI(title="10-Agent DevOps Pipeline")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_github_headers() -> dict:
    token = os.getenv("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ---------------------------------------------------------------------------
# Security: Verify GitHub Webhook Signature
# ---------------------------------------------------------------------------

async def verify_github_signature(request: Request):
    """Verifies the HMAC-SHA256 signature sent by GitHub."""
    secret_str = os.getenv("GITHUB_WEBHOOK_SECRET", "my_super_secret_key")
    secret = secret_str.encode()

    github_signature = request.headers.get("x-hub-signature-256")
    if not github_signature:
        raise HTTPException(status_code=401, detail="Missing signature header")

    body = await request.body()

    mac = hmac.new(secret, msg=body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + mac.hexdigest()

    if not hmac.compare_digest(expected_signature, github_signature):
        raise HTTPException(status_code=401, detail="Signatures do not match")


# ---------------------------------------------------------------------------
# Incremental Vector Store Sync (called on PR merge)
# ---------------------------------------------------------------------------

async def _sync_vector_store_on_merge(payload: WebhookPayload) -> None:
    """
    When a PR is merged:
      1. Fetch the list of modified files from GitHub Files API.
      2. Delete stale vectors for each modified file.
      3. Fetch new file contents from GitHub raw API.
      4. Re-ingest fresh vectors into ChromaDB.

    This keeps the vector store in sync with the main branch.
    """
    # Late imports to avoid loading ChromaDB/sentence-transformers at startup
    # (they take a few seconds for the model download on first run)
    from context_engine.chunking_engine import chunk_file
    from context_engine.vector_store import add_chunks, delete_by_file
    import tempfile
    import os as _os

    repo_full_name = payload.repository.full_name   # e.g. "your-org/backend_pandhi"
    repo_name      = payload.repository.name         # e.g. "backend_pandhi"
    pr_number      = payload.number
    head_sha       = payload.pull_request.head.sha

    print(f"[webhook] Incremental sync triggered for PR #{pr_number} in '{repo_full_name}'")

    github_api_base = f"https://api.github.com/repos/{repo_full_name}"
    headers = _get_github_headers()

    async with httpx.AsyncClient(timeout=30.0) as client:
        # ------------------------------------------------------------------ #
        # Step 1: Get the list of files changed in this PR
        # ------------------------------------------------------------------ #
        files_url = f"{github_api_base}/pulls/{pr_number}/files"
        resp = await client.get(files_url, headers=headers)

        if resp.status_code != 200:
            print(f"[webhook] Could not fetch PR files: {resp.status_code} — {resp.text[:200]}")
            return

        changed_files = resp.json()   # list of {filename, status, raw_url, ...}

        print(f"[webhook] {len(changed_files)} file(s) changed in PR #{pr_number}")

        for file_info in changed_files:
            file_path  = file_info.get("filename", "")
            file_status = file_info.get("status", "")   # added | modified | removed | renamed

            # ---------------------------------------------------------------- #
            # Step 2: Delete stale vectors for this file
            # ---------------------------------------------------------------- #
            deleted = delete_by_file(file_path=file_path, repo_name=repo_name)
            print(f"[webhook]   Deleted {deleted} stale vectors for '{file_path}'")

            # If the file was removed, nothing more to do
            if file_status == "removed":
                continue

            # ---------------------------------------------------------------- #
            # Step 3: Fetch new content from GitHub raw API
            # ---------------------------------------------------------------- #
            raw_url = file_info.get("raw_url", "")
            if not raw_url:
                # Fallback: construct raw URL from head SHA
                raw_url = f"https://raw.githubusercontent.com/{repo_full_name}/{head_sha}/{file_path}"

            raw_resp = await client.get(raw_url, headers=headers)
            if raw_resp.status_code != 200:
                print(f"[webhook]   Could not fetch raw content for '{file_path}': {raw_resp.status_code}")
                continue

            # ---------------------------------------------------------------- #
            # Step 4: Write to a temp file, chunk it, re-ingest
            # ---------------------------------------------------------------- #
            suffix = "." + file_path.rsplit(".", 1)[-1] if "." in file_path else ""
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode="wb") as tmp:
                tmp.write(raw_resp.content)
                tmp_path = tmp.name

            try:
                chunks = chunk_file(file_path=tmp_path, repo_name=repo_name)
                # Restore original file_path in metadata (not the temp path)
                for chunk in chunks:
                    chunk["metadata"]["file_path"] = file_path
                count = add_chunks(chunks)
                print(f"[webhook]   Re-ingested {count} chunks for '{file_path}'")
            finally:
                _os.unlink(tmp_path)   # clean up temp file

    print(f"[webhook] Incremental sync complete for PR #{pr_number}.")


# ---------------------------------------------------------------------------
# Webhook Endpoint
# ---------------------------------------------------------------------------

@app.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(
    payload: WebhookPayload,
    request: Request,
    _=Depends(verify_github_signature)
):
    """
    Main webhook handler.

    - PR opened / synchronized  →  dispatch AI review via Celery
    - PR closed + merged        →  incremental vector store sync, then dispatch
    """
    pr     = payload.pull_request
    action = payload.action

    print(f"[webhook] Received event: action='{action}' PR #{payload.number}: '{pr.title}'")

    # --- Merged PR: sync vector store first ---
    if action == "closed" and pr.merged:
        print(f"[webhook] PR #{payload.number} was MERGED — starting incremental vector store sync.")
        await _sync_vector_store_on_merge(payload)

    # --- Dispatch AI review for new/updated/merged PRs ---
    if action in ("opened", "synchronize", "reopened") or (action == "closed" and pr.merged):
        process_pull_request_task.delay(payload.model_dump())
        return {"message": f"Webhook received. PR #{payload.number} queued for AI review."}

    # --- Any other action (assigned, labeled, etc.) — acknowledge but skip ---
    return {"message": f"Event '{action}' acknowledged. No action taken."}
```

## `/api/models.py`
```python
"""
api/models.py

Pydantic models for the GitHub webhook payload.
Extended to capture merge status, repository identity, and head SHA
required by the incremental vector store sync on PR merge.
"""

from pydantic import BaseModel


class HeadCommit(BaseModel):
    sha: str = ""


class Repository(BaseModel):
    full_name: str          # e.g. "your-org/backend_pandhi"
    name: str               # e.g. "backend_pandhi"


class PullRequest(BaseModel):
    html_url: str
    title: str
    body: str | None = None
    merged: bool = False
    head: HeadCommit = HeadCommit()
    base: HeadCommit = HeadCommit()


class WebhookPayload(BaseModel):
    action: str
    number: int
    pull_request: PullRequest
    repository: Repository = Repository(full_name="unknown/unknown", name="unknown")
```

## `/context_engine/chunking_engine.py`
```python
"""
context_engine/chunking_engine.py

Chunking Engine: reads source files, parses them into an AST with Tree-sitter,
extracts meaningful top-level code blocks (functions, classes, methods, types),
and returns structured chunks ready for embedding.

Usage:
    from context_engine.chunking_engine import chunk_file

    chunks = chunk_file("src/main.go", repo_name="backend_pandhi")
    # chunks -> list of {text: str, metadata: {...}, id: str}
"""

import hashlib
from pathlib import Path

from tree_sitter import Query, QueryCursor

from context_engine.parser_router import get_parser, get_language_name

# ---------------------------------------------------------------------------
# S-expression queries per language family.
# In tree-sitter 0.25+, each pattern in a query is independent.
# We list them as separate one-per-line entries for clarity.
# ---------------------------------------------------------------------------
# Each entry: list of (s_expression, capture_name) tuples
_QUERY_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "python": [
        ("(function_definition) @function", "function"),
        ("(class_definition) @class",       "class"),
    ],
    "go": [
        ("(function_declaration) @function",   "function"),
        ("(method_declaration) @method",        "method"),
        ("(type_declaration) @type",             "type"),
    ],
    "javascript": [
        ("(function_declaration) @function",     "function"),
        ("(lexical_declaration) @arrow_function", "arrow_function"),
        ("(class_declaration) @class",           "class"),
    ],
    "typescript": [
        ("(function_declaration) @function",      "function"),
        ("(lexical_declaration) @arrow_function",  "arrow_function"),
        ("(class_declaration) @class",            "class"),
        ("(interface_declaration) @interface",    "interface"),
        ("(type_alias_declaration) @type_alias",  "type_alias"),
    ],
}

# Extension → query language family
_EXT_TO_LANG_FAMILY: dict[str, str] = {
    ".py":  "python",
    ".go":  "go",
    ".js":  "javascript",
    ".jsx": "javascript",
    ".ts":  "typescript",
    ".tsx": "typescript",
}

# Minimum block size in characters — skip tiny/trivial nodes
_MIN_BLOCK_CHARS = 30


def _make_chunk_id(repo_name: str, file_path: str, start_byte: int) -> str:
    """Stable unique ID for a chunk based on position in file."""
    raw = f"{repo_name}::{file_path}::{start_byte}"
    return hashlib.md5(raw.encode()).hexdigest()


def chunk_file(file_path: str, repo_name: str) -> list[dict]:
    """
    Parse a source file and return a list of code-chunk dicts.

    Each dict has the shape:
        {
            "id":       str,       # stable MD5 hash of (repo, path, byte_offset)
            "text":     str,       # raw source text of the block
            "metadata": {
                "repo_name":  str,
                "file_path":  str,
                "language":   str,
                "block_type": str, # e.g. "function", "class", "method"
            }
        }

    Returns an empty list if the file is unsupported or unreadable.
    """
    path = Path(file_path)
    ext  = path.suffix.lower()

    # 1. Get parser & language family
    parser, language = get_parser(file_path)
    if parser is None:
        return []

    lang_family = _EXT_TO_LANG_FAMILY.get(ext)
    if lang_family is None:
        return []

    lang_name = get_language_name(file_path) or lang_family

    # 2. Read source bytes
    try:
        source_bytes = path.read_bytes()
    except (OSError, PermissionError) as exc:
        print(f"  [chunker] Could not read {file_path}: {exc}")
        return []

    # 3. Parse into AST
    tree = parser.parse(source_bytes)

    # 4. Build queries and run via QueryCursor (tree-sitter 0.25+ API)
    patterns = _QUERY_PATTERNS.get(lang_family, [])
    if not patterns:
        return []

    chunks: list[dict] = []
    seen_byte_offsets: set[int] = set()

    for s_expr, block_type in patterns:
        try:
            query = Query(language, s_expr)
        except Exception as exc:
            print(f"  [chunker] Query build error for '{block_type}' in {file_path}: {exc}")
            continue

        cursor = QueryCursor(query)
        for _pattern_index, captures_dict in cursor.matches(tree.root_node):
            # captures_dict: {capture_name: [Node, ...]}
            for cap_nodes in captures_dict.values():
                for node in cap_nodes:
                    text = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

                    if len(text.strip()) < _MIN_BLOCK_CHARS:
                        continue
                    if node.start_byte in seen_byte_offsets:
                        continue
                    seen_byte_offsets.add(node.start_byte)

                    chunk_id = _make_chunk_id(repo_name, str(file_path), node.start_byte)
                    chunks.append({
                        "id": chunk_id,
                        "text": text,
                        "metadata": {
                            "repo_name":  repo_name,
                            "file_path":  str(file_path),
                            "language":   lang_name,
                            "block_type": block_type,
                        }
                    })

    return chunks

```

## `/context_engine/parser_router.py`
```python
"""
context_engine/parser_router.py

Grammar Router: maps file extensions to the correct Tree-sitter parser + Language.
Supports Python, Go, JavaScript, TypeScript, and their variants.

Usage:
    from context_engine.parser_router import get_parser

    parser, language = get_parser("src/main.py")
    if parser is not None:
        tree = parser.parse(source_bytes)
"""

from pathlib import Path
from tree_sitter import Language, Parser

import tree_sitter_python as _tspy
import tree_sitter_go as _tsgo
import tree_sitter_javascript as _tsjs
import tree_sitter_typescript as _tsts

# ---------------------------------------------------------------------------
# Build Language objects once at module load (cheap, just wraps a pointer)
# ---------------------------------------------------------------------------
_LANGUAGES: dict[str, Language] = {
    ".py":  Language(_tspy.language()),
    ".go":  Language(_tsgo.language()),
    ".js":  Language(_tsjs.language()),
    ".jsx": Language(_tsjs.language()),
    ".ts":  Language(_tsts.language_typescript()),
    ".tsx": Language(_tsts.language_tsx()),
}

# Friendly names used in metadata
LANGUAGE_NAMES: dict[str, str] = {
    ".py":  "python",
    ".go":  "go",
    ".js":  "javascript",
    ".jsx": "javascript",
    ".ts":  "typescript",
    ".tsx": "typescript",
}


def get_parser(file_path: str) -> tuple[Parser | None, Language | None]:
    """
    Return an instantiated (Parser, Language) for the given file path.

    Returns (None, None) if the file extension is not supported.
    """
    ext = Path(file_path).suffix.lower()
    language = _LANGUAGES.get(ext)
    if language is None:
        return None, None
    return Parser(language), language


def get_language_name(file_path: str) -> str | None:
    """Return a human-readable language name for a file path, or None."""
    ext = Path(file_path).suffix.lower()
    return LANGUAGE_NAMES.get(ext)

```

## `/context_engine/vector_store.py`
```python
"""
context_engine/vector_store.py

ChromaDB Vector Store Wrapper using local sentence-transformers embeddings.
No API key required — completely offline via all-MiniLM-L6-v2.

Exposes three public functions used throughout the system:
    - add_chunks(chunks)             → bulk upsert
    - delete_by_file(file, repo)     → remove stale vectors on PR merge
    - search(query, repo, n)         → semantic similarity search
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

# Persistent client — data survives restarts in ./chroma_db/
_client = chromadb.PersistentClient(path=_CHROMA_PATH)

# Create or reuse the collection
_collection = _client.get_or_create_collection(
    name=_COLLECTION_NAME,
    embedding_function=_embedding_fn,
    metadata={"hnsw:space": "cosine"},   # cosine distance for semantic search
)

print(f"[vector_store] ChromaDB ready at: {_CHROMA_PATH}")
print(f"[vector_store] Collection '{_COLLECTION_NAME}' — {_collection.count()} vectors loaded.")


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

    Returns the number of deleted vectors (approximate — ChromaDB returns None on delete).
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

```

## `/context_engine/__init__.py`
```python
# context_engine package
# Provides multi-language AST parsing, semantic chunking, and vector store operations.

```

## `/graph/builder.py`
```python
from langgraph.graph import StateGraph, END
from graph.state import AgentState
from graph.edges import route_negotiation

from agents.nodes import (
    security_agent_node,
    backend_analyst_node,
    development_agent_node,
    documentation_summarizer_node,
    code_quality_agent_node,
    architecture_agent_node,
    qa_agent_node,
    frontend_agent_node
)

# -----------------------------
# Sandbox Node
# -----------------------------
def environment_sandbox_node(state: AgentState):
    print(" Deployment: Consensus reached! Deploying to sandbox.")
    return {}


# -----------------------------
# Human Fallback Node (Fix #3)
# -----------------------------
def human_fallback_node(state: AgentState):
    """
    Reached when the pipeline exhausts all 3 review iterations without
    reaching consensus. Stamps `requires_human_review: True` in state so
    that the webhook response / front-end dashboard can tag a Senior
    Developer to step in. Then falls through to the Doc Agent which will
    include the failure sign-off in its Markdown report.
    """
    print(" [FALLBACK] Iteration limit reached. Escalating to human reviewer.")
    print("   -> Setting requires_human_review = True in pipeline state.")
    return {"requires_human_review": True}


# -----------------------------
#  NEW: Consensus Node (FAN-IN)
# -----------------------------
def consensus_node(state: AgentState):
    """
    Fan-in point — collects all specialist votes.

    Fix #1 — Memory Wipe Bug:
        active_critiques are NO LONGER wiped here. The Developer Agent is
        the consumer of these critiques; it must read them BEFORE they are
        cleared. Wiping here caused the Dev Agent to receive an empty log
        on Round 2, creating an infinite failure loop.

        The wipe now happens inside development_agent_node, after it copies
        the critiques into the human message. full_history is still
        accumulated here so the Doc Agent has the complete journey.
    """
    votes = state.get("domain_approvals", {})
    print(f" Consensus Node: All agents finished.")
    print(f" Votes: {votes}")

    if any(vote == "rejected" for vote in votes.values()):
        current_critiques = state.get("active_critiques", [])
        print(f" → {len(current_critiques)} critiques archived to full_history. Preserved for Dev Agent.")
        return {
            "full_history": current_critiques,  # Append to long-term memory
            # ✅ active_critiques NOT wiped here — Dev Agent reads them first,
            #    then wipes them in its own return dict.
        }
    return {}


# -----------------------------
# Initialize Graph
# -----------------------------
workflow = StateGraph(AgentState)

# -----------------------------
# Add Nodes
# -----------------------------
workflow.add_node("development_agent_node", development_agent_node)
workflow.add_node("backend_analyst_node", backend_analyst_node)

workflow.add_node("security_agent_node", security_agent_node)
workflow.add_node("code_quality_agent_node", code_quality_agent_node)
workflow.add_node("architecture_agent_node", architecture_agent_node)
workflow.add_node("qa_agent_node", qa_agent_node)
workflow.add_node("frontend_agent_node", frontend_agent_node)

workflow.add_node("consensus_node", consensus_node)

workflow.add_node("human_fallback_node", human_fallback_node)
workflow.add_node("documentation_summarizer_node", documentation_summarizer_node)
workflow.add_node("environment_sandbox_node", environment_sandbox_node)

# -----------------------------
# Entry Point
# -----------------------------
workflow.set_entry_point("backend_analyst_node")

# -----------------------------
# Routing (ONLY from consensus)
# -----------------------------
workflow.add_conditional_edges("consensus_node", route_negotiation)
workflow.add_edge("development_agent_node", "backend_analyst_node")

# -----------------------------
# FAN-OUT handled by route_negotiation
# -----------------------------

# -----------------------------
# FAN-IN: All agents → consensus
# -----------------------------
workflow.add_edge("backend_analyst_node", "security_agent_node")
workflow.add_edge("security_agent_node", "code_quality_agent_node")
workflow.add_edge("code_quality_agent_node", "architecture_agent_node")
workflow.add_edge("architecture_agent_node", "qa_agent_node")
workflow.add_edge("qa_agent_node", "frontend_agent_node")
workflow.add_edge("frontend_agent_node", "consensus_node")

# -----------------------------
# Final Flow
# -----------------------------
workflow.add_edge("human_fallback_node", "documentation_summarizer_node")
workflow.add_edge("environment_sandbox_node", "documentation_summarizer_node")
workflow.add_edge("documentation_summarizer_node", END)

# -----------------------------
# Compile
# -----------------------------
app = workflow.compile()


# -----------------------------
# TESTING
# -----------------------------
if __name__ == "__main__":
    print("Starting the 10-Agent Pipeline Test...\n")

    initial_state = {
        "pr_url": "https://github.com/fake/repo/pull/1",
        "current_code": "def login():\n    password = 'super_secret_password'\n    return True",
        "iteration_count": 0,
        "ast_is_valid": False,
        "domain_approvals": {
            "security": "pending",
            "architecture": "pending",
            "code_quality": "pending",
            "qa": "pending",
            "frontend": "pending"
        }
    }

    for output in app.stream(initial_state):
        for key, value in output.items():
            print(f"Finished: {key}\n")
```

## `/graph/edges.py`
```python
from graph.state import AgentState

def route_negotiation(state: AgentState):

    # ── Iteration Limit (Fix #3) ──────────────────────────────────────────────
    # When 3 rounds pass without consensus, stamp the state as requiring human
    # review before routing to the Documentation Agent for the failure report.
    if state.get("iteration_count", 0) >= 3:
        return "human_fallback_node"

    # Syntactic Failure
    if not state["ast_is_valid"]:
        return "development_agent_node"

    # Consensus Reached
    if state.get("domain_approvals") and all(vote == "approved" for vote in state["domain_approvals"].values()):
        return "environment_sandbox_node"

    if state.get("domain_approvals") and any(vote == "rejected" for vote in state["domain_approvals"].values()):
        return "development_agent_node"

    # Fallback to development if approvals are somehow missing/invalid
    return "development_agent_node"
```

## `/graph/state.py`
```python
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
    current_files: dict[str, str]
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
```

## `/worker/celery_app.py`
```python
from celery import Celery

#  * Initialize our worker and connect  to the Redis 
celery_app = Celery(
    "devops_worker",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

# *  Define the job the worker needs to do
@celery_app.task  
def process_pull_request_task(payload_dict: dict):
    print(f"👷 Celery worker is now processing PR #{payload_dict.get('number')} in the background...")
    return "AI Processing Complete"
```

## `/scripts/bulk_ingest.py`
```python
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

```

## `/scripts/inspect_ts.py`
```python
"""Inspect QueryCursor in tree-sitter 0.25+."""
import tree_sitter_python as tspy
from tree_sitter import Language, Parser, Query, QueryCursor

lang = Language(tspy.language())
parser = Parser(lang)

src = b"def hello(x):\n    return x + 1\n\nclass Foo:\n    pass\n"
tree = parser.parse(src)

print("QueryCursor attrs:", [a for a in dir(QueryCursor) if not a.startswith("_")])

# Build Query using the new constructor (not lang.query())
q = Query(lang, "(function_definition) @func (class_definition) @cls")

# Use QueryCursor
cursor = QueryCursor(q)
print("\nUsing cursor.matches()...")
cursor.matches(tree.root_node)  # prime it

# Try exec methods
for attr in ["matches", "captures", "exec", "set_point_range", "set_byte_range", "set_match_limit"]:
    print(f"  has {attr}:", hasattr(cursor, attr))

# Try captures
cursor2 = QueryCursor(q)
print("\nCaptures:")
for match in cursor2.matches(tree.root_node):
    print(" match:", match)

```

## `/scripts/smoke_test.py`
```python
"""
Full pipeline test:
1. Ingest this project into ChromaDB
2. Run a semantic search and verify results
"""
import sys
sys.path.insert(0, ".")

print("Step 1: Ingesting the project itself into ChromaDB...")
print("(This will download the sentence-transformer model on first run ~90MB)\n")

# Import the ingest function from bulk_ingest script
from scripts.bulk_ingest import ingest_repository

stats = ingest_repository(repo_path=".", repo_name="devops_agent")

print("\nStep 2: Running semantic search...")
from context_engine.vector_store import search, collection_stats

print(collection_stats())

results = search("security vulnerability checking agent", "devops_agent", n_results=2)
print(f"\nSearch returned {len(results)} results:")
for i, r in enumerate(results, 1):
    print(f"\n--- Result {i} ---")
    print(r[:300])
    print("...")

print("\nFull pipeline test: PASSED!")

```

## `/scripts/__init__.py`
```python
# scripts package placeholder

```

