# Empowering Judicial India — User Stories & Feature List

> **Project:** AI-Powered Multi-Agent System for Enhancing Legal Research and Access to Justice  
> **Team:** Mridul Tiwari, Yogesh Kumar Singh, Aaditya Negi, Sankalp Vyas  
> **Institution:** Nitte Meenakshi Institute of Technology  

---

## Table of Contents

1. [User Personas](#user-personas)
2. [User Stories](#user-stories)
3. [Feature List](#feature-list)
4. [Non-Functional Requirements](#non-functional-requirements)

---

## User Personas

| Persona | Role | Primary Goal |
|---|---|---|
| **Advocate Arjun** | Practicing lawyer | Quickly find relevant precedents for an ongoing case |
| **Priya** | Law student / researcher | Study case law and understand precedential relationships |
| **Judge Sharma** | Judicial officer | Cross-verify cited precedents and assess their authority |
| **Citizen Ramesh** | Common citizen | Understand if similar cases have been fought and won |
| **Legal Aid Worker** | NGO / legal aid | Help underserved clients access justice efficiently |

---

## User Stories

### Epic 1 — Legal Query Input

**US-01**  
*As a lawyer, I want to describe my case in plain natural language so that I don't need to know specific legal keywords or case numbers to start a search.*

**Acceptance Criteria:**
- System accepts free-text input of at least 500 characters
- Input can include facts, issues, and desired outcomes
- System provides a confirmation summary of what it understood from the query

---

**US-02**  
*As a law student, I want to upload a case document (PDF or text) so that the system can extract facts and issues automatically.*

**Acceptance Criteria:**
- Accepts PDF and plain text document uploads
- Automatically segments uploaded documents into facts, issues, reasoning, and outcomes
- Shows a preview of extracted segments before processing

---

**US-03**  
*As a legal researcher, I want to refine my query after seeing initial results so that I can narrow down or broaden the scope of the search.*

**Acceptance Criteria:**
- Users can add filters (court level, year range, jurisdiction) after an initial result
- Refined queries trigger a new retrieval cycle without restarting the full session
- Each refinement is logged for transparency

---

### Epic 2 — Case Retrieval & Similarity

**US-04**  
*As a lawyer, I want to see the most relevant precedents ranked by contextual similarity — not just keyword overlap — so that I can trust the results are genuinely useful.*

**Acceptance Criteria:**
- Results are ranked by a hybrid score (semantic similarity + structural alignment + precedential weight)
- Each result shows a relevance score breakdown
- Results differ meaningfully from a plain keyword search

---

**US-05**  
*As a judge, I want to see the citation strength of a retrieved case so that I can assess how authoritative a precedent is within the judicial hierarchy.*

**Acceptance Criteria:**
- Each case shows citation count and citing court levels (Supreme Court, High Court, etc.)
- Precedential weight is displayed as a score with an explanation
- Cases from higher courts are visually distinguished

---

**US-06**  
*As a legal aid worker, I want results sorted by outcome similarity so that I can quickly find cases where the verdict favored a party in a similar situation to my client.*

**Acceptance Criteria:**
- Results can be filtered/sorted by outcome type (in favor of petitioner, respondent, etc.)
- Outcome alignment is shown as part of the similarity breakdown
- Cases with identical or highly similar outcomes are highlighted

---

### Epic 3 — Multi-Agent Reasoning & Debate

**US-07**  
*As a researcher, I want to see why the system ranked a case highly so that I can validate the reasoning rather than blindly trusting an AI.*

**Acceptance Criteria:**
- Every result includes an explainability panel showing which agent contributed what
- Debate logs (claim → counterclaim → synthesis) are accessible per result
- Reasoning is expressed in plain, readable language

---

**US-08**  
*As a lawyer, I want the system to run multiple validation rounds on ambiguous queries so that the final results are more refined and reliable.*

**Acceptance Criteria:**
- The Scheduler automatically triggers additional retrieval cycles when confidence is low
- Users can see how many iterations were run and why
- Final results are marked with a confidence level

---

**US-09**  
*As a legal professional, I want competing agent opinions to be surfaced when agents disagree so that I'm aware of alternative interpretations of my query.*

**Acceptance Criteria:**
- Disagreement between agents is flagged in the UI
- Both the majority and minority agent positions are shown
- User can choose which perspective to prioritize for further exploration

---

### Epic 4 — Precedent Mapping & Graph View

**US-10**  
*As a law student, I want to see a visual map of how retrieved cases cite each other so that I understand the precedential relationships between cases.*

**Acceptance Criteria:**
- A graph visualization shows nodes (cases) and edges (citations)
- Node size or color reflects court hierarchy or citation frequency
- Clicking a node opens the case summary

---

**US-11**  
*As a researcher, I want to trace the evolution of a legal principle across multiple cases over time so that I can write a structured literature review or legal argument.*

**Acceptance Criteria:**
- Cases can be sorted and filtered by date
- A timeline view shows how a particular legal issue has evolved
- Exported timeline is available in PDF or CSV

---

### Epic 5 — Explainability & Transparency

**US-12**  
*As a legal professional, I want every recommendation to be accompanied by citation-backed justifications so that I can use the output directly in my legal brief.*

**Acceptance Criteria:**
- All recommendations reference the source case with court, date, and citation
- Justification text is formatted for direct inclusion in a legal document
- Users can copy individual justifications with one click

---

**US-13**  
*As a researcher, I want access to the full intermediate reasoning logs of all agents so that I can audit the system's decision-making for academic purposes.*

**Acceptance Criteria:**
- Full agent logs are downloadable as structured JSON or plain text
- Logs include timestamps, agent IDs, inputs, outputs, and confidence scores
- Log viewer is available within the UI

---

### Epic 6 — Frontend Interface

**US-14**  
*As any user, I want a clean and simple web interface so that I can use the system without any technical training.*

**Acceptance Criteria:**
- Query input, results panel, and reasoning panel are clearly separated
- The system works on desktop and tablet browsers
- No login required for basic search (authentication optional for saved sessions)

---

**US-15**  
*As a lawyer in a time-sensitive situation, I want the system to show me results progressively as agents complete their work so that I don't have to wait for the entire pipeline to finish.*

**Acceptance Criteria:**
- Initial FAISS retrieval results are shown within 5 seconds
- Enriched results with scores and debate logs are populated progressively
- A progress indicator shows which agent is currently running

---

**US-16**  
*As a citizen with limited legal knowledge, I want a plain-language summary of retrieved cases so that I can understand the gist of a judgment without reading the full text.*

**Acceptance Criteria:**
- Each result includes a 3–5 sentence plain-language summary
- Legal jargon in summaries is explained with tooltips
- A "Simplify further" button is available for extra clarity

---

### Epic 7 — Evaluation & Metrics

**US-17**  
*As a researcher, I want to benchmark the system against baseline retrieval models so that I can quantify the improvement of the multi-agent approach.*

**Acceptance Criteria:**
- System computes Precision@K, nDCG@K, and MRR against a BM25 and embedding-only baseline
- Evaluation results are displayed in a comparison dashboard
- Benchmark datasets and evaluation scripts are documented

---

---

## Feature List

### Core Features

| ID | Feature | Description | Priority |
|---|---|---|---|
| F-01 | Natural Language Query Input | Free-text case query with intent parsing | P0 |
| F-02 | Document Upload & Parsing | Upload PDF/text case documents; auto-segment into facts, issues, reasoning, outcomes | P0 |
| F-03 | FAISS Semantic Retrieval | Vector-indexed retrieval of legally relevant cases using embeddings | P0 |
| F-04 | Hybrid Similarity Score | Combined score from cosine similarity, structural alignment, and citation weight | P0 |
| F-05 | Precedential Authority Weighting | Score cases by judicial hierarchy level and citation frequency | P0 |
| F-06 | Multi-Agent Architecture | Planner, Retriever, Similarity, Mapping, Debate, Evaluator, and Scheduler agents | P0 |
| F-07 | Debate Mechanism | Claim → counterclaim → synthesis rounds between agents with confidence adjustment | P0 |
| F-08 | Adaptive Scheduler | Dynamically triggers additional retrieval cycles based on confidence and disagreement flags | P0 |
| F-09 | Ranked Result List | Sorted list of precedents with relevance scores and outcome alignment | P0 |
| F-10 | Explainability Panel | Per-result breakdown of why it was recommended, with agent contributions | P0 |

### Secondary Features

| ID | Feature | Description | Priority |
|---|---|---|---|
| F-11 | Citation Graph Visualization | Interactive node-edge graph showing citation relationships between cases | P1 |
| F-12 | Timeline View | Chronological view of how legal principles evolved across cases | P1 |
| F-13 | Query Refinement | Post-result filters for court level, jurisdiction, year range, and outcome type | P1 |
| F-14 | Plain-Language Summaries | AI-generated 3–5 sentence summaries of each retrieved case | P1 |
| F-15 | Agent Log Viewer | In-UI viewer and downloader for full intermediate agent reasoning logs | P1 |
| F-16 | Real-Time Workflow Visualization | Live view of which agent is active, progress indicator, and partial results | P1 |
| F-17 | Disagreement Flagging | UI indicator when agents disagree; shows both majority and minority positions | P1 |

### Evaluation & Research Features

| ID | Feature | Description | Priority |
|---|---|---|---|
| F-18 | Retrieval Metric Dashboard | Displays Precision@K, nDCG@K, and MRR scores | P1 |
| F-19 | Baseline Comparison | Side-by-side comparison of multi-agent results vs. BM25 and embedding-only retrieval | P1 |
| F-20 | Structured JSON Export | Export results, reasoning, and logs in structured JSON format | P2 |
| F-21 | PDF / CSV Export | Export result lists, timelines, and comparison reports | P2 |
| F-22 | Benchmark Dataset Integration | Pluggable evaluation dataset support for reproducible benchmarking | P2 |

### Infrastructure & Corpus Features

| ID | Feature | Description | Priority |
|---|---|---|---|
| F-23 | Legal Corpus Ingestion Pipeline | Automated collection, cleaning, and metadata tagging of public Indian case law | P0 |
| F-24 | Embedding Generation & FAISS Indexing | Batch embedding pipeline with FAISS index build and update | P0 |
| F-25 | Structured Agent Communication | JSON-based inter-agent messaging protocol | P0 |
| F-26 | Traceability Logging | All intermediate steps logged with timestamps, agent IDs, and confidence scores | P0 |
| F-27 | Gemini API Integration | Use of Gemini LLM for query planning, debate, and summarization steps | P0 |

---

## Non-Functional Requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-01 | Initial retrieval response time | ≤ 5 seconds for FAISS retrieval |
| NFR-02 | Full pipeline completion time | ≤ 60 seconds for standard queries |
| NFR-03 | Retrieval quality (Precision@10) | Measurably higher than BM25 baseline |
| NFR-04 | System availability | 99% uptime on Render Pro deployment |
| NFR-05 | Explainability | 100% of results include a human-readable justification |
| NFR-06 | Ethical compliance | System operates in decision-support mode only; no legal advisory automation |
| NFR-07 | Scalability | Architecture supports corpus growth without full re-indexing |
| NFR-08 | Transparency | All agent reasoning steps are logged and accessible |
| NFR-09 | Browser compatibility | Works on Chrome, Firefox, Edge (desktop and tablet) |

---

*Document generated from the IEI Student Research Project Proposal — Batch 14, Nitte Meenakshi Institute of Technology.*