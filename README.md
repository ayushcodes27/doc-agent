# DocAgent — Agentic Invoice Processing Engine

[![CI](https://github.com/ayushcodes27/doc-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/ayushcodes27/doc-agent/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-State_Machine-orange.svg)](https://github.com/langchain-ai/langgraph)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-red.svg?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-UI-FF4B4B.svg?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **DocAgent** is a production-grade, autonomous document processing agent designed to streamline accounts payable and enterprise invoice operations. It extracts structured data from multi-modal documents (PDF, Scanned Images, TXT), validates compliance against 9 deterministic business rules, performs statistical fraud & anomaly screening, detects SHA-256 duplicates, and manages human-in-the-loop approval workflows with full database persistence and an immutable audit trail.

---

## System Architecture

<div align="center">
  <img src="images/docagent_archi.png" alt="DocAgent System Architecture" width="850"/>
</div>

### End-to-End Data Flow

<div align="center">
  <img src="images/docagent_dataflow.png" alt="DocAgent End-to-End Data Flow" width="850"/>
</div>

<details open>
<summary><b>End-to-End System Architecture (Deterministic 2-Pillar Flow)</b></summary>

```mermaid
flowchart TD
    classDef startEnd fill:#e1f5fe,stroke:#0288d1,stroke-width:2px;
    classDef gate fill:#fff3e0,stroke:#f57c00,stroke-width:2px;
    classDef dual fill:#ede7f6,stroke:#5e35b1,stroke-width:2px;
    classDef p1 fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef p2 fill:#fce4ec,stroke:#c2185b,stroke-width:2px;
    classDef approve fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px;
    classDef review fill:#ffe0b2,stroke:#ef6c00,stroke-width:2px;
    classDef reject fill:#ffcdd2,stroke:#c62828,stroke-width:2px;
    classDef save fill:#eceff1,stroke:#455a64,stroke-width:2px;

    Start(["1. Ingestion: PDF / Image"]):::startEnd --> HashGate{"SHA-256 Hash in SQL DB?"}:::gate
    HashGate -- "Yes (Exact Duplicate)" --> QuickReject["Instant Reject ($0 LLM Cost)"]:::reject
    HashGate -- "No (New File)" --> Prep["PyMuPDF Prep:<br/>Render 150 DPI Image + Check Digital Text"]:::dual

    subgraph Stage1 ["Stage 1: Hybrid OCR & Dual-Observer Extraction"]
        Prep --> OCRCheck{"Digital Layer >= 50 chars?"}:::gate
        OCRCheck -- "Yes" --> NativeText["Native Digital Text"]
        OCRCheck -- "No (Scanned PDF)" --> RapidOCR["RapidOCR Fallback (CPU ONNX)"]:::dual

        Prep --> ObsA["Observer A: Gemini Flash Vision<br/>(150 DPI Image + Raw Digital Layer)<br/>Extracts Full Schema + Tampering Flag"]:::dual
        NativeText & RapidOCR --> ObsB["Observer B: GPT-4o-mini (temp=0.0)<br/>(Verifier Text Only)<br/>Extracts 3 Anchors + Evidence Snippets"]:::dual
    end

    subgraph Stage2 ["Stage 2: Deterministic 2-Pillar Scoring Engine"]
        ObsA & ObsB --> P1["Pillar 1: Extraction & Observer Trust (Max 0.50)<br/>• Hard Breaker: Tampering=True OR Total Diff > $0.05<br/>• Vendor Name Fuzzy < 80% (+0.20)<br/>• Invoice # Edit Dist > 1 (+0.15)<br/>• Missing Evidence Snippet (+0.15)"]:::p1
        
        ObsA --> P2["Pillar 2: Hard Math & SQL Dedup (Max 0.50)<br/>• Hard Breaker: SQL Duplicate Inv# + Vendor<br/>• Sum(Line Items) != Subtotal (+0.25)<br/>• Subtotal + Tax != Total (+0.25)<br/>• Due Date < Inv Date (+0.15) | Total > $10k (+0.25)"]:::p2

        P1 & P2 --> Breaker{"Any Hard Breaker Triggered?"}:::gate
        Breaker -- "No" --> Calc["Composite Risk Score: R = P1 + P2<br/>Bounded: [0.00, 1.00]"]:::save
    end

    Breaker -- "Yes" --> AutoReject["Auto-Reject"]:::reject
    Calc -- "R >= 0.60" --> AutoReject
    Calc -- "0.20 <= R < 0.60" --> HumanReview["Human Review Queue"]:::review
    Calc -- "R < 0.20" --> AutoApprove["Auto-Approve for Payout"]:::approve

    HumanReview --> HumanDec{"Reviewer Action"}:::gate
    HumanDec -- "Approve" --> AutoApprove
    HumanDec -- "Reject" --> AutoReject

    QuickReject & AutoApprove & AutoReject --> DB[("PostgreSQL / SQLite<br/>(Invoices Table + Audit Status Log)")]:::save
```
</details>

---

## Core Capabilities & Agent Pipeline

```
Raw Invoice (PDF / Image / TXT)
  │
  ├─► 1. Pre-LLM SQL Hash Gate: SELECT id FROM invoices WHERE file_hash = :hash AND status != 'REJECTED'
  │      └─► Instant reject for duplicate files ($0 LLM API Cost)
  │
  ├─► 2. Ingestion & RapidOCR Fallback (tools/document_loader.py)
  │      ├─► Renders 150 DPI page image for multimodal inspection
  │      ├─► Extracts raw digital text layer (passed to Observer A to flag digital-vs-visual tampering)
  │      └─► Uses RapidOCR fallback if digital text < 50 chars (passed to Observer B so scans never fail)
  │
  ├─► 3. Observer A (Gemini Flash Multimodal Vision)
  │      └─► Extracts full invoice schema, line items, and detects visual layer discrepancy
  │
  ├─► 4. Observer B (GPT-4o-mini, temp=0.0)
  │      └─► Text-only extraction of 3 key anchors + verbatim evidence snippets
  │
  ├─► 5. Deterministic 2-Pillar Scoring & Routing Engine (tools/score_and_route.py)
  │      ├─► Pillar 1: Extraction & Observer Trust (Max: 0.50)
  │      │     • Hard Breaker: Tampering detected OR Total Diff > $0.05
  │      │     • Soft Checks: Vendor similarity < 80% (+0.20), Inv# mismatch (+0.15), Missing snippet (+0.15)
  │      │
  │      ├─► Pillar 2: Hard Math & Pure SQL Deduplication (Max: 0.50)
  │      │     • Hard Breaker: SQL Duplicate (invoice_number_norm + vendor_name)
  │      │     • Soft Checks: Line items sum != subtotal (+0.25), Subtotal + tax != total (+0.25)
  │      │     • Compliance: Due date < Invoice date (+0.15), Total > Payout Cap (+0.25)
  │      │
  │      └─► Deterministic Routing Matrix:
  │            • Hard Breaker OR R >= 0.60 ──► AUTO_REJECT
  │            • 0.20 <= R < 0.60          ──► HUMAN_REVIEW
  │            • R < 0.20                  ──► AUTO_APPROVE
  │
  ├─► 6. Human Review Queue & Decision Overrides (Streamlit UI with audit logs)
  │
  └─► 7. Tamper-Evident SHA-256 Hash-Chained Audit Trail

---

## Business Validation Engine (9 Compliance Rules)

| Rule Name | Severity | Description |
|---|---|---|
| `max_amount` | `ERROR` | Invoice amount must not exceed departmental budget limit (₹500,000 / $500,000). |
| `approved_vendor` | `ERROR` | Vendor must be in the approved master vendor registry (24+ verified enterprise vendors + real database vendors). |
| `date_validity` | `ERROR` | Invoice date must be a valid ISO format and not post-dated in the future. |
| `visual_text_consistency` | `ERROR` | Embedded visual scan amount must match digital line items (tampering alert). |
| `line_item_math` | `WARNING` | Individual line items (`qty × rate`) must sum to subtotal within ±1% tolerance. |
| `total_math` | `WARNING` | Declared `Subtotal + Tax Amount` must match `Total Amount` within ±1% tolerance. |
| `vendor_id_present` | `WARNING` | Vendor must supply a valid tax registration identifier (GSTIN, VAT ID, EIN). |
| `currency_consistency` | `WARNING` | Currency must be a recognized ISO 4217 standard currency code (INR, USD, EUR, GBP). |
| `payment_terms_check` | `INFO` | Invoice must explicitly declare payment terms (e.g., Net 30, Due on Receipt). |

---

## Evaluation & Benchmark Suite

### 1. Real-World Enterprise Benchmark (16 Real Invoices vs 500 Federal Awards)

DocAgent has been benchmarked directly on **16 authentic enterprise PDF invoices** (including Amazon Web Services, Flipkart B2B, Azure, QualityHosting, Coolblue, and Microsoft Document Intelligence samples) evaluated against a historical baseline of **500 real U.S. federal contract awards ($146.1B volume across 178 contractors via USASpending.gov)**:

```bash
# Run the real-world enterprise benchmark suite
python eval/run_real_benchmark.py
```

| Real-World Benchmark Metric | Result | Target | Status |
|---|---|---|---|
| **Document Extraction Rate** | `100.0%` (16/16 invoices) | `≥ 90.0%` | PASSED |
| **Vendor Recognition Accuracy** | `100.0%` (16/16 vendors) | `≥ 90.0%` | PASSED |
| **Total Amount Accuracy** | `100.0%` (16/16 totals) | `≥ 95.0%` | PASSED |
| **Invoice Date Accuracy** | `100.0%` (16/16 dates) | `≥ 90.0%` | PASSED |
| **Line Items Extraction Rate** | `100.0%` (16/16 items) | `≥ 85.0%` | PASSED |
| **Average Extraction Confidence** | `95.9%` | `≥ 85.0%` | PASSED |
| **Average Processing Latency** | `11.23s` / document | `≤ 15.0s` | PASSED |

*Full real-world reports: [`eval/real_benchmark_report.md`](eval/real_benchmark_report.md) and [`eval/real_benchmark_report.json`](eval/real_benchmark_report.json).*

---

### 2. Deterministic Compliance & Anomaly Test Suite

DocAgent also includes a rule-verification test harness evaluated against 20 curated test scenarios across 5 distinct compliance categories:

```bash
# Run offline compliance rule tests
python eval/run_eval.py --mode offline
```

| Benchmark Metric | Result | Target | Status |
|---|---|---|---|
| **Rule Compliance Accuracy** | `100.0%` (180/180 checks) | `≥ 95.0%` | PASSED |
| **Anomaly Detection Precision** | `1.00` | `≥ 0.90` | PASSED |
| **Anomaly Detection Recall** | `1.00` | `≥ 0.90` | PASSED |
| **Anomaly Detection F1 Score** | `1.00` | `≥ 0.90` | PASSED |
| **Decision Routing Accuracy** | `100.0%` (20/20 invoices) | `≥ 95.0%` | PASSED |
| **Approval Level Routing** | `100.0%` (20/20 invoices) | `≥ 95.0%` | PASSED |

*Full offline evaluation reports: [`eval/eval_report.md`](eval/eval_report.md) and [`eval/eval_report.json`](eval/eval_report.json).*

---

### 3. DeepEval G-Eval Benchmark vs Deterministic Claim Verifier

To evaluate qualitative LLM reasoning and establish benchmark parity with industry standards, DocAgent was evaluated using **DeepEval's G-Eval methodology (LLM-as-a-judge)** on golden enterprise invoices, directly comparing the LLM Judge against DocAgent's deterministic token-span claim verifier:

```bash
# Run the live DeepEval G-Eval benchmark
python eval/run_deepeval_benchmark.py
```

| Benchmark Metric | Result | Target | Status |
|---|---|---|---|
| **Judge Agreement Rate (Det vs G-Eval)** | `100.0%` (5/5 invoices) | `≥ 85.0%` | PASSED |
| **Mean G-Eval Judge Score** | `0.88` / 1.00 (`4.40/5`) | `≥ 0.85` | PASSED |
| **Mean Deterministic Claim Score** | `1.00` / 1.00 | `≥ 0.90` | PASSED |
| **Mean G-Eval Judge Latency** | `4.29s` / document | `≤ 5.0s` | PASSED |
| **Deterministic Verifier CI Latency** | `< 0.001s` (sub-millisecond) | `≤ 0.01s` | PASSED |

*Full DeepEval reports: [`eval/deepeval_benchmark_report.md`](eval/deepeval_benchmark_report.md) and [`eval/deepeval_benchmark_report.json`](eval/deepeval_benchmark_report.json).*

---

### 4. Multi-Invoice Live LLM Extraction Variance Benchmark

To measure non-deterministic AI variance, DocAgent was benchmarked across **15 repeated live extraction runs ($N=5$ runs each at $\text{temp}=0.1$)** across 3 distinct invoice categories (INR consulting, AWS USD cloud, Logitech hardware supplies):

```bash
# Run the live multi-invoice extraction variance benchmark
python eval/run_extraction_variance.py
```

| Tested Invoice Category | Total Agreement Rate | Vendor Exact Match | Vendor Fuzzy Match (≥0.80) | Conf Std Dev (σ) | Status |
|---|:---:|:---:|:---:|:---:|:---:|
| **INR Consulting (`Infosys Limited`)** | `100.0%` (5/5) | `100.0%` | `100.0%` | `σ = 0.0000` | PASSED |
| **USD Cloud Infra (`Amazon Web Services`)** | `100.0%` (5/5) | `100.0%` | `100.0%` | `σ = 0.0000` | PASSED |
| **Hardware Supplies (`Logitech`)** | `100.0%` (5/5) | `100.0%` | `100.0%` | `σ = 0.0000` | PASSED |
| **Downstream Policy Determinism** | `100.0%` (15/15) | — | — | `σ_risk = 0.00` | PASSED |

*Full variance reports: [`eval/extraction_variance_report.md`](eval/extraction_variance_report.md) and [`eval/extraction_variance_report.json`](eval/extraction_variance_report.json).*

---

### 5. Automated CI Test Suite & AI Red-Teaming (84 Tests in CI)

DocAgent enforces a multi-tier automated test suite integrated into **GitHub Actions CI** running 84 automated tests across 14 test modules:

```bash
# Run complete test suite (unit, integration, custom LLM eval, AI safety)
pytest tests/ -v
```

| Evaluation Tier | Metric / Check | Result | Target | Status |
|---|---|---|---|---|
| **Deterministic Grounding** | Golden Cases Faithfulness (Rule-Based Token Verifier) | `100.0%` | `≥ 90.0%` | PASSED |
| **Deterministic Grounding** | Golden Cases Hallucination Rate | `0.00` | `≤ 0.10` | PASSED |
| **Hallucination Injection** | Synthetic Fictitious Field Detection Recall | `100.0%` | `100.0%` | PASSED |
| **Custom Schema & Math** | Completeness & Arithmetic Consistency Score | `0.98` | `≥ 0.85` | PASSED |
| **Adversarial Regression** | 20-Vector Known Attack Suite (Baseline 15% ➔ 0.0%) | `0.00%` (0/20) | `0.00%` | PASSED |
| **Novel Generalization** | 5 Held-Out Attack Vectors (Multilingual, Credit Spoof) | `100.0%` Defended | `≥ 80.0%` | PASSED |
| **AI Safety & Privacy**| PII Redaction (Credit Cards, SSNs, API Keys) | `100.0%` | `100.0%` | PASSED |
| **Automated Pytest** | End-to-End Test Suite Pass Rate | `100.0%` (84/84) | `100.0%` | PASSED |

> **Evaluation Methodology & Architectural Insights:**
> 1. **Rule-Based Grounding vs DeepEval G-Eval LLM Judge:** Rather than introducing a non-deterministic LLM-judge in CI (which costs ~$0.002 per call and suffers from prompt drift), continuous CI verification runs a deterministic, token-span claim-grounding verifier against raw source text ($<1\text{ms}$, $\$0.00$ cost). DeepEval's G-Eval LLM Judge is utilized for pre-release qualitative benchmarking, demonstrating $100.0\%$ concordance on clean invoices. The evaluator was validated via synthetic hallucination injection (injecting fabricated entities and proving $100\%$ detection recall).
> 2. **Multi-Invoice Variance Findings:** Live temperature-sampled testing across distinct invoice categories confirmed $100\%$ numerical total agreement and $100\%$ fuzzy vendor matching, while proving downstream policy scoring remains strictly deterministic ($\sigma_{\text{risk}} = 0.00$).
> 3. **AI Red-Teaming & 20-Vector Regression Suite:** An unconstrained single-reader pipeline showed an initial $15.0\%$ ASR ($3/20$ breaches: Cyrillic homoglyphs, visual-digital deception, and semantic CFO waivers). Multi-layered defenses (Unicode NFKD normalization, Dual-Observer cross-examination, and SQL hash gating) remediated all 3 vulnerabilities, establishing a regression-tested $0.00\%$ ASR ($0/20$). Generalization was confirmed against 5 novel, held-out attack vectors (including multilingual smuggling and negative credit offset tricks).
> 4. **Dual-Observer Cost & Latency Trade-Off:** Observer A (Gemini Flash Vision) + Observer B (GPT-4o-mini text verifier) adds a second model invocation (~$0.0005 total cost, average latency 11.23s). In enterprise accounts payable, fraudulent \$50,000 disbursements represent existential risk; spending a fraction of a cent and ~11s for multi-modal cross-examination delivers an overwhelming safety and compliance ROI. Pre-LLM SHA-256 hash gating completely offsets this by dropping exact duplicates at **$0.00 cost** in sub-2ms.

---

## User Interface & Screenshots

### 1. Document Upload & Processing Dashboard
Upload PDF, Image, or TXT invoices to initiate multi-stage extraction, compliance verification, and routing.

![Upload Dashboard](images/image1.png)

### 2. Extracted Data, Risk Scoring & Anomaly Inspection
Live visual feedback with extracted table breakdown, composite risk gauge, and compliance rule results.

![Extraction & Compliance](images/image2.png)

### 3. Step-by-Step Agent Audit Trail
Transparent observability into every step executed by the LangGraph state machine.

![Agent Audit Trail](images/image3.png)

---

## Technical Decisions & Architecture Rationale

| Decision Area | Technology / Pattern | Engineering Rationale |
|---|---|---|
| **Agent Framework** | LangGraph (StateGraph) | Deterministic state machine, checkpointing/resume capabilities, conditional routing, and granular step observability. |
| **Multi-Modal & Dual Observer** | Gemini Flash Vision + GitHub Models (GPT-4o-mini) | Dual-observer cross-examination (multimodal extraction + verbatim evidence verifier) with automatic failover. |
| **Duplicate Prevention** | SQL Indexing + SHA-256 Fingerprint | Sub-2ms idempotent query over key invoice attributes (`vendor:number`) in PostgreSQL/SQLite + in-memory cache without external broker dependencies. |
| **Human-in-the-Loop** | LangGraph Interrupts | Pauses workflow execution for manager/director sign-off without dropping state; resumes via `/resume/{thread_id}`. |
| **Backend API** | FastAPI | Async I/O, automatic OpenAPI Swagger documentation, dependency injection, and Pydantic validation. |
| **Frontend UI** | Streamlit | Rapid, reactive UI rendering with interactive audit logs, pending review queues, and live analytics. |
| **LLM Evaluation & Safety** | Deterministic Claim-Grounding & Custom G-Eval | Rule-based token grounding against raw text, synthetic hallucination injection tests, 20-attack regression suite, and 5 held-out novel attacks. |
| **CI/CD Quality Gate** | GitHub Actions | Automated linting, 84-test pytest suite, and offline regression benchmark execution on all pushes and PRs. |

---

## Getting Started

### Prerequisites
- Python 3.12+
- Gemini API Key (or GitHub Personal Access Token for GitHub Models)
- Docker & Docker Compose *(optional, for containerized execution)*

---

### Option A: Running with Docker (Recommended)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ayushcodes27/doc-agent.git
   cd doc-agent
   ```

2. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env and supply your GEMINI_API_KEY (or GITHUB_TOKEN)
   ```

3. **Launch the entire stack:**
   ```bash
   docker-compose up --build
   ```

4. **Access the services:**
   - **Streamlit UI:** [http://localhost:8501](http://localhost:8501)
   - **FastAPI Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
   - **PostgreSQL:** `localhost:5432`

---

### Option B: Running Locally (Without Docker)

1. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   # Windows (PowerShell):
   .venv\Scripts\Activate.ps1
   # macOS/Linux:
   source .venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Ensure your GEMINI_API_KEY / GITHUB_TOKEN are set in .env
   ```

4. **Start the FastAPI backend server:**
   ```bash
   uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
   ```

5. **In a separate terminal, launch the Streamlit frontend:**
   ```bash
   streamlit run ui/app.py
   ```

---

## Running Unit & Integration Tests

The test suite covers data models, agent nodes, validation rules, anomaly detection, deduplication, database persistence, and the complete LangGraph workflow.

```bash
# Run all 75 unit and integration tests
pytest -v

# Run real-world benchmark suite
python eval/run_real_benchmark.py

# Run offline compliance rule tests
python eval/run_eval.py --mode offline
```

---

## Repository Structure

```
doc-agent/
├── agent/       # LangGraph StateGraph workflow, nodes, & human-in-the-loop logic
├── api/         # FastAPI REST service (/process, /resume, /invoices, /analytics)
├── data/        # Real procurement datasets (USASpending.gov) & benchmark invoices
├── db/          # SQLAlchemy 2.0 persistence layer, ORM models, & repository CRUD
├── eval/        # Benchmark runners, ground truth datasets, and evaluation reports
├── tools/       # Multi-modal extractors, 9-rule validator, anomaly & dedup engines
├── ui/          # Streamlit frontend (Document ingestion, review queue, analytics)
├── scripts/     # Ingestion, seeding, and downloading utilities
├── tests/       # Pytest unit & integration test suite (75 tests)
├── config.py    # Environment configuration & LLM provider settings
└── docker-compose.yml # Container orchestration (API, UI, PostgreSQL)
```

---

## License
Distributed under the MIT License. See `LICENSE` for more information.
