import os
import time
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from graph.state import AgentState
from agents.schemas import SpecialistReview
from agents.prompts import (
    SECURITY_AGENT_PROMPT, BACKEND_ANALYST_AGENT_PROMPT, DEVELOPMENT_AGENT_PROMPT,
    DOC_AGENT_PROMPT, CODE_QUALITY_AGENT_PROMPT, ARCHITECTURE_AGENT_PROMPT, QA_AGENT_PROMPT,
    FRONTEND_AGENT_PROMPT
)
from agents.tools import search_codebase_context

load_dotenv()

#  Groq LLM (WORKING)
llm = ChatOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    model="openai/gpt-oss-20b",
    max_tokens=2048
)

from langchain_core.output_parsers import PydanticOutputParser

# Pydantic Output Parser to strictly enforce schema without risky Tool-calling
parser = PydanticOutputParser(pydantic_object=SpecialistReview)

def invoke_strict(messages, max_retries=3):
    """Invokes the LLM and ensures the output is valid JSON according to the schema."""
    for attempt in range(max_retries):
        try:
            time.sleep(3) # Prevent bursting Groq's rate limits
            instructions = "CRITICAL: You MUST wrap your entire response in a valid JSON object. Do not include introductory text.\n" + parser.get_format_instructions()
            new_messages = messages + [HumanMessage(content=instructions)]
            res = llm.invoke(new_messages)
            
            content = res.content.strip()
            if not content:
                print(f"      (Attempt {attempt+1}) LLM returned empty response. Retrying...")
                continue
                
            # Strip markdown code blocks if the model included them
            if content.startswith("```"):
                # Find the first { and last }
                start = content.find("{")
                end = content.rfind("}")
                if start != -1 and end != -1:
                    content = content[start:end+1]
            
            return parser.parse(content)
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"      Final attempt failed: {e}")
                raise e
            print(f"      (Attempt {attempt+1}) Parsing failed. Retrying... Error: {e}")
            time.sleep(2)
            
    # If the loop finishes without returning, it means all attempts were either empty or failed.
    raise ValueError(f"LLM consistently returned empty responses or failed to parse after {max_retries} attempts.")

# Tool-calling LLMs can invoke search_codebase_context before giving their final verdict.
_context_tools = [search_codebase_context]
llm_with_tools = llm.bind_tools(_context_tools)
# We remove strict_security_llm_with_tools because binding tools + structured output
# concurrently confuses the API's tool_choice forcing.


def safe_print_critique(critique: str):
    """Safely print critique strings on Windows consoles without charmap crashes"""
    safe_str = critique.encode("ascii", errors="replace").decode("ascii")
    print(f"   -> Critique: {safe_str}")

def security_agent_node(state: AgentState):
    time.sleep(2) # Prevent rate limits
    print(" Security Agent: Scanning code for vulnerabilities (with codebase context)...")
    
    code_to_review = state.get("current_code", "")
    repo_name = state.get("repo_name", "")
    
    messages = [
        SystemMessage(content=SECURITY_AGENT_PROMPT),
        HumanMessage(content=(
            f"Repository: {repo_name}\n\n"
            f"Review this pull request code:\n\n{code_to_review}"
        ))
    ]
    
    context_gathered = ""
    # Phase 1: Let the AI search the codebase using tools (up to 3 times)
    for _ in range(3):
        time.sleep(2) # Rate limit protection
        response = llm_with_tools.invoke(messages)
        messages.append(response)
        
        if not response.tool_calls:
            break
            
        for tool_call in response.tool_calls:
            if tool_call["name"] == "search_codebase_context":
                tool_msg_content = str(search_codebase_context.invoke(tool_call["args"]))
                context_gathered += f"\n--- Context ---\n{tool_msg_content}\n"
                messages.append(ToolMessage(
                    tool_call_id=tool_call["id"],
                    name=tool_call["name"],
                    content=tool_msg_content
                ))
    
    # Phase 2: Force the final response into the SpecialistReview JSON format
    # We create a fresh clean message list to avoid confusing Groq's JSON/tool parser 
    # with the intermediate ToolMessages history.
    
    # Strip the tool instruction so the model doesn't try to output tool JSON instead of SpecialistReview
    phase2_prompt = SECURITY_AGENT_PROMPT.split("[TOOL USE")[0] + "[CONSTRAINTS]" + SECURITY_AGENT_PROMPT.split("[CONSTRAINTS]")[1]
    
    final_messages = [
        SystemMessage(content=phase2_prompt),
        HumanMessage(content=(
            f"Repository: {repo_name}\n\n"
            f"Review this pull request code:\n\n{code_to_review}\n\n"
            f"Context gathered from codebase:\n{context_gathered}"
        ))
    ]
    ai_review = invoke_strict(final_messages)
    
    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)
    
    return {
        "domain_approvals": {"security": ai_review.vote},
        "active_critiques": [f"Security: {ai_review.critique}"] 
    }

