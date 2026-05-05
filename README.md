# Verdicto — AI-Powered Multi-Agent Legal Research Platform

> **Empowering Judicial India** — A multi-agent AI system for Indian Supreme Court judgment research and precedent discovery.

---

## Architecture

```
Frontend (React/Vite)  →  FastAPI Backend  →  PostgreSQL + FAISS + Gemini
                                ↓
                          Agent Pipeline:
                    QueryPlanner → Retriever → PrecedentWeighter → Debate → Evaluator
                                ↑
                          Scheduler (Orchestrator, max 3 iterations)
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 18+
- Python 3.11+
- A Google Gemini API key

### 1. Environment Setup
```bash
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### 2. Start Infrastructure
```bash
docker-compose up db redis -d
```

### 3. Run Database Migrations
```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
```

### 4. Start the Backend
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### 5. Start the Frontend
```bash
cd Frontend/webapp
npm install
npm run dev
```

### 6. Open the App
Navigate to `http://localhost:5173`

---

## Data Ingestion Pipeline

Run these scripts to populate the corpus:

```bash
cd backend

# 1. Download metadata from S3
python -m scripts.ingest.download_dataset --year-from 2020 --year-to 2024

# 2. Extract text from PDFs
python -m scripts.ingest.extract_text --input-dir ./data/raw/pdfs --output-dir ./data/processed

# 3. Segment into facts/issues/reasoning/outcome
python -m scripts.ingest.segment_text --input-dir ./data/processed --output-dir ./data/processed/segmented

# 4. Generate embeddings
python -m scripts.ingest.build_embeddings --input-dir ./data/processed/segmented --output-dir ./data/embeddings

# 5. Build FAISS index
python -m scripts.ingest.build_faiss_index --embeddings-dir ./data/embeddings --output-dir ./data/index
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/query` | Submit legal query for multi-agent analysis |
| `GET` | `/api/v1/query/{id}/status` | Poll query status |
| `GET` | `/api/v1/cases/{case_id}` | Get full case details |
| `GET` | `/api/v1/cases/{case_id}/similar` | Get similar cases |
| `GET` | `/api/v1/stats` | System statistics |
| `GET` | `/api/v1/health` | Health check |

Interactive docs at `http://localhost:8000/docs`

---

## Testing

```bash
cd backend
pytest --cov=app --cov-report=term-missing
```

---

## Project Structure

```
Verdicto/
├── backend/
│   ├── app/
│   │   ├── agents/          # 6 specialized AI agents
│   │   ├── api/v1/          # FastAPI route handlers
│   │   ├── core/            # Config, DB, Gemini client, FAISS, exceptions
│   │   ├── models/          # SQLAlchemy ORM + Pydantic schemas
│   │   ├── services/        # Ranking, search, explanation services
│   │   ├── main.py          # FastAPI app entrypoint
│   │   └── worker.py        # Celery worker config
│   ├── alembic/             # Database migrations
│   ├── scripts/ingest/      # Data pipeline scripts
│   ├── tests/               # Unit + integration tests
│   ├── Dockerfile
│   └── requirements.txt
├── Frontend/webapp/
│   ├── src/
│   │   ├── lib/apiClient.js  # Central API abstraction
│   │   ├── components/       # Layout, Sidebar, Topbar
│   │   └── pages/            # 8 page components
│   └── vite.config.js
├── data/                     # Local data storage (gitignored)
├── docker-compose.yml
└── .env.example
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19 + Vite + react-router-dom |
| API | FastAPI (async) |
| LLM | Google Gemini 1.5 Flash/Pro |
| Embeddings | Gemini text-embedding-004 |
| Vector Search | FAISS (IndexFlatIP) |
| Database | PostgreSQL 15 (tsvector + asyncpg) |
| Task Queue | Celery + Redis |
| Containers | Docker + docker-compose |
