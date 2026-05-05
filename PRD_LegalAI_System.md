# Product Requirements Document (PRD)
## Agentic Multi-Agent Legal Case Analysis System
### "Empowering Judicial India" — Team 14, NMIT

---

## Document Metadata

| Field | Value |
|---|---|
| Project Name | Empowering Judicial India: AI-Powered Multi-Agent System for Legal Research |
| Team | Mridul Tiwari, Yogesh Kumar Singh, Aaditya Negi, Sankalp Vyas |
| Institution | Nitte Meenakshi Institute of Technology, Bengaluru |
| Guide | Dr. Manoj Kumar M V, Mr. Prashanth B S |
| Industry Partner | Rectopage LLP, Bengaluru |
| Version | 1.0 |
| Date | April 2026 |
| Status | Active Development |

---

## 1. Executive Summary

This system is a **web-based, multi-agent AI platform** for legal case research and precedent discovery, targeting the Indian judicial context. It replaces keyword-based search with a pipeline of specialized autonomous agents that collaboratively retrieve, rank, debate, and explain relevant Supreme Court judgments.

The frontend static demo is already built. This PRD governs all **backend, agent orchestration, data pipeline, and API layers** while ensuring the live system connects seamlessly to the existing frontend.

**Core dataset:** Indian Supreme Court Judgments (1950–2025), hosted on AWS Open Data Registry at `s3://indian-supreme-court-judgments/`. Available as PDFs + JSON metadata + Parquet structured metadata.

---

## 2. Problem Statement

Legal professionals in India face:
- Keyword-based systems (like eCourts) that return high-noise, low-relevance results
- No contextual prioritization by judicial hierarchy, citation authority, or factual similarity
- No explainability in why a case was deemed relevant
- Inability to discover precedent chains across decades of Supreme Court judgments

**This system solves all four.**

---

## 3. Goals & Non-Goals

### Goals
- Replace the static hardcoded frontend demo with a live, API-backed system
- Ingest, parse, and index Indian Supreme Court judgments from AWS S3
- Build a multi-agent backend that processes legal queries end-to-end
- Return explainable, ranked results with citation justification
- Expose clean REST API endpoints consumed by the existing frontend

### Non-Goals
- This system does NOT provide legal advice or replace lawyers
- It does NOT cover High Court or District Court judgments (scope limited to Supreme Court)
- It does NOT handle real-time eCourts scraping (uses the static AWS dataset)
- It does NOT support case filing or document submission workflows

---

## 4. System Architecture Overview

```
User Query (Frontend)
        │
        ▼
┌───────────────────────────────────────────────┐
│              FastAPI Gateway Layer             │
│  /api/query  /api/agents/status  /api/cases   │
└───────────────────────┬───────────────────────┘
                        │
        ┌───────────────▼───────────────┐
        │     Scheduler Agent (Orchestrator)     │
        │  Controls agent DAG execution          │
        └──┬────────┬────────┬──────────┘
           │        │        │
    ┌──────▼──┐ ┌───▼────┐ ┌─▼──────────┐
    │ Query   │ │Retriever│ │ Precedent  │
    │ Planner │ │ Agent   │ │ Weighting  │
    │ Agent   │ │(FAISS)  │ │ Agent      │
    └──────┬──┘ └───┬────┘ └──────┬─────┘
           │        │             │
           └────────▼─────────────┘
                    │
           ┌────────▼────────┐
           │   Debate Agent  │
           │ (Claim/Counter/ │
           │   Synthesis)    │
           └────────┬────────┘
                    │
           ┌────────▼────────┐
           │  Evaluator Agent│
           │ (P@K, nDCG, MRR)│
           └────────┬────────┘
                    │
           ┌────────▼────────┐
           │ Structured JSON │
           │ Response (API)  │
           └─────────────────┘
                    │
             Frontend Display
```

---

## 5. Data Pipeline (Corpus Preparation)

### 5.1 Dataset

**Source:** `s3://indian-supreme-court-judgments/` (no AWS credentials needed)

