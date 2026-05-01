import os
import re
import subprocess
import time
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from graph.state import AgentState
from agents.prompts import (
    SECURITY_AGENT_PROMPT, BACKEND_ANALYST_AGENT_PROMPT, DEV_AGENT_PROMPT,
    DOC_AGENT_PROMPT, CODE_QUALITY_AGENT_PROMPT, ARCHITECT_AGENT_PROMPT, QA_AGENT_PROMPT,
    FRONTEND_AGENT_PROMPT, CRITIQUE_RESOLVE_AGENT_PROMPT
)
from agents.sandbox import (
    setup_workspace,
    update_workspace_files,
    run_tests_in_docker,
    teardown_workspace,
)
from agents.runtime_config import get_session_settings, record_usage_from_response
from agents.wiki_builder_agent import generate_knowledge_map
from context_engine.knowledge_map_loader import load_knowledge_context
from context_engine.repo_map_builder import build_repo_map
from context_engine.toon_parser import generate_toon_skeleton

load_dotenv()

# =============================================================================
# LLM INSTANCES
#
# Architecture:
#   - arch_llm       : llama-3.3-70b-versatile  â†’ Architecture Agent (tool-calling, ChromaDB)
#                      and Developer + Doc Agents (heavy reasoning, code generation)
#   - review_llm_70b : llama-3.3-70b-versatile  â†’ Backend Analyst (complex logic checking)
#   - review_llm_8b  : llama-3.1-8b-instant     â†’ Security, Code Quality, Frontend Agents
#                      (lightweight TOON verdict, no tool calls, universal rules)
#   - review_llm_scout: llama-4-scout            â†’ QA Agent (separate TPD bucket)
#
# Token Budget per day (Groq Free Tier):
#   llama-3.3-70b-versatile : 100,000 TPD
#   llama-3.1-8b-instant    : 500,000 TPD
#   llama-4-scout           : 500,000 TPD
# =============================================================================

# Heavy lifter: tool-calling + code generation
architecture_llm = None

# High-quality reviewer: complex backend logic analysis
backend_llm = None

# Fast reviewer: universal rule-based checks (security, quality, frontend)
# 500K TPD â€” nearly impossible to exhaust
security_llm = None

# QA Agent: Use 8b instance for tests to stay within budget
qa_llm = None
code_quality_llm = None
frontend_llm = None
critique_llm = None
development_llm = None
documentation_llm = None
wiki_builder_llm = None

_llm_models: dict[int, str] = {}


def _create_llm(agent_key: str) -> ChatOpenAI:
    settings = get_session_settings().get(agent_key, {})
    params = settings.get("parameters", {})
    model = str(settings.get("model", "llama-3.1-8b-instant"))
    llm_kwargs = dict(params)
    max_tokens = int(llm_kwargs.pop("max_tokens", 300))
    temperature = float(llm_kwargs.pop("temperature", 0.2))
    top_p = float(llm_kwargs.pop("top_p", 1.0))
    frequency_penalty = float(llm_kwargs.pop("frequency_penalty", 0.0))
    presence_penalty = float(llm_kwargs.pop("presence_penalty", 0.0))

    llm = ChatOpenAI(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
        **llm_kwargs,
    )
    _llm_models[id(llm)] = model
    return llm


def _record_response_usage(llm_instance: ChatOpenAI, response_obj) -> None:
    model_name = _llm_models.get(id(llm_instance), "unknown")
    record_usage_from_response(model_name, response_obj)

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
            _record_response_usage(llm_instance, res)

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
                current_messages.append(HumanMessage(content="You rejected the code but provided no explanation. You MUST provide a specific, actionable critique formatted as '[CATEGORY] file:line â€” finding'. Do not just say 'REJECT'. Try again."))
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
            response = llm_instance.invoke(messages)
            _record_response_usage(llm_instance, response)
            return response
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"      Final attempt failed: {e}")
                raise e
            print(f"      (Attempt {attempt+1}) API limit/error: {e}. Retrying in 8s...")
            time.sleep(8)


