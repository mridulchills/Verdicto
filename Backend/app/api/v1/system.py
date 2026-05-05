"""
GET /api/v1/health — Health check for all services.
GET /api/v1/stats — System statistics.
"""
from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.faiss_index import get_faiss_index
from app.models.case import Case, QueryRecord
from app.models.query import HealthResponse, SystemStatsResponse

logger = structlog.get_logger()
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    """Health check for DB, FAISS, Redis, Gemini."""
    resp = HealthResponse(status="healthy")

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        resp.database = "connected"
    except Exception as e:
        resp.database = f"error: {e}"
        resp.status = "degraded"

    # Check FAISS
    try:
        idx = get_faiss_index()
        resp.faiss = "loaded" if idx.is_loaded else "not_loaded"
    except Exception:
        resp.faiss = "not_loaded"

    # Redis check (basic)
    try:
        import redis as _redis
        from app.core.config import get_settings
        r = _redis.from_url(get_settings().redis_url)
        r.ping()
        resp.redis = "connected"
    except Exception:
        resp.redis = "not_available"

    # Gemini check (just config, no live call)
    try:
        from app.core.config import get_settings
        if get_settings().gemini_api_key:
            resp.gemini = "configured"
        else:
            resp.gemini = "not_configured"
    except Exception:
        resp.gemini = "not_configured"

    return resp


@router.get("/stats", response_model=SystemStatsResponse)
async def system_stats(db: AsyncSession = Depends(get_db)) -> SystemStatsResponse:
    """System statistics: total cases, years covered, query count."""
    total_cases = (await db.execute(select(func.count()).select_from(Case))).scalar() or 0
    years_result = await db.execute(select(Case.year).distinct().order_by(Case.year))
    years = [row[0] for row in years_result.fetchall()]
    total_queries = (await db.execute(select(func.count()).select_from(QueryRecord))).scalar() or 0

    idx = get_faiss_index()
    return SystemStatsResponse(total_cases=total_cases, years_covered=years,
        total_queries=total_queries, faiss_index_size=idx.total_vectors, embedding_dimension=idx.dimension)