**Structure:**
```
s3://indian-supreme-court-judgments/
├── data/
│   ├── pdf/year={YEAR}/        # Individual PDFs
│   └── tar/year={YEAR}/
│       └── english/
│           ├── english.tar      # Bulk judgments
│           └── english.index.json  # Index without downloading tar
├── metadata/
│   ├── json/year={YEAR}/       # Per-judgment metadata JSON
│   └── parquet/year={YEAR}/    # Structured metadata (queryable)
```

**Access (no AWS account required):**
```bash
aws s3 ls s3://indian-supreme-court-judgments/data/tar/ --no-sign-request
aws s3 cp s3://indian-supreme-court-judgments/data/tar/year=2023/english/english.index.json . --no-sign-request
```

### 5.2 Ingestion Pipeline

**Script:** `scripts/ingest/ingest_pipeline.py`

Steps:
1. **Download index files** for target years (start with 2015–2024 for manageable corpus)
2. **Download metadata Parquet** files for fast structured access
3. **Extract PDF text** using `pdfplumber` → store as `.txt` per judgment
4. **Segment text** into 4 structured sections:
   - `facts` — Background facts of the case
   - `issues` — Legal questions raised
   - `reasoning` — Court's analysis
   - `outcome` — Final decision/order
5. **Generate embeddings** using `google/gemini-embedding-exp-03-07` (or `text-embedding-004` as fallback) → store vectors
6. **Build FAISS index** with metadata mapping (case_id → FAISS index position)
7. **Store** everything in PostgreSQL (metadata) + FAISS flat file (vectors)

### 5.3 Metadata Schema (PostgreSQL: `cases` table)

```sql
CREATE TABLE cases (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id         VARCHAR(100) UNIQUE NOT NULL,   -- e.g. "2023_SC_1234"
    year            INTEGER NOT NULL,
    title           TEXT NOT NULL,
    bench           TEXT,                            -- Judges
    petitioner      TEXT,
    respondent      TEXT,
    decision_date   DATE,
    disposal_nature VARCHAR(100),                    -- Allowed / Dismissed / etc.
    acts_sections   TEXT[],                          -- Referenced legislation
    citation        VARCHAR(200),                    -- e.g. "AIR 2023 SC 4567"
    full_text_path  TEXT,                            -- Path to extracted .txt
    embedding_id    INTEGER,                         -- FAISS index position
    facts_text      TEXT,
    issues_text     TEXT,
    reasoning_text  TEXT,
    outcome_text    TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE citations (
    citing_case_id  VARCHAR(100) REFERENCES cases(case_id),
    cited_case_id   VARCHAR(100) REFERENCES cases(case_id),
    citation_count  INTEGER DEFAULT 1,
    PRIMARY KEY (citing_case_id, cited_case_id)
);
```

---

## 6. Agent Specifications

### 6.1 Query Planner Agent

**Responsibility:** Parse and decompose the user's natural language legal query.

**Input:** Raw user query string

**Output (JSON):**
```json
{
  "query_id": "uuid",
  "original_query": "...",
  "legal_domain": "constitutional|civil|criminal|tax|...",
  "extracted_issues": ["issue 1", "issue 2"],
  "extracted_facts": "...",
  "target_outcome": "...",
  "temporal_hint": "recent|historical|any",
  "reformulated_queries": ["query variant 1", "query variant 2"],
  "confidence": 0.87
}
```

**Implementation:**
- Call Gemini API with structured prompt
- Force JSON output via `response_mime_type: "application/json"`
- No memory across queries (stateless)

### 6.2 Retriever Agent

**Responsibility:** Perform hybrid semantic + keyword retrieval from FAISS + Postgres.

**Input:** Query Planner output

**Process:**
1. Generate query embedding via Gemini Embedding API
2. FAISS similarity search → top-K candidates (default K=50)
3. BM25 keyword search on full text (via PostgreSQL `tsvector`)
4. Merge results using Reciprocal Rank Fusion (RRF)