def reload_runtime_models() -> None:
    global architecture_llm, backend_llm, security_llm, qa_llm, code_quality_llm
    global frontend_llm, critique_llm, development_llm, documentation_llm, wiki_builder_llm
    architecture_llm = _create_llm("architecture")
    backend_llm = _create_llm("backend")
    security_llm = _create_llm("security")
    qa_llm = _create_llm("qa")
    code_quality_llm = _create_llm("code_quality")
    frontend_llm = _create_llm("frontend")
    critique_llm = _create_llm("critique_resolve")
    development_llm = _create_llm("development")
    documentation_llm = _create_llm("documentation")
    wiki_builder_llm = _create_llm("wiki_builder")


reload_runtime_models()


# =============================================================================
# Helpers
# =============================================================================

def safe_print_critique(critique: str):
    """Safely print critique strings on Windows consoles without charmap crashes."""
    safe_str = critique.encode("ascii", errors="replace").decode("ascii")
    print(f"   -> Critique: {safe_str}")

def format_files_numbered(files_dict) -> str:
    """
    Coordinate System â€” Single Source of Truth.

    Prepends 1-indexed line numbers to every line of every file:
        1: package main
        2: import "fmt"
        3: func Login() {

    Purpose:
      - Eliminates ambiguity: specialists MUST cite coordinates (e.g., api/endpoints.go:26)
      - Enables surgical fixes: the Dev Agent uses coordinates to target specific lines
      - State verification: confirms disk code matches what the Dev Agent claimed to fix
    """
    if not isinstance(files_dict, dict):
        return str(files_dict)

    formatted = ""
    for filepath, content in files_dict.items():
        lines = content.split("\n")
        # Compact format: 1:line instead of 1: line
        numbered_lines = [f"{i+1}:{line}" for i, line in enumerate(lines)]
        numbered_content = "\n".join(numbered_lines)
        formatted += f"\n[FILE: {filepath}]\n{numbered_content}\n"
    return formatted.strip()


def format_files_raw(files_dict) -> str:
    """
    Raw formatting â€” no line numbers.
    Used when the consumer needs executable/writable code (e.g., disk writes).
    """
    if not isinstance(files_dict, dict):
        return str(files_dict)

    formatted = ""
    for filepath, content in files_dict.items():
        formatted += f"\n--- FILE: {filepath} ---\n{content}\n"
    return formatted.strip()

def format_files_for_reviewers(current_files: dict, diff_files: dict) -> str:
    """
    Builds the ultra-lightweight payload for 8b fast reviewers.
    Combines the TOON Skeleton and the exact Git Patch to eliminate tokens.
    """
    if not isinstance(current_files, dict):
        return str(current_files)

    formatted = ""
    for filepath, content in current_files.items():
        toon_skeleton = generate_toon_skeleton(content, filepath)
        patch = diff_files.get(filepath, "No patch available")
        
        formatted += f"\n[FILE: {filepath}]\n"
        formatted += "--- STRUCTURE (TOON) ---\n"
        formatted += toon_skeleton + "\n"
        formatted += "--- EXACT CHANGES (PATCH) ---\n"
        formatted += patch + "\n"
    
    return formatted.strip()


