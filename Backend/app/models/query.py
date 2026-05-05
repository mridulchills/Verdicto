"""
Pydantic v2 request/response schemas for the API layer.
These define the exact contract between frontend and backend.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Request Schemas ───────────────────────────────────────────────────────


class QueryFilters(BaseModel):
    """Optional filters for narrowing search scope."""

    year_from: int | None = None
    year_to: int | None = None
    domain: str | None = None


class QueryOptions(BaseModel):
    """Optional tuning parameters for the query pipeline."""

    top_k: int = Field(default=10, ge=1, le=50)
    enable_debate: bool = True
    explanation_detail: str = Field(default="full", pattern="^(full|brief|none)$")


class QueryRequest(BaseModel):
    """POST /api/v1/query request body."""

    query: str = Field(..., min_length=5, max_length=5000)
    filters: QueryFilters = Field(default_factory=QueryFilters)
    options: QueryOptions = Field(default_factory=QueryOptions)


# ── Response Schemas ──────────────────────────────────────────────────────


class CaseResult(BaseModel):
    """A single case result in the query response."""

    rank: int
    case_id: str
    title: str
    year: int
    citation: str | None = None
    bench: str | None = None
    decision_date: str | None = None
    disposal_nature: str | None = None
    relevance_score: float = Field(ge=0.0, le=1.0)
    authority_score: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)
    matched_issues: list[str] = Field(default_factory=list)
    snippet: str = ""
    explanation: str = ""
    debate_notes: str = ""
    acts_sections: list[str] = Field(default_factory=list)


class AgentTraceEntry(BaseModel):
    """Trace data for a single agent execution."""

    agent_name: str
    status: str = "complete"  # complete, failed, skipped
    latency_ms: float = 0.0
    input_size: int = 0
    output_size: int = 0
    details: dict[str, Any] = Field(default_factory=dict)


class AgentTrace(BaseModel):
    """Full pipeline execution trace."""

    query_planner: AgentTraceEntry | None = None
    retriever: AgentTraceEntry | None = None
    precedent_weighting: AgentTraceEntry | None = None
    debate: AgentTraceEntry | None = None
    scheduler: AgentTraceEntry | None = None
    evaluator: AgentTraceEntry | None = None


class QueryResponse(BaseModel):
    """POST /api/v1/query response body."""

    query_id: str
    status: str = "complete"
    processing_time_ms: int = 0
    results: list[CaseResult] = Field(default_factory=list)
    agent_trace: AgentTrace = Field(default_factory=AgentTrace)


class QueryStatusResponse(BaseModel):
    """GET /api/v1/query/{query_id}/status response."""

    query_id: str
    status: str  # pending, processing, complete, failed
    processing_time_ms: int | None = None
    created_at: str
    completed_at: str | None = None
    agent_trace: AgentTrace | None = None


class CaseDetailResponse(BaseModel):
    """GET /api/v1/cases/{case_id} response."""

    case_id: str
    title: str
    year: int
    bench: str | None = None
    petitioner: str | None = None
    respondent: str | None = None
    decision_date: str | None = None
    disposal_nature: str | None = None
    acts_sections: list[str] = Field(default_factory=list)
    citation: str | None = None
    facts_text: str | None = None
    issues_text: str | None = None
    reasoning_text: str | None = None
    outcome_text: str | None = None
    citation_count: int = 0


class SimilarCaseResponse(BaseModel):
    """A single similar case entry."""

    case_id: str
    title: str
    year: int
    similarity_score: float
    bench: str | None = None


class SystemStatsResponse(BaseModel):
    """GET /api/v1/stats response."""

    total_cases: int = 0
    years_covered: list[int] = Field(default_factory=list)
    total_queries: int = 0
    faiss_index_size: int = 0
    embedding_dimension: int = 0


class HealthResponse(BaseModel):
    """GET /api/v1/health response."""

    status: str = "healthy"
    database: str = "unknown"
    faiss: str = "unknown"
    redis: str = "unknown"
    gemini: str = "unknown"



class QueryListItem(BaseModel):
    """A single past query entry."""

    query_id: str
    query_text: str
    status: str
    processing_time_ms: int | None = None
    created_at: str
    completed_at: str | None = None


class QueryListResponse(BaseModel):
    """GET /api/v1/queries response."""

    queries: list[QueryListItem] = Field(default_factory=list)
    total: int = 0


class ErrorResponse(BaseModel):
    """Consistent error response format."""

    error: dict[str, str | None]
