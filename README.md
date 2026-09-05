#  DocAgent — Agentic Invoice Processing Engine

DocAgent is an autonomous agentic document processing system built to extract, validate, check compliance, detect anomalies, and route invoice approval workflows with a complete audit trail.

---

##  Architecture & Tech Stack

- **Agent Orchestrator:** LangGraph (State Machine)
- **Extraction & Reasoning:** Google Gemini API
- **Backend API:** FastAPI
- **Cache & Deduplication:** Redis
- **Database:** PostgreSQL (SQLAlchemy)
- **UI / Dashboard:** Streamlit

---

##  Quickstart

### 1. Clone the repository
```bash
git clone https://github.com/ayushcodes27/doc-agent.git
cd doc-agent
```

### 2. Set up environment
```bash
cp .env.example .env
# Add your GEMINI_API_KEY in .env
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

---

##  License
MIT License
