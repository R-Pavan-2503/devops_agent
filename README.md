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