def development_agent_node(state: AgentState):
    time.sleep(2) # Prevent rate limits
    print("Development Agent: Rewriting the code to fix issues...")
    
    # 1. Get the current broken code from the clipboard
    broken_code = state.get("current_code", "")
    current_count = state.get("iteration_count", 0)
    critique_log = state.get("active_critiques", [])  # Short-term: only this round's feedback
    
    # 2. Package the instructions for the AI
    human_content = (
        f"Feedback:\n{critique_log}\n\n"
        f"Please fix this code:\n\n{broken_code}\n\n"
        "CRITICAL: Output ONLY the raw source code as plain text. "
        "Do NOT use any tool calls, function calls, or JSON wrappers. "
        "Your entire response must be executable source code and nothing else."
    )
    messages = [
        SystemMessage(content=DEVELOPMENT_AGENT_PROMPT),
        HumanMessage(content=human_content)
    ]
    
    # 3. Send it to the LLM — longer delay here because all 5 analysts just ran
    time.sleep(8) # Rate limit protection: give Groq TPM quota time to reset
    response = llm.invoke(messages)
    
    # 4. Extract and clean the raw text from the AI's response
    new_code = response.content
    
    # Strip markdown if the AI wrapped it in ```python or ```
    if "```" in new_code:
        # Extract content between the first and last triple backticks
        parts = new_code.split("```")
        if len(parts) >= 3:
            # part[0] is before first ```
            # part[1] is the language + code (e.g. "python\ndef...")
            # We want to remove the language identifier if it exists
            content = parts[1]
            lines = content.split("\n")
            if lines and not lines[0].strip().startswith(" "): # Likely language name
                content = "\n".join(lines[1:])
            new_code = content.strip()

    safe_code = new_code.encode("ascii", errors="replace").decode("ascii")
    print(f"   -> Wrote new code:\n{safe_code}\n")
    
    # 5. Return the updates to the LangGraph clipboard!
    return {
        "current_code": new_code,
        "iteration_count": current_count + 1,
        "ast_is_valid": True,
        "domain_approvals": {
            "backend": "pending",
            "security": "pending",
            "architecture": "pending",
            "code_quality": "pending",
            "qa": "pending",
            "frontend": "pending"
        },
    }

def backend_analyst_node(state: AgentState):
    time.sleep(2) # Prevent rate limits
    print(" Backend Analyst: Checking functional logic and efficiency...")
    code = state.get("current_code", "")
    messages = [SystemMessage(content=BACKEND_ANALYST_AGENT_PROMPT), HumanMessage(content=code)]
    ai_review = invoke_strict(messages)
    
    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"backend": ai_review.vote},
        "active_critiques": [f"Backend: {ai_review.critique}"]
    }

