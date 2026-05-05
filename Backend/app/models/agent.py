"""
Pydantic schemas for agent input/output validation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class QueryPlannerOutput(BaseModel):
    """Output schema for the Query Planner Agent."""

    query_id: str
    original_query: str
    legal_domain: str = "general"
    extracted_issues: list[str] = Field(default_factory=list)
    extracted_facts: str = ""
    target_outcome: str = ""
    temporal_hint: str = "any"  # recent | historical | any
    reformulated_queries: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class RetrieverOutput(BaseModel):
    """Output schema for the Retriever Agent."""

    candidates: list[dict] = Field(default_factory=list)
    faiss_hits: int = 0
    bm25_hits: int = 0
    after_rrf: int = 0


class PrecedentWeighterOutput(BaseModel):
    """Output schema for the Precedent Weighting Agent."""

    ranked_cases: list[dict] = Field(default_factory=list)
    reranked_count: int = 0


class DebateRound(BaseModel):
    """A single round of the debate."""

    round_number: int
    advocate_argument: str = ""
    advocate_key_principles: list[str] = Field(default_factory=list)
    advocate_confidence: float = 0.0
    counterargument: str = ""
    weaknesses: list[str] = Field(default_factory=list)
    counter_confidence: float = 0.0


class DebateOutput(BaseModel):
    """Output schema for the Debate Agent."""

    debate_rounds: list[DebateRound] = Field(default_factory=list)
    final_ranking: list[str] = Field(default_factory=list)
    consensus_rationale: str = ""
    disagreement_flags: list[str] = Field(default_factory=list)


class EvaluatorOutput(BaseModel):
    """Output schema for the Evaluator Agent."""

    precision_at_5: float = 0.0
    precision_at_10: float = 0.0
    ndcg_at_10: float = 0.0
    mrr: float = 0.0
    coverage: float = 0.0
    confidence: float = 0.0
    needs_refinement: bool = False


class SchedulerOutput(BaseModel):
    """Output schema for the Scheduler Agent."""

    iterations: int = 0
    final_status: str = "complete"
    confidence: float = 0.0
