import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from graph.state import AgentState
from agents.schemas import SpecialistReview
from agents.prompts import SECURITY_AGENT_PROMPT , DEV_AGENT_PROMPT , DOC_AGENT_PROMPT , CODE_QUALITY_AGENT_PROMPT , ARCHITECTURE_AGENT_PROMPT , QA_AGENT_PROMPT
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

def invoke_strict(messages):
    instructions = "CRITICAL: You MUST wrap your entire response in a valid JSON object. Do not include introductory text.\n" + parser.get_format_instructions()
    new_messages = messages + [HumanMessage(content=instructions)]
    res = llm.invoke(new_messages)
    return parser.invoke(res)

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
        "critique_log": [ai_review.critique] 
    }

def backend_dev_node(state: AgentState):
    print(" Backend Dev: Rewriting the code to fix vulnerabilities...")
    
    # 1. Get the current broken code from the clipboard
    broken_code = state.get("current_code", "")
    current_count = state.get("iteration_count", 0)
    critique_log = state.get("critique_log", [])
    
    # 2. Package the instructions for the AI
    messages = [
        SystemMessage(content=DEV_AGENT_PROMPT),
        HumanMessage(content=f"Security Feedback:\n{critique_log}\n\nPlease fix this code:\n\n{broken_code}")
    ]
    
    # 3. Send it to the LLM (Notice we use the standard 'llm' here, not the strict JSON one!)
    response = llm.invoke(messages)
    
    # 4. Extract the raw text from the AI's response
    new_code = response.content
    safe_code = new_code.encode("ascii", errors="replace").decode("ascii")
    print(f"   -> Wrote new code:\n{safe_code}\n")
    
    # 5. Return the updates to the LangGraph clipboard!
    return {
    "current_code": new_code,
    "iteration_count": current_count + 1,
    "ast_is_valid": True,
    "domain_approvals": {
        "security": "pending",
        "architecture": "pending",
        "code_quality": "pending",
        "qa": "pending"
    }
}

def documentation_summarizer_node(state: AgentState):
    print("Doc Agent: Summarizing the journey and saving the report...")
    
    # 1. Pull the "story" from the clipboard 📋
    full_log = state.get("critique_log", [])
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
    print(" Code Quality Agent: Checking for clean code...")
    code = state.get("current_code", "")
    messages = [SystemMessage(content=CODE_QUALITY_AGENT_PROMPT), HumanMessage(content=code)]
    ai_review = invoke_strict(messages)
    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"code_quality": ai_review.vote},
        "critique_log": [f"Code Quality: {ai_review.critique}"]
    }

def architecture_agent_node(state: AgentState):
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
        "critique_log": [f"Architecture: {ai_review.critique}"]
    }

def qa_agent_node(state: AgentState):
    print(" QA Agent: Checking testability and mocks...")
    code = state.get("current_code", "")
    messages = [SystemMessage(content=QA_AGENT_PROMPT), HumanMessage(content=code)]
    ai_review = invoke_strict(messages)
    
    print(f"   -> Vote: {ai_review.vote}")
    safe_print_critique(ai_review.critique)

    return {
        "domain_approvals": {"qa": ai_review.vote},
        "critique_log": [f"QA: {ai_review.critique}"]
    }