import os
import re
import time
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from graph.state import AgentState
from agents.old_prompts_v2 import (
    SECURITY_AGENT_PROMPT, BACKEND_ANALYST_AGENT_PROMPT, DEV_AGENT_PROMPT,
    DOC_AGENT_PROMPT, CODE_QUALITY_AGENT_PROMPT, ARCHITECT_AGENT_PROMPT, QA_AGENT_PROMPT,
    FRONTEND_AGENT_PROMPT
)
from agents.tools import search_codebase_context
from agents.sandbox import (
    setup_workspace,
    update_workspace_files,
    run_tests_in_docker,
    teardown_workspace,
)

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


def qa_agent_node(state):
    """
    QA / SDET Agent — Testability Checker.
 
    Dynamic invocation:
        If pr_has_tests=False (set by pr_router_node because no test files
        were found in the PR), this node self-skips immediately.
        This saves ~300–500 Groq tokens per pipeline run.
 
    When pr_has_tests=True, runs the full coverage gate and testability review.
    """
    import time
    from langchain_core.messages import SystemMessage, HumanMessage
    from agents.prompts import QA_AGENT_PROMPT
    from agents.nodes import (
        invoke_strict, review_llm_scout,
        format_files_for_llm, safe_print_critique,
    )
 
    # ── Dynamic skip gate ────────────────────────────────────────────────────
    if not state.get("pr_has_tests", True):
        print(" QA Agent: No test files detected — skipping (pr_has_tests=False).")
        return {
            "domain_approvals": {"qa": "approved"},
            "active_critiques": [],  # empty list = no-op with wipeable_add reducer
        }
 
    # ── Full review path ─────────────────────────────────────────────────────
    time.sleep(2)
    print(" QA Agent: Checking testability and mocks...")
 
    code        = format_files_for_llm(state.get("current_files", {}))
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
    ai_review = invoke_strict(messages, review_llm_scout)
 
    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)
 
    return {
        "domain_approvals": {"qa": ai_review.vote},
        "active_critiques": [
            f"[Round {state.get('iteration_count', 0)}] QA: {ai_review.critique}"
        ],
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
    Developer Agent — Code Rewriter + Docker Sandbox Validator.

    Receives the combined critique log from all agents in the current round
    and rewrites the code to fix all identified issues.

    Sandbox Integration (3-round loop):
        Round 1 (iteration_count == 0):
            - setup_workspace() creates the host temp dir and writes all .go files.
            - go.mod is auto-injected at the Go project root (detected from file paths)
              so `go vet` works inside Docker without needing network access.
            - workspace_path is persisted in state so Rounds 2 & 3 can reuse it.

        Rounds 2 & 3 (iteration_count >= 1):
            - Workspace already exists (path carried in state['sandbox_workspace_path']).
            - update_workspace_files() patches the sandbox with the new code.
            - run_tests_in_docker() verifies the new fix.

    go.mod placement:
        go.mod must live in the same directory as the Go source files, not at the
        workspace root. The function detects the project root from the file paths:
          "test_apps/backend_login_go/api/endpoints.go"  →  go.mod at
          "test_apps/backend_login_go/go.mod"
        This ensures `import "backend_login_go/service"` resolves correctly inside Docker.
    """
    time.sleep(2)
    print("Development Agent: Rewriting the code to fix issues...")

    broken_code = format_files_for_llm(state.get("current_files", {}))
    current_count = state.get("iteration_count", 0)
    critique_log = state.get("active_critiques", [])
    workspace_path = state.get("sandbox_workspace_path", "")
    prev_docker_result = state.get("sandbox_test_result", "")

    # ── Sandbox: Setup on Round 1, patch-in-place on Rounds 2 & 3 ────────
    current_files = dict(state.get("current_files", {}))

    if not workspace_path:
        # Strip "test_apps/backend_login_go/" prefix so the Go project
        # lands at the workspace root — matching how go.mod declares the module.
        _PREFIX = "test_apps/"
        files_for_sandbox = {
            (k[len(_PREFIX):] if k.replace("\\", "/").startswith(_PREFIX) else k): v
            for k, v in current_files.items()
        }

        if any(f.endswith(".go") for f in files_for_sandbox):
            # Inject the real go.mod from disk (has correct require + go version)
            try:
                with open("test_apps/backend_login_go/go.mod", "r", encoding="utf-8") as _f:
                    files_for_sandbox["backend_login_go/go.mod"] = _f.read()
                print("   [Sandbox] Injected real go.mod from disk")
            except FileNotFoundError:
                files_for_sandbox["backend_login_go/go.mod"] = "module backend_login_go\n\ngo 1.22\n"
                print("   [Sandbox] WARNING: go.mod not found on disk — using minimal fallback")

            # Inject go.sum so external deps (golang.org/x/crypto) resolve offline
            for _sum_candidate in [
                "test_apps/backend_login_go/go.sum",
                "go.sum",
            ]:
                try:
                    with open(_sum_candidate, "r", encoding="utf-8") as _f:
                        files_for_sandbox["backend_login_go/go.sum"] = _f.read()
                    print(f"   [Sandbox] Injected go.sum from {_sum_candidate} ({len(files_for_sandbox['backend_login_go/go.sum'])} bytes)")
                    break
                except FileNotFoundError:
                    continue
            else:
                print("   [Sandbox] WARNING: go.sum not found anywhere — external deps may fail")

        workspace_path = setup_workspace(files_for_sandbox)
        print(f"   [Sandbox] Workspace created: {workspace_path}")
    else:
        # Rounds 2 & 3 — Reuse the existing workspace, patch changed files.
        _PREFIX = "test_apps/"
        files_stripped = {
            (k[len(_PREFIX):] if k.replace("\\", "/").startswith(_PREFIX) else k): v
            for k, v in current_files.items()
        }
        update_workspace_files(workspace_path, files_stripped)
        print(f"   [Sandbox] Workspace patched for Round {current_count + 1}: {workspace_path}")

    # ── Build LLM prompt with Docker compiler evidence (if available) ─────
    docker_evidence_block = (
        f"Docker Sandbox result from previous fix attempt:\n{prev_docker_result}\n\n"
    ) if prev_docker_result else ""

    warning_text = "WARNING: FINAL ATTEMPT. Fix ALL critiques or build fails.\n\n" if current_count == 2 else ""

    human_content = (
        f"Feedback from all reviewers:\n{chr(10).join(critique_log)}\n\n"
        f"{docker_evidence_block}"
        f"{warning_text}"
        f"Please fix this codebase:\n\n{broken_code}\n\n"
        "CRITICAL: First provide your CHECKLIST, then provide the full rewritten "
        "source code enclosed in triple backticks for each file you modify. "
        "DO NOT wrap the entire response in a single block — use [FILE: path] "
        "followed by a backtick block for EACH file. Do not use tool calls or wrappers."
    )
    messages = [
        SystemMessage(content=DEV_AGENT_PROMPT),
        HumanMessage(content=human_content)
    ]

    time.sleep(8)
    response = invoke_with_retry(arch_llm, messages)

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
            print(f"   -> [WARNING] LLM returned empty content for {filepath} — skipping to preserve original")
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

    # ── Patch sandbox workspace with LLM's rewritten files ───────────────
    # Exclude go.mod (any path variant) — injected once at setup, must not be overwritten.
    _PREFIX = "test_apps/"
    files_to_patch = {
        (k[len(_PREFIX):] if k.replace("\\", "/").startswith(_PREFIX) else k): v
        for k, v in current_files.items()
        if k not in ("go.mod", "go.sum")  # never let LLM overwrite these
    }
    update_workspace_files(workspace_path, files_to_patch)
    print(f"   [Sandbox] Patched {len(files_to_patch)} file(s) with LLM's rewritten code.")

    # ── Run Docker compilation check (`go vet` -> `go test`) ───────────────
    docker_result = run_tests_in_docker(
        workspace_path=workspace_path,
        test_command=(
             "cd backend_login_go && "
             "(GONOSUMCHECK=* GOFLAGS=-mod=mod go vet ./... && "
             "echo '--- VET_PASSED ---' && "
             "GONOSUMCHECK=* GOFLAGS=-mod=mod go test ./... -v) 2>&1"
        ),
        docker_image="golang:1.22",
    )

    stdout_str = docker_result.stdout or ""
    stderr_str = docker_result.stderr or ""
    full_output = stdout_str + "\n" + stderr_str

    if docker_result.timed_out:
        sandbox_result_str = f"[SANDBOX Round {current_count + 1}] ⏱️ go vet/test TIMED OUT after 60s."
        print(f"   [Sandbox] ⏱️ TIMED OUT")
    else:
        # Determine exactly what happened
        vet_passed = "--- VET_PASSED ---" in full_output
        has_tests = "no test files" not in full_output and "?   " not in full_output
        tests_passed = vet_passed and docker_result.passed

        print("\n   [Sandbox] --- Execution Report ---")
        if vet_passed:
            print("   ✅ Compilation / go vet: SUCCESS")
            if tests_passed:
                print("   ✅ Unit Tests: SUCCESS")
                sandbox_result_str = f"[SANDBOX Round {current_count + 1}] ✅ COMPILATION PASSED. ✅ UNIT TESTS PASSED."
            else:
                if has_tests:
                    print(f"   ❌ Unit Tests: FAILED (exit code {docker_result.exit_code})")
                    sandbox_result_str = f"[SANDBOX Round {current_count + 1}] ✅ COMPILATION PASSED. ❌ UNIT TESTS FAILED.\nSTDOUT:\n{stdout_str[:1500]}"
                else:
                    print("   ⚠️ Unit Tests: DID NOT RUN (No tests found)")
                    sandbox_result_str = f"[SANDBOX Round {current_count + 1}] ✅ COMPILATION PASSED. ⚠️ NO TESTS RAN."
                    # If there's no tests, but vet passed, that's still an AST success
                    docker_result.passed = True
        else:
            print(f"   ❌ Compilation / go vet: REJECTED (exit code {docker_result.exit_code})")
            print("   ⚠️ Unit Tests: DID NOT RUN (Compilation failed)")
            sandbox_result_str = (
                f"[SANDBOX Round {current_count + 1}] ❌ COMPILATION FAILED (exit_code={docker_result.exit_code}).\n"
                f"STDOUT:\n{stdout_str[:1500]}\n"
                f"STDERR:\n{stderr_str[:1500]}"
            )
        print("   ----------------------------------\n")

    return {
        "current_files": current_files,
        "iteration_count": current_count + 1,
        "ast_is_valid": docker_result.passed,
        "shadow_passed": False,
        # Persist workspace path so Rounds 2 & 3 reuse the same temp dir
        # instead of spinning up a new one each iteration.
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

    Sandbox Teardown:
        This node is the single convergence point for BOTH the happy-path
        (environment_sandbox_node → here) and the failure-path
        (human_fallback_node → here). Tearing down the Docker workspace here
        guarantees it is called exactly once, regardless of which path was
        taken, leaving zero footprint on the host machine.
    """
    time.sleep(2)

    # ── Sandbox Teardown (called exactly once, after the 3-round loop) ────
    workspace_path = state.get("sandbox_workspace_path", "")
    if workspace_path:
        try:
            teardown_workspace(workspace_path)
            print("   [Sandbox] Workspace torn down ✓ — host filesystem clean.")
        except Exception as e:
            # Non-fatal: log and continue. The report must still be generated.
            print(f"   [Sandbox] Teardown warning (non-fatal): {e}")

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