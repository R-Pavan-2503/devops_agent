import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from graph.state import AgentState
from agents.schemas import SpecialistReview
from agents.prompts import SECURITY_AGENT_PROMPT

load_dotenv()

#  Groq LLM (WORKING)
llm = ChatOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    model="openai/gpt-oss-20b"
)

strict_security_llm = llm.with_structured_output(SpecialistReview)


def security_agent_node(state: AgentState):
    print(" Security Agent: Scanning code for vulnerabilities...")
    
    code_to_review = "def login():\n    password = 'super_secret_password'\n    return True"
    
    messages = [
        SystemMessage(content=SECURITY_AGENT_PROMPT),
        HumanMessage(content=f"Review this pull request code:\n\n{code_to_review}")
    ]
    
    ai_review = strict_security_llm.invoke(messages)
    
    print(f"   -> Vote: {ai_review.vote}")
    print(f"   -> Critique: {ai_review.critique}")
    
    return {"domain_approvals": {"security": ai_review.vote}}