**Output:** List of `{case_id, faiss_score, bm25_score, rrf_score}` for top-50 candidates

**Config:**
```python
FAISS_TOP_K = 50
BM25_TOP_K = 50
FINAL_CANDIDATES = 50  # after RRF merge
```

### 6.3 Precedent Weighting Agent

**Responsibility:** Re-rank candidates based on legal authority signals.

**Signals (weighted):**
| Signal | Weight | Source |
|---|---|---|
| Citation count (how often case is cited) | 0.35 | `citations` table |
| Bench size (5-judge Constitution Bench > 3-judge > 2-judge) | 0.20 | metadata |
| Recency (newer = higher unless overruled) | 0.15 | `decision_date` |
| Factual alignment (issues overlap) | 0.20 | Gemini comparison |
| Same legal domain | 0.10 | Query Planner output |

**Output:** Re-ranked list with `authority_score` appended, top-20 returned

### 6.4 Debate Agent

**Responsibility:** Run a structured multi-round deliberation to challenge the top-ranked results.

**Protocol (3 rounds max):**

**Round 1 — Claims:** For each of top-5 results, Agent A makes the case for relevance.

**Round 2 — Counterclaims:** Agent B challenges each claim (are there stronger precedents? Was the case overruled? Is the factual context different?).

**Round 3 — Synthesis:** Moderator sub-agent produces a final consensus ranking with rationale.

**Implementation:** Each "agent" is a distinct Gemini API call with a specific role prompt. This is simulated multi-agent deliberation — no actual concurrency required; it runs sequentially with state passed forward.

**Output:**
```json
{
  "debate_rounds": [...],
  "final_ranking": ["case_id_1", "case_id_3", "case_id_2", ...],
  "consensus_rationale": "Case X is ranked highest because...",
  "disagreement_flags": ["case_id_4 was disputed due to overruling in 2019"]
}
```

### 6.5 Scheduler Agent

**Responsibility:** Orchestrate the entire pipeline and decide whether to iterate.

**Decision logic:**
```python
if evaluator_confidence < CONFIDENCE_THRESHOLD (0.75):
    trigger_requery = True
    expand_k = True
elif debate_disagreement_rate > 0.3:
    run_extra_debate_round = True
else:
    terminate = True
```

**Max iterations:** 3 (prevent infinite loops)

**Output:** Pipeline execution log with timing, iteration count, final status

### 6.6 Evaluator Agent

**Responsibility:** Score result quality using retrieval metrics.

**Metrics computed:**
- `Precision@K` (K=5, 10)
- `nDCG@K` (normalized Discounted Cumulative Gain)
- `MRR` (Mean Reciprocal Rank)
- `Coverage` (% of query issues addressed by returned cases)

**Evaluation data:** A manually curated golden set of 100 test queries with known relevant cases (to be built during development).

---

## 7. API Specification (FastAPI)

### Base URL: `/api/v1`

### Endpoints

#### `POST /api/v1/query`
Submit a legal query for analysis.

**Request:**
```json
{
  "query": "Right to privacy as fundamental right under Article 21",
  "filters": {
    "year_from": 2000,
    "year_to": 2024,
    "domain": "constitutional"
  },
  "options": {
    "top_k": 10,
    "enable_debate": true,
    "explanation_detail": "full"
  }
}
```

