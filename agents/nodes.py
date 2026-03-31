import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from graph.state import AgentState
from agents.schemas import SpecialistReview
from agents.prompts import SECURITY_AGENT_PROMPT , DEV_AGENT_PROMPT , DOC_AGENT_PROMPT , CODE_QUALITY_AGENT_PROMPT , ARCHITECTURE_AGENT_PROMPT , QA_AGENT_PROMPT

load_dotenv()

#  Groq LLM (WORKING)
llm = ChatOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    model="openai/gpt-oss-20b",
    max_tokens=2048
)

strict_security_llm = llm.with_structured_output(SpecialistReview)


def security_agent_node(state: AgentState):
    print(" Security Agent: Scanning code for vulnerabilities...")
    
    code_to_review = state.get("current_code", "")
    
    messages = [
        SystemMessage(content=SECURITY_AGENT_PROMPT),
        HumanMessage(content=f"Review this pull request code:\n\n{code_to_review}")
    ]
    
    ai_review = strict_security_llm.invoke(messages)
    
    print(f"   -> Vote: {ai_review.vote}")
    print(f"   -> Critique: {ai_review.critique}")
    
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
    print(f"   -> Wrote new code:\n{new_code}\n")
    
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
    ai_review = strict_security_llm.invoke(messages)
    return {
        "domain_approvals": {"code_quality": ai_review.vote},
        "critique_log": [f"Code Quality: {ai_review.critique}"]
    }

def architecture_agent_node(state: AgentState):
    print(" Architecture Agent: Checking structural design...")
    code = state.get("current_code", "")
    messages = [SystemMessage(content=ARCHITECTURE_AGENT_PROMPT), HumanMessage(content=code)]
    ai_review = strict_security_llm.invoke(messages)
    return {
        "domain_approvals": {"architecture": ai_review.vote},
        "critique_log": [f"Architecture: {ai_review.critique}"]
    }

def qa_agent_node(state: AgentState):
    print(" QA Agent: Checking testability and mocks...")
    code = state.get("current_code", "")
    messages = [SystemMessage(content=QA_AGENT_PROMPT), HumanMessage(content=code)]
    ai_review = strict_security_llm.invoke(messages)
    return {
        "domain_approvals": {"qa": ai_review.vote},
        "critique_log": [f"QA: {ai_review.critique}"]
    }