def read_file_numbered(filepath: str) -> str:
    """
    Reads a single file from disk and returns it with line numbers prepended.
    Useful for state verification â€” confirming on-disk code matches state.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        numbered = [f"{i+1}: {line.rstrip()}" for i, line in enumerate(lines)]
        return f"--- FILE: {filepath} ---\n" + "\n".join(numbered)
    except Exception as e:
        return f"--- FILE: {filepath} --- ERROR: {e}"


# =============================================================================
# AGENT NODES
# =============================================================================

def security_agent_node(state: AgentState):
    """
    Security Agent â€” Universal Rule Checker.

    Why NO ChromaDB:
        SQL injection, hardcoded credentials, and missing auth are universal
        security anti-patterns. The agent does NOT need to know how your
        specific repo is structured to identify them. It applies the same
        rules regardless of codebase. Removing ChromaDB here saves ~3,000
        tokens per call.
    """
    time.sleep(2)
    print(" Security Agent: Scanning code for vulnerabilities...")

    code = format_files_for_reviewers(state.get("current_files", {}), state.get("diff_files", {}))
    messages = [
        SystemMessage(content=SECURITY_AGENT_PROMPT),
        HumanMessage(content=f"Review this pull request code for security vulnerabilities:\n\n{code}")
    ]
    ai_review = invoke_strict(messages, security_llm)

    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"security": ai_review.vote},
        "active_critiques": [f"[Round {state.get('iteration_count', 0)}] Security: {ai_review.critique}"] if ai_review.vote == "rejected" else []
    }


def architecture_agent_node(state: AgentState):
    """
    Architecture Agent - Codebase Pattern Checker.

    Deterministic Context Strategy:
        Round 1:
          - Layer 1: Build/load Repomix repo map (cached by repo + commit).
          - Layer 2: Load Obsidian knowledge map. If missing, bootstrap once
            via Wiki Builder Agent.
          - Cache composed context in state["arch_codebase_context"].
        Round 2+:
          - Reuse cached deterministic context.
    """
    time.sleep(2)
    print(" Architecture Agent: Checking structural design (deterministic context)...")

    code = format_files_for_reviewers(state.get("current_files", {}), state.get("diff_files", {}))
    repo_name = state.get("repo_name", "")
    cached_context = state.get("arch_codebase_context", "")
    commit_sha = state.get("commit_sha", "")
    workspace_path = state.get("sandbox_workspace_path", "")

    if cached_context:
        print("   [Cache HIT] Reusing deterministic context from Round 1.")
        context_gathered = cached_context
        context_to_save = ""
    else:
        print("   [Cache MISS] Building deterministic context layers...")
        if not workspace_path:
            raise RuntimeError(
                "[Architecture] Missing sandbox_workspace_path. Cannot build repo map."
            )

        layer1 = build_repo_map(repo_name=repo_name, workspace_path=workspace_path, commit_sha=commit_sha)
        repo_map_str = layer1["repo_map_str"]

        layer2 = load_knowledge_context(repo_name=repo_name, commit_sha=commit_sha)
        if layer2["map_exists"]:
            knowledge_context_str = layer2["knowledge_context_str"]
            source_commit = layer2.get("source_commit", "")
            if source_commit and commit_sha:
                try:
                    drift_out = subprocess.run(
                        ["git", "rev-list", "--count", f"{source_commit}..{commit_sha}"],
                        cwd=workspace_path,
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=10,
                    )
                    drift_count = int((drift_out.stdout or "0").strip() or 0)
                    if drift_count > 100:
                        print(
                            f"[Knowledge Map] Drift warning: knowledge map is {drift_count} commits behind ({source_commit} -> {commit_sha[:8]})."
                        )
                except Exception:
                    print("[Knowledge Map] Drift check skipped (non-fatal).")
        else:
            print("   [Knowledge Map] Missing map. Triggering Wiki Builder bootstrap...")
            generated = generate_knowledge_map(
                repo_name=repo_name,
                workspace_path=workspace_path,
                repo_map_str=repo_map_str,
                commit_sha=commit_sha,
                wiki_builder_llm=wiki_builder_llm,
            )
            knowledge_context_str = generated["knowledge_context_str"]

        context_gathered = (
            f"[Layer 1 Repo Map]\n{repo_map_str[:4000]}\n\n"
            f"[Layer 2 Knowledge Map]\n{knowledge_context_str[:2000]}"
        )
        context_to_save = context_gathered

    final_messages = [
        SystemMessage(content=ARCHITECT_AGENT_PROMPT),
        HumanMessage(content=(
            f"Repository: {repo_name}\n\n"
            f"Review this pull request code:\n\n{code}\n\n"
            f"Relevant codebase patterns for reference:\n{context_gathered}"
        ))
    ]
    ai_review = invoke_strict(final_messages, architecture_llm)

    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"architecture": ai_review.vote},
        "active_critiques": [f"[Round {state.get('iteration_count', 0)}] Architecture: {ai_review.critique}"] if ai_review.vote == "rejected" else [],
        "arch_codebase_context": context_to_save
    }


def backend_analyst_node(state: AgentState):
    """
    Backend Analyst â€” Functional Logic Checker.

    Why NO ChromaDB:
        Checks functional correctness: SQL injection risks, connection
        leak patterns, incorrect HTTP status codes, error handling.
        These are universal backend patterns â€” no codebase comparison needed.
        Uses the 70b model for its superior reasoning on complex logic.

    Fix #2 â€” UAC Injection:
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

    code = format_files_for_reviewers(state.get("current_files", {}), state.get("diff_files", {}))
    uac_context = state.get("uac_context", "").strip()

    uac_block = (
        f"User Acceptance Criteria (UAC):\n{uac_context}\n\n"
        "Verify that the code below implements exactly what the UAC describes.\n"
        "A feature mismatch is a CRITICAL logic flaw â€” REJECT immediately.\n\n"
    ) if uac_context else ""

    messages = [
        SystemMessage(content=BACKEND_ANALYST_AGENT_PROMPT),
        HumanMessage(content=f"{uac_block}Review this code for functional logic issues:\n\n{code}")
    ]
    ai_review = invoke_strict(messages, backend_llm)

    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"backend": ai_review.vote},
        "active_critiques": [f"[Round {state.get('iteration_count', 0)}] Backend: {ai_review.critique}"] if ai_review.vote == "rejected" else []
    }