**Response:**
```json
{
  "query_id": "uuid",
  "status": "complete",
  "processing_time_ms": 4230,
  "results": [
    {
      "rank": 1,
      "case_id": "2017_SC_4234",
      "title": "Justice K.S. Puttaswamy vs Union of India",
      "year": 2017,
      "citation": "AIR 2017 SC 4161",
      "bench": "9-Judge Constitution Bench",
      "decision_date": "2017-08-24",
      "disposal_nature": "Allowed",
      "relevance_score": 0.941,
      "authority_score": 0.887,
      "final_score": 0.921,
      "matched_issues": ["Right to Privacy", "Article 21", "Fundamental Rights"],
      "snippet": "The right to privacy is protected as an intrinsic part of the right to life...",
      "explanation": "This 9-judge bench judgment directly establishes privacy as a fundamental right under Article 21, which is the precise legal issue in your query. It has been cited in 340+ subsequent judgments and has the highest authority score.",
      "debate_notes": "Agent consensus: unanimously ranked #1 with no disputes.",
      "acts_sections": ["Constitution of India - Article 21", "Article 19(1)(a)"]
    }
  ],
  "agent_trace": {
    "query_planner": {...},
    "retriever": {"faiss_hits": 50, "bm25_hits": 38, "after_rrf": 50},
    "precedent_weighting": {"reranked": 20},
    "debate": {"rounds": 2, "disputes": 1},
    "scheduler": {"iterations": 1},
    "evaluator": {"precision_at_5": 0.8, "ndcg_at_10": 0.74, "mrr": 0.91}
  }
}
```

#### `GET /api/v1/cases/{case_id}`
Retrieve full details of a single case.

#### `GET /api/v1/cases/{case_id}/similar`
Get cases similar to a given case (powers "Related Cases" UI).

#### `GET /api/v1/query/{query_id}/status`
Poll status of a running query (for streaming/async UI).

#### `GET /api/v1/stats`
System statistics: total cases indexed, years covered, query count.

#### `GET /api/v1/health`
Health check for all services (DB, FAISS, Gemini).

---

## 8. Frontend Integration (Replacing Static Demo)

### What to Remove
- All hardcoded `const MOCK_RESULTS = [...]` arrays
- Static case cards with fixed data
- Any `setTimeout` simulating "loading"
- Hardcoded agent trace/workflow visualizations with fake data

### What to Wire Up
Replace every static data source with API calls:

| Frontend Component | Old (Static) | New (API) |
|---|---|---|
| Search results list | `MOCK_RESULTS` array | `POST /api/v1/query` |
| Case detail modal | Hardcoded object | `GET /api/v1/cases/{id}` |
| "Related cases" section | Static list | `GET /api/v1/cases/{id}/similar` |
| Agent workflow viz | Fake step-through | Real `agent_trace` from response |
| Stats/metrics display | Hardcoded numbers | `GET /api/v1/stats` |
| Loading states | `setTimeout` | Actual API latency + loading spinner |

### Frontend Contract Rules
1. All API calls must go through a central `apiClient.ts` (or equivalent) — never raw `fetch` scattered across components.
2. Error states must be handled: show user-friendly messages for timeout, empty results, and API errors.
3. The `agent_trace` object powers the workflow visualization — the frontend should render it dynamically from the response, not hardcode steps.
4. Use optimistic UI for search — show skeleton loaders immediately on submit.
5. Debate logs (`debate_rounds`) should be toggleable — hidden by default, expandable for researchers.

---

## 9. Tech Stack

### Backend
| Layer | Technology | Rationale |
|---|---|---|
| API Framework | FastAPI (Python) | Async support, auto-docs, Pydantic validation |
| LLM | Google Gemini 1.5 Flash / Pro | Budget-efficient, large context window for legal docs |
| Embeddings | Gemini `text-embedding-004` | Consistent with LLM vendor, strong multilingual |
| Vector DB | FAISS (local) | No infra cost, sufficient for <500K vectors |
| Relational DB | PostgreSQL 15 | Full-text search via `tsvector`, JSON support |
| Task Queue | Celery + Redis | Async query processing for long-running agent pipelines |
| Caching | Redis | Cache embeddings and frequent queries |

### Data
| Component | Technology |
|---|---|
| PDF Extraction | `pdfplumber` + `pypdf` fallback |
| Dataset Access | `boto3` with `--no-sign-request` (public S3) |
| Bulk download | `aws s3 cp` / `sync` |
| Parquet reading | `pandas` + `pyarrow` |

