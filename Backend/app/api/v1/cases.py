"""
GET /api/v1/cases/{case_id} — Full case details.
GET /api/v1/cases/{case_id}/similar — Similar cases.
"""
from __future__ import annotations
from typing import Any
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.faiss_index import get_faiss_index
from app.core.gemini_client import get_gemini_client
from app.models.case import Case, Citation
from app.models.query import CaseDetailResponse, SimilarCaseResponse

logger = structlog.get_logger()
router = APIRouter()


@router.get("/cases/{case_id}", response_model=CaseDetailResponse)
async def get_case_detail(case_id: str, db: AsyncSession = Depends(get_db)) -> CaseDetailResponse:
    """Retrieve full details of a single case."""
    stmt = select(Case).where(Case.case_id == case_id)
    result = await db.execute(stmt)
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail={"error": {"code": "CASE_NOT_FOUND", "message": f"Case {case_id} not found"}})

    cite_stmt = select(func.count()).where(Citation.cited_case_id == case_id)
    cite_result = await db.execute(cite_stmt)
    cite_count = cite_result.scalar() or 0

    return CaseDetailResponse(
        case_id=case.case_id, title=case.title, year=case.year, bench=case.bench,
        petitioner=case.petitioner, respondent=case.respondent,
        decision_date=str(case.decision_date) if case.decision_date else None,
        disposal_nature=case.disposal_nature, acts_sections=case.acts_sections or [],
        citation=case.citation, facts_text=case.facts_text, issues_text=case.issues_text,
        reasoning_text=case.reasoning_text, outcome_text=case.outcome_text, citation_count=cite_count)


@router.get("/cases/{case_id}/similar", response_model=list[SimilarCaseResponse])
async def get_similar_cases(case_id: str, top_k: int = 10, db: AsyncSession = Depends(get_db)) -> list[SimilarCaseResponse]:
    """Get cases similar to a given case via FAISS."""
    faiss_idx = get_faiss_index()
    if not faiss_idx.is_loaded:
        raise HTTPException(status_code=503, detail={"error": {"code": "INDEX_NOT_LOADED", "message": "FAISS index not available"}})

    embedding = faiss_idx.get_case_embedding(case_id)
    if embedding is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "CASE_NOT_FOUND", "message": f"No embedding for case {case_id}"}})

    results = faiss_idx.search(embedding, top_k=top_k + 1)
    # Exclude the case itself
    results = [r for r in results if r["case_id"] != case_id][:top_k]

    if not results:
        return []

    case_ids = [r["case_id"] for r in results]
    stmt = select(Case).where(Case.case_id.in_(case_ids))
    db_result = await db.execute(stmt)
    cases = {c.case_id: c for c in db_result.scalars().all()}

    return [
        SimilarCaseResponse(case_id=r["case_id"], title=cases[r["case_id"]].title if r["case_id"] in cases else "Unknown",
            year=cases[r["case_id"]].year if r["case_id"] in cases else 0,
            similarity_score=round(r["faiss_score"], 4), bench=cases.get(r["case_id"], Case).bench if r["case_id"] in cases else None)
        for r in results
    ]