def documentation_summarizer_node(state: AgentState):
    time.sleep(2) # Prevent rate limits
    print("Doc Agent: Summarizing the journey and saving the report...")
    
    # 1. Pull the full journey from long-term memory 📋
    full_log = state.get("full_history", [])  # Long-term: entire journey across all rounds
    final_code = state.get("current_code", "")
    
    # 2. Ask the AI to format it into Markdown 🤖
    messages = [
        SystemMessage(content=DOC_AGENT_PROMPT),
        HumanMessage(content=f"History of changes:\n{full_log}\n\nFinal Approved Code:\n{final_code}")
    ]
    
    response = llm.invoke(messages)
    report_md = response.content
    
    # 3. Write the actual file to your disk 💾
    try:
        with open("report.md", "w", encoding="utf-8") as f:
            f.write(report_md)
        print("   -> Success! report.md has been created.")
    except Exception as e:
        print(f"   -> Error saving file: {e}")
    
    return {"human_readable_summary": report_md}


def code_quality_agent_node(state: AgentState):
    time.sleep(2) # Prevent rate limits
    print(" Code Quality Agent: Checking for clean code...")
    code = state.get("current_code", "")
    messages = [SystemMessage(content=CODE_QUALITY_AGENT_PROMPT), HumanMessage(content=code)]
    ai_review = invoke_strict(messages)
    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"code_quality": ai_review.vote},
        "active_critiques": [f"Code Quality: {ai_review.critique}"]
    }

def architecture_agent_node(state: AgentState):
    time.sleep(2) # Prevent rate limits
    print(" Architecture Agent: Checking structural design (with codebase context)...")
    code = state.get("current_code", "")
    repo_name = state.get("repo_name", "")
    messages = [
        SystemMessage(content=ARCHITECTURE_AGENT_PROMPT),
        HumanMessage(content=(
            f"Repository: {repo_name}\n\n"
            f"Review this pull request code:\n\n{code}"
        ))
    ]
    context_gathered = ""
    # Phase 1: Let the AI search the codebase using tools
    for _ in range(3):
        time.sleep(2) # Rate limit protection
        response = llm_with_tools.invoke(messages)
        messages.append(response)
        
        if not response.tool_calls:
            break
            
        for tool_call in response.tool_calls:
            if tool_call["name"] == "search_codebase_context":
                tool_msg_content = str(search_codebase_context.invoke(tool_call["args"]))
                context_gathered += f"\n--- Context ---\n{tool_msg_content}\n"
                messages.append(ToolMessage(
                    tool_call_id=tool_call["id"],
                    name=tool_call["name"],
                    content=tool_msg_content
                ))

    # Phase 2: Force the final extraction
    phase2_prompt = ARCHITECTURE_AGENT_PROMPT.split("[TOOL USE")[0] + "[TASK]" + ARCHITECTURE_AGENT_PROMPT.split("[TASK]")[1]
    
    final_messages = [
        SystemMessage(content=phase2_prompt),
        HumanMessage(content=(
            f"Repository: {repo_name}\n\n"
            f"Review this pull request code:\n\n{code}\n\n"
            f"Context gathered from codebase:\n{context_gathered}"
        ))
    ]
    ai_review = invoke_strict(final_messages)
    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"architecture": ai_review.vote},
        "active_critiques": [f"Architecture: {ai_review.critique}"]
    }

def qa_agent_node(state: AgentState):
    time.sleep(2) # Prevent rate limits
    print(" QA Agent: Checking testability and mocks...")
    code = state.get("current_code", "")
    messages = [SystemMessage(content=QA_AGENT_PROMPT), HumanMessage(content=code)]
    ai_review = invoke_strict(messages)
    
    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"qa": ai_review.vote},
        "active_critiques": [f"QA: {ai_review.critique}"]
    }

def frontend_agent_node(state: AgentState):
    time.sleep(2) # Prevent rate limits
    print(" Frontend Agent: Checking API contract and formatting...")
    code = state.get("current_code", "")
    messages = [SystemMessage(content=FRONTEND_AGENT_PROMPT), HumanMessage(content=code)]
    ai_review = invoke_strict(messages)
    
    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"frontend": ai_review.vote},
        "active_critiques": [f"Frontend: {ai_review.critique}"]
    }