### Infrastructure
| Component | Technology |
|---|---|
| Hosting | Render Pro (as budgeted) |
| Object Storage | S3 (source data only, no egress cost via same-region) |
| Container | Docker + docker-compose for local dev |
| Environment | `.env` files, Pydantic Settings |

---

## 10. Project Structure

```
legal-ai-system/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app entrypoint
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── query.py           # /query endpoint
│   │   │   │   ├── cases.py           # /cases endpoints
│   │   │   │   └── system.py          # /health, /stats
│   │   ├── agents/
│   │   │   ├── base_agent.py          # Abstract Agent class
│   │   │   ├── query_planner.py       # Query Planner Agent
│   │   │   ├── retriever.py           # Retriever Agent
│   │   │   ├── precedent_weighter.py  # Precedent Weighting Agent
│   │   │   ├── debate.py              # Debate Agent
│   │   │   ├── scheduler.py           # Scheduler Agent (Orchestrator)
│   │   │   └── evaluator.py           # Evaluator Agent
│   │   ├── core/
│   │   │   ├── config.py              # Settings (Pydantic BaseSettings)
│   │   │   ├── database.py            # Postgres connection (SQLAlchemy async)
│   │   │   ├── faiss_index.py         # FAISS load/search wrapper
│   │   │   ├── gemini_client.py       # Centralized Gemini API calls
│   │   │   └── exceptions.py          # Custom exception classes
│   │   ├── models/
│   │   │   ├── case.py                # SQLAlchemy ORM models
│   │   │   ├── query.py               # Pydantic request/response schemas
│   │   │   └── agent.py               # Agent I/O schemas
│   │   └── services/
│   │       ├── search_service.py      # Orchestrates retrieval
│   │       ├── ranking_service.py     # RRF + scoring logic
│   │       └── explanation_service.py # Generates human-readable rationale
│   ├── scripts/
│   │   ├── ingest/
│   │   │   ├── download_dataset.py    # S3 download script
│   │   │   ├── extract_text.py        # PDF → text
│   │   │   ├── segment_text.py        # Text → facts/issues/reasoning/outcome
│   │   │   ├── build_embeddings.py    # Text → vectors
│   │   │   └── build_faiss_index.py   # Vectors → FAISS index
│   │   └── eval/
│   │       ├── golden_set.json        # 100 curated test queries
│   │       └── run_eval.py            # Evaluation harness
│   ├── tests/
│   │   ├── unit/
│   │   │   ├── test_agents/
│   │   │   └── test_services/
│   │   └── integration/
│   │       └── test_api.py
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── requirements.txt
├── frontend/                          # Existing frontend (do NOT restructure)
│   └── ...                            # Wire up API calls only
├── data/                              # Local data storage (gitignored)
│   ├── raw/                           # Downloaded PDFs/metadata
│   ├── processed/                     # Extracted text per case
│   └── index/                         # FAISS index files
├── .env.example
└── README.md
```

---

## 11. Data Flow — End to End

```
1. User types query in frontend search bar
2. Frontend sends POST /api/v1/query with query + filters
3. FastAPI receives → validates via Pydantic → enqueues Celery task
4. Scheduler Agent starts pipeline:
   a. Query Planner → parse query → extract issues/facts/domain
   b. Retriever Agent → embed query → FAISS search (top-50) + BM25 (top-50) → RRF merge (top-50)
   c. Precedent Weighting Agent → apply authority scores → top-20
   d. Debate Agent → 3-round deliberation → final top-10 with rationale
   e. Evaluator Agent → compute P@K, nDCG, MRR
   f. Scheduler → check confidence → iterate if needed
5. Final result assembled → stored in Redis with query_id TTL=1h
6. API returns structured JSON response
7. Frontend receives → renders results, agent trace, metrics
8. Static mock data is NOT used anywhere in this flow
```

---

## 12. Evaluation Strategy

### Offline Evaluation
- Golden set: 100 hand-curated (query, relevant_case_ids) pairs
- Baseline: BM25-only retrieval
- Comparison: Full multi-agent system vs. baseline
- Target: >15% nDCG@10 improvement over BM25 baseline

### Online Evaluation (Post-deployment)
- Track click-through rate on results
- Collect user "thumbs up/down" feedback per result
- Log query latency by agent stage

---

## 13. Performance & Constraints

| Metric | Target |
|---|---|
| Query end-to-end latency (P95) | < 8 seconds |
| FAISS search latency | < 200ms for 500K vectors |
| Gemini API calls per query | ≤ 12 (across all agents) |
| Corpus size (initial) | 2015–2024 judgments (~50K–80K cases) |
| FAISS index size | ~4GB for 500K × 768-dim embeddings |
| Max debate rounds | 3 (hard cap) |
| Scheduler max iterations | 3 (hard cap) |
| API rate limit | 100 req/min per IP |

---

## 14. Security & Compliance

- Gemini API key stored in environment variable, never in code
- No user PII collected (queries are anonymous unless user registers)
- All case data is publicly available (eCourts / AWS Open Data)
- Rate limiting on all endpoints (FastAPI middleware)
- CORS configured to allow only the frontend domain in production

---

## 15. Development Phases

### Phase 1 — Data Foundation (Weeks 1–3)
- [ ] Set up PostgreSQL + FAISS infrastructure
- [ ] Write and test ingestion pipeline (start with 2020–2024, ~10K cases)
- [ ] Validate text extraction quality on sample PDFs
- [ ] Build initial FAISS index and test basic similarity search

### Phase 2 — Core Agents (Weeks 4–7)
- [ ] Implement Query Planner Agent with Gemini
- [ ] Implement Retriever Agent (FAISS + BM25 + RRF)
- [ ] Implement Precedent Weighting Agent
- [ ] Build Scheduler Agent orchestration loop
- [ ] Expose `POST /api/v1/query` endpoint

### Phase 3 — Debate & Evaluation (Weeks 8–10)
- [ ] Implement Debate Agent (3-round protocol)
- [ ] Implement Evaluator Agent with P@K / nDCG / MRR
- [ ] Build golden evaluation set (100 queries)
- [ ] Run baseline vs. system comparison

### Phase 4 — Frontend Integration (Weeks 10–12)
- [ ] Remove all hardcoded mock data from frontend
- [ ] Wire all components to live API endpoints
- [ ] Implement `apiClient.ts` abstraction
- [ ] Test end-to-end with real queries

### Phase 5 — Hardening & Deployment (Weeks 12–14)
- [ ] Docker containerization
- [ ] Deploy to Render Pro
- [ ] Load testing + latency optimization
- [ ] Final evaluation run + documentation

---

## 16. Open Questions & Decisions Pending

1. **Embedding model choice:** Gemini `text-embedding-004` vs `gemini-embedding-exp-03-07` — test both for legal domain quality.
2. **Segmentation quality:** Rule-based regex segmentation (facts/issues/reasoning/outcome) vs. Gemini-assisted segmentation — budget vs. accuracy tradeoff.
3. **Citation graph:** Build full citation network (expensive) vs. use citation count only (simpler) — start simple, extend later.
4. **Multi-language:** Dataset has regional language judgments. Scope to English only for MVP.
5. **Streaming responses:** Consider Server-Sent Events (SSE) for streaming agent progress to frontend — improves UX for long queries.

---

## 17. Glossary

| Term | Definition |
|---|---|
| FAISS | Facebook AI Similarity Search — vector similarity library |
| BM25 | Best Match 25 — probabilistic keyword ranking algorithm |
| RRF | Reciprocal Rank Fusion — algorithm to merge multiple ranked lists |
| nDCG@K | Normalized Discounted Cumulative Gain at K — measures ranking quality |
| MRR | Mean Reciprocal Rank — measures how high the first relevant result appears |
| P@K | Precision at K — fraction of top-K results that are relevant |
| Constitution Bench | Indian SC bench of 5+ judges for constitutional questions |
| Precedent | A past judgment that guides future decisions (stare decisis) |

---

*End of PRD — v1.0*