def code_quality_agent_node(state: AgentState):
    """
    Code Quality Agent â€” Clean Code Checker.

    Why NO ChromaDB:
        Checks naming conventions, function length, docstrings, nesting
        depth. These are language-level universal standards (e.g., Go
        conventions). Has nothing to do with the repo structure.
        Uses the fast 8b model since this is a lightweight check.
    """
    time.sleep(2)
    print(" Code Quality Agent: Checking for clean code...")

    code = format_files_for_reviewers(state.get("current_files", {}), state.get("diff_files", {}))
    messages = [
        SystemMessage(content=CODE_QUALITY_AGENT_PROMPT),
        HumanMessage(content=code)
    ]
    ai_review = invoke_strict(messages, code_quality_llm)

    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"code_quality": ai_review.vote},
        "active_critiques": [f"[Round {state.get('iteration_count', 0)}] Code Quality: {ai_review.critique}"] if ai_review.vote == "rejected" else []
    }


def qa_agent_node(state):
    """
    QA / SDET Agent â€” Testability Checker.
 
    Dynamic invocation:
        If pr_has_tests=False (set by pr_router_node because no test files
        were found in the PR), this node self-skips immediately.
        This saves ~300â€“500 Groq tokens per pipeline run.
 
    When pr_has_tests=True, runs the full coverage gate and testability review.
    """
    # â”€â”€ Dynamic skip gate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not state.get("pr_has_tests", True):
        print(" QA Agent: No test files detected â€” skipping (pr_has_tests=False).")
        return {
            "domain_approvals": {"qa": "approved"},
            "active_critiques": [],  # empty list = no-op with wipeable_add reducer
        }
 
    # â”€â”€ Full review path â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    time.sleep(2)
    print(" QA Agent: Checking testability and mocks...")

    code = format_files_for_reviewers(state.get("current_files", {}), state.get("diff_files", {}))
    uac_context = state.get("uac_context", "").strip()
 
    uac_block = (
        f"User Acceptance Criteria (UAC):\n{uac_context}\n\n"
        "Also verify the test suite contains at least one test case per UAC scenario. "
        "Missing UAC coverage = REJECT.\n\n"
    ) if uac_context else ""
 
    messages = [
        SystemMessage(content=QA_AGENT_PROMPT),
        HumanMessage(content=f"{uac_block}{code}"),
    ]
    ai_review = invoke_strict(messages, qa_llm)
 
    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)
 
    return {
        "domain_approvals": {"qa": ai_review.vote},
        "active_critiques": [f"[Round {state.get('iteration_count', 0)}] QA: {ai_review.critique}"] if ai_review.vote == "rejected" else [],
    }


def frontend_agent_node(state: AgentState):
    """
    Frontend Integration Agent â€” API Contract Checker.

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

    code = format_files_for_reviewers(state.get("current_files", {}), state.get("diff_files", {}))
    messages = [
        SystemMessage(content=FRONTEND_AGENT_PROMPT),
        HumanMessage(content=code)
    ]
    ai_review = invoke_strict(messages, frontend_llm)

    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"frontend": ai_review.vote},
        "active_critiques": [f"[Round {state.get('iteration_count', 0)}] Frontend: {ai_review.critique}"] if ai_review.vote == "rejected" else []
    }


def critique_resolve_agent_node(state: AgentState):
    """
    Critique Resolve Agent â€” Conflict Resolution Brain.

    Sits between specialist consensus and the Dev Agent. Produces a single
    Master Directive by:
      1. Sorting critiques by priority (Security > QA > Arch > Backend > Frontend > Quality)
      2. Resolving file:line conflicts (higher priority wins)
      3. Blocking goalpost shifting (new non-critical categories in Round 2+)

    The Dev Agent reads ONLY the master_directive, never the raw active_critiques.

    LLM: arch_llm (70b, 3000 tokens). Runs sequentially before the Dev Agent,
    so they never compete for the same API call slot. ~2000 tokens per call.
    """
    time.sleep(2)
    print(" Critique Resolve Agent: Synthesizing critiques into Master Directive...")

    active_critiques = state.get("active_critiques", [])
    iteration_count = state.get("iteration_count", 0)
    full_history = state.get("full_history", [])

    if not active_critiques:
        print("   -> No critiques to resolve. All agents approved.")
        return {"master_directive": "NO_CRITIQUES â€” all agents approved."}

    # â”€â”€ Phase 1: Programmatic Pre-Processing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    AGENT_PRIORITY = {
        "security": 1,
        "qa": 2,
        "architecture": 3,
        "backend": 4,
        "frontend": 5,
        "code quality": 6,
        "code_quality": 6,
    }

    def get_priority(critique_line: str) -> int:
        lower = critique_line.lower()
        for agent_key, priority in AGENT_PRIORITY.items():
            if agent_key in lower:
                return priority
        return 99  # Unknown agent, lowest priority

    # Sort critiques so highest-priority agent appears first
    sorted_critiques = sorted(active_critiques, key=get_priority)

    # Extract Round 1 critiques for loop prevention context
    round_1_critiques = [c for c in full_history if "[Round 0]" in c]

    # â”€â”€ Phase 2: LLM Synthesis â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    round_1_text = "\n".join(round_1_critiques) if round_1_critiques else "(This is Round 1 â€” no prior history)"
    current_text = "\n".join(sorted_critiques)

    human_content = (
        f"ITERATION: {iteration_count}\n\n"
        f"CURRENT_ROUND CRITIQUES (pre-sorted by priority):\n{current_text}\n\n"
        f"ROUND_1_HISTORY:\n{round_1_text}\n\n"
        "Produce the Master Directive now."
    )

    messages = [
        SystemMessage(content=CRITIQUE_RESOLVE_AGENT_PROMPT),
        HumanMessage(content=human_content),
    ]

    time.sleep(3)  # Rate limit buffer after all specialists
    response = invoke_with_retry(critique_llm, messages)

    master_directive = response.content.strip()

    safe_directive = master_directive.encode("ascii", errors="replace").decode("ascii")
    print(f"   -> Master Directive:\n{safe_directive}")

    return {"master_directive": master_directive}


def development_agent_node(state: AgentState):
    """
    Developer Agent - Code Rewriter + Docker Sandbox Validator (Node.js).

    Receives the Master Directive from the Critique Resolve Agent (a conflict-
    resolved, priority-ordered action list) and rewrites the code to fix all
    identified issues. Uses the 70b model for high-quality code generation.

    Sandbox strategy:
      - Webhook mode: The Celery worker pre-clones the full repo into a temp
        dir and passes it via sandbox_workspace_path. We patch LLM-fixed files
        on top and run `npm install && npm test` inside node:20-alpine.
      - Local test_request.py mode: No pre-cloned path; we create a minimal
        sandbox from the in-memory PR diff files instead.
      - Rounds 2 & 3: Re-use the same workspace dir, patching only changed files.
    """
    time.sleep(2)
    print("Development Agent: Rewriting the code to fix issues...")

    broken_code = format_files_numbered(state.get("current_files", {}))
    current_count = state.get("iteration_count", 0)
    master_directive = state.get("master_directive", "")
    workspace_path = state.get("sandbox_workspace_path", "")
    prev_docker_result = state.get("sandbox_test_result", "")

    # -- Sandbox: Use pre-cloned workspace OR create one from memory ----------
    current_files = dict(state.get("current_files", {}))

    if not workspace_path:
        # Local test mode (test_request.py): build sandbox from PR diff in memory
        workspace_path = setup_workspace(current_files)
        print(f"   [Sandbox] Workspace created from memory: {workspace_path}")
    else:
        print(f"   [Sandbox] Using pre-cloned workspace: {workspace_path}")

    # -- Build LLM prompt with Docker compiler evidence (if available) --------
    active_critiques = state.get("active_critiques", [])
    critique_log = active_critiques if active_critiques else ["No specific critiques from this round (all approved)."]

    docker_evidence_block = (
        f"Docker Sandbox result from previous fix attempt:\n{prev_docker_result}\n\n"
    ) if prev_docker_result else ""

    warning_text = "WARNING: FINAL ATTEMPT. Fix ALL critiques or build fails.\n\n" if current_count == 2 else ""

    human_content = (
        f"Feedback from all reviewers:\n{chr(10).join(critique_log)}\n\n"
        f"MASTER DIRECTIVE (conflict-resolved, priority-ordered):\n{master_directive}\n\n"
        f"{docker_evidence_block}"
        f"{warning_text}"
        f"Please fix this codebase:\n\n{broken_code}\n\n"
        "CRITICAL: First provide your CHECKLIST, then provide the full rewritten "
        "source code enclosed in triple backticks for each file you modify. "
        "DO NOT wrap the entire response in a single block - use [FILE: path] "
        "followed by a backtick block for EACH file. Do not use tool calls or wrappers."
    )
    messages = [
        SystemMessage(content=DEV_AGENT_PROMPT),
        HumanMessage(content=human_content)
    ]

    time.sleep(8)
    response = invoke_with_retry(development_llm, messages)

    new_code = response.content
    checklist = ""

    parts = new_code.split("[FILE:", 1)
    if len(parts) > 1:
        checklist = parts[0].strip()
        file_content_part = "[FILE:" + parts[1]
    else:
        file_content_part = new_code

    if checklist:
        safe_checklist = checklist.encode("ascii", errors="replace").decode("ascii")
        print(f"\n   -> Verification Checklist:\n{safe_checklist}\n")

    file_blocks = re.findall(
        r"\[FILE:\s*(.*?)\s*\]\n*(?:```[\w]*\n)?(.*?)```",
        file_content_part,
        re.DOTALL
    )

    for filepath, file_content in file_blocks:
        filepath = filepath.strip()
        file_content = file_content.strip()
        if not file_content:
            print(f"   -> [WARNING] LLM returned empty content for {filepath} - skipping to preserve original")
            continue
        current_files[filepath] = file_content

        try:
            parent = os.path.dirname(filepath)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(file_content)
            print(f"   -> Overwrote local file: {filepath}")
        except Exception as e:
            print(f"   -> [WARNING] Failed to write local file {filepath}: {e}")

    # -- Patch workspace with LLM's rewritten files ---------------------------
    # Write every fixed file into the workspace directory so Docker sees the new code.
    update_workspace_files(workspace_path, current_files)
    print(f"   [Sandbox] Patched {len(current_files)} file(s) into workspace.")

    # -- Auto-detect Node.js app directory ------------------------------------
    # The cloned repo may have a package.json at root OR inside a sub-folder.
    from pathlib import Path as _Path

    workspace_root = _Path(workspace_path)
    node_app_dir = None

    if (workspace_root / "package.json").exists():
        node_app_dir = "."   # package.json is at repo root
    else:
        # Search one level deep for the first sub-directory with package.json
        for subdir in sorted(workspace_root.iterdir()):
            if subdir.is_dir() and (subdir / "package.json").exists():
                node_app_dir = subdir.name
                break

    docker_image = "node:20-alpine"

    if node_app_dir:
        if node_app_dir == ".":
            test_command = (
                "npm install --legacy-peer-deps 2>&1 "
                "&& echo '--- INSTALL_PASSED ---' "
                "&& npm test 2>&1"
            )
        else:
            test_command = (
                f"cd {node_app_dir} "
                "&& npm install --legacy-peer-deps 2>&1 "
                "&& echo '--- INSTALL_PASSED ---' "
                "&& npm test 2>&1"
            )
        print(f"   [Sandbox] Node.js app detected at: {node_app_dir!r} - using {docker_image}")
    else:
        # No package.json found anywhere - skip Docker gracefully
        print("   [Sandbox] WARNING: No package.json found - skipping Docker execution.")
        return {
            "current_files": current_files,
            "iteration_count": current_count + 1,
            "ast_is_valid": True,  # non-fatal; agents still reviewed the code
            "shadow_passed": False,
            "sandbox_workspace_path": workspace_path,
            "sandbox_test_result": "[SANDBOX] No runnable Node.js app detected (no package.json found).",
            "active_critiques": [],
            "domain_approvals": {
                "backend": "pending", "security": "pending",
                "architecture": "pending", "code_quality": "pending",
                "qa": "pending", "frontend": "pending"
            },
        }

    # -- Run Docker: npm install + npm test -----------------------------------
    docker_result = run_tests_in_docker(
        workspace_path=workspace_path,
        test_command=test_command,
        docker_image=docker_image,
    )

    stdout_str = docker_result.stdout or ""
    stderr_str = docker_result.stderr or ""
    full_output = stdout_str + "\n" + stderr_str

    if docker_result.timed_out:
        sandbox_result_str = f"[SANDBOX Round {current_count + 1}] npm install/test TIMED OUT after 60s."
        print("   [Sandbox] TIMED OUT")
    else:
        install_passed = "--- INSTALL_PASSED ---" in full_output
        tests_passed = install_passed and docker_result.passed

        print("\n   [Sandbox] --- Execution Report ---")
        if install_passed:
            print("   [OK] npm install: SUCCESS")
            if tests_passed:
                print("   [OK] npm test: SUCCESS")
                sandbox_result_str = f"[SANDBOX Round {current_count + 1}] OK npm install PASSED. OK npm test PASSED."
            else:
                print(f"   [FAIL] npm test: FAILED (exit code {docker_result.exit_code})")
                sandbox_result_str = (
                    f"[SANDBOX Round {current_count + 1}] OK npm install PASSED. FAIL npm test FAILED.\n"
                    f"STDOUT:\n{stdout_str[:1500]}\n"
                    f"STDERR:\n{stderr_str[:1500]}"
                )
        else:
            print(f"   [FAIL] npm install: FAILED (exit code {docker_result.exit_code})")
            sandbox_result_str = (
                f"[SANDBOX Round {current_count + 1}] FAIL npm install FAILED (exit_code={docker_result.exit_code}).\n"
                f"STDOUT:\n{stdout_str[:1500]}\n"
                f"STDERR:\n{stderr_str[:1500]}"
            )
        print("   ----------------------------------\n")

    return {
        "current_files": current_files,
        "iteration_count": current_count + 1,
        "ast_is_valid": docker_result.passed,
        "shadow_passed": False,
        # Persist workspace path so Rounds 2 & 3 reuse the same cloned directory.
        "sandbox_workspace_path": workspace_path,
        "sandbox_test_result": sandbox_result_str,
        # Wipe short-term critique memory after Dev Agent has consumed it.
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
    Fix #4 â€” Doc Agent Token Bloat.

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
            condensed.append(entry[:max_chars_per_entry] + " [â€¦truncated]")
        else:
            condensed.append(entry)
    return "\n".join(condensed) if condensed else "(no history recorded)"


def documentation_summarizer_node(state: AgentState):
    """
    Documentation Agent â€” Report Generator.

    Reads structured verdicts and critiques from state and passes them
    as pre-built data blocks so the LLM copies them verbatim instead of
    guessing from raw log text. This eliminates hallucinated verdicts.

    Sandbox Teardown:
        This node is the single convergence point for BOTH the happy-path
        (environment_sandbox_node â†’ here) and the failure-path
        (human_fallback_node â†’ here). Tearing down the Docker workspace here
        guarantees it is called exactly once, regardless of which path was
        taken, leaving zero footprint on the host machine.
    """
    time.sleep(2)

    # â”€â”€ Sandbox Teardown (called exactly once, after the 3-round loop) â”€â”€â”€â”€
    workspace_path = state.get("sandbox_workspace_path", "")
    if workspace_path:
        try:
            teardown_workspace(workspace_path)
            print("   [Sandbox] Workspace torn down âœ“ â€” host filesystem clean.")
        except Exception as e:
            # Non-fatal: log and continue. The report must still be generated.
            print(f"   [Sandbox] Teardown warning (non-fatal): {e}")

    print("Doc Agent: Summarizing the journey and saving the report...")

    full_log = state.get("full_history", [])
    files_dict = state.get("current_files", {})
    final_code = format_files_raw(files_dict)
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
    master_directive = state.get("master_directive", "None")

    human_content = (
        f"VERDICTS:\n{verdicts_table}\n\n"
        f"FINAL_CRITIQUES:\n{final_critiques_block}\n\n"
        f"HISTORY (condensed timeline):\n{condensed_history}\n\n"
        f"MASTER_DIRECTIVE (dropped critiques context):\n{master_directive}\n\n"
        f"REQUIRES_HUMAN_REVIEW: {requires_human_review}"
    )

    messages = [
        SystemMessage(content=DOC_AGENT_PROMPT),
        HumanMessage(content=human_content)
    ]

    report_md = ""
    for attempt in range(3):
        try:
            response = invoke_with_retry(documentation_llm, messages, max_retries=3)
            report_md = response.content.strip()
            if report_md:
                break
            print(f"      (Attempt {attempt+1}) Doc Agent returned empty response. Retrying...")
            time.sleep(3)
        except Exception as e:
            print(f"      (Attempt {attempt+1}) Doc Agent error: {e}")
            time.sleep(3)

    if not report_md:
        report_md = "âš ï¸ Could not generate the report. The LLM returned empty responses after multiple attempts."

    try:
        with open("report.md", "w", encoding="utf-8") as f:
            f.write(report_md)
        print("   -> Success! report.md has been created.")
    except Exception as e:
        print(f"   -> Error saving file: {e}")

    # â”€â”€ Post results back to GitHub (Fix #12) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _post_github_results(state, report_md, final_votes)

    return {"human_readable_summary": report_md}


def _post_github_results(state: AgentState, report_md: str, final_votes: dict) -> None:
    """
    Post the review summary as a PR comment and set a GitHub Check Run status.

    Both calls are best-effort â€” any failure is logged but does not affect
    pipeline state or the returned report.

    Silently skips when:
      - pr_url is absent or not a github.com URL (local / unit-test mode).
      - GITHUB_TOKEN env var is not set (would 401 on private repos anyway).
    """
    pr_url = state.get("pr_url", "")
    if not pr_url or "github.com" not in pr_url:
        print("   [GitHub] Skipping posting â€” no GitHub PR URL in state (local test mode).")
        return

    github_token = os.getenv("GITHUB_TOKEN", "")
    if not github_token:
        print("   [GitHub] Skipping posting â€” GITHUB_TOKEN not set.")
        return

    # Parse https://github.com/{owner}/{repo}/pull/{number}
    url_match = re.match(
        r"https://github\.com/([^/]+/[^/]+)/pull/(\d+)",
        pr_url
    )
    if not url_match:
        print(f"   [GitHub] Cannot parse repo/PR number from URL: {pr_url}")
        return

    repo_full_name = url_match.group(1)
    pr_number = int(url_match.group(2))

    # Determine pass/fail conclusion (pending votes are not counted as approved)
    all_approved = all(
        v == "approved"
        for v in final_votes.values()
        if v != "pending"
    )
    conclusion = "success" if all_approved else "failure"

    # Late import â€” avoids loading httpx at module-import time in tests
    from api.github_client import post_pr_comment, create_check_run  # noqa: PLC0415

    # 1. PR comment
    posted = post_pr_comment(repo_full_name, pr_number, report_md)
    print(
        f"   [GitHub] PR comment {'posted' if posted else 'FAILED (non-fatal)'} "
        f"on {repo_full_name}#{pr_number}."
    )

    # 2. Check run (requires a commit SHA from state)
    commit_sha = state.get("commit_sha", "")
    if commit_sha:
        ok = create_check_run(
            repo=repo_full_name,
            sha=commit_sha,
            name="AI Review",
            conclusion=conclusion,
            output={
                "title": "AI Review Complete",
                "summary": report_md[:65535],
            },
        )
        print(
            f"   [GitHub] Check run {'created' if ok else 'FAILED (non-fatal)'} "
            f"(conclusion={conclusion})."
        )
    else:
        print("   [GitHub] No commit_sha in state â€” skipping check run creation.")

