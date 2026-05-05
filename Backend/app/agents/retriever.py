"""
Retriever Agent — Performs hybrid semantic (FAISS) + keyword (BM25/tsvector) retrieval.
Merges results using Reciprocal Rank Fusion (RRF).
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_agent import BaseAgent
from app.core.config import get_settings
from app.core.exceptions import AgentError
from app.core.faiss_index import get_faiss_index
from app.services.embedding_service import get_embedding

logger = structlog.get_logger()
settings = get_settings()


def rrf_score(rank: int, k: int = 60) -> float:
    """Reciprocal Rank Fusion score for a given rank."""
    return 1.0 / (k + rank)


def merge_rankings(
    faiss_results: list[dict[str, Any]],
    bm25_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Merge FAISS and BM25 result lists using RRF.
    Returns sorted list of {case_id, rrf_score, faiss_score, bm25_score}.
    """
    scores: dict[str, dict[str, float]] = {}

    for rank, result in enumerate(faiss_results, start=1):
        cid = result["case_id"]
        if cid not in scores:
            scores[cid] = {"rrf_score": 0.0, "faiss_score": 0.0, "bm25_score": 0.0}
        scores[cid]["rrf_score"] += rrf_score(rank)
        scores[cid]["faiss_score"] = result.get("faiss_score", 0.0)

    for rank, result in enumerate(bm25_results, start=1):
        cid = result["case_id"]
        if cid not in scores:
            scores[cid] = {"rrf_score": 0.0, "faiss_score": 0.0, "bm25_score": 0.0}
        scores[cid]["rrf_score"] += rrf_score(rank)
        scores[cid]["bm25_score"] = result.get("bm25_score", 0.0)

    merged = [
        {"case_id": cid, **data}
        for cid, data in scores.items()
    ]
    merged.sort(key=lambda x: x["rrf_score"], reverse=True)
    return merged


class RetrieverAgent(BaseAgent):
    """
    Hybrid retrieval: FAISS vector search + PostgreSQL BM25 tsvector search.
    Merges with RRF. Stateless.
    """

    name: str = "retriever"

    def __init__(self, db_session: AsyncSession | None = None) -> None:
        self._db_session = db_session

    async def _faiss_search(
        self, query_text: str, top_k: int
    ) -> list[dict[str, Any]]:
        """Perform FAISS semantic search."""
        faiss_idx = get_faiss_index()
        
        if not faiss_idx.is_loaded:
            logger.warning("retriever.faiss_not_loaded")
            return []

        query_embedding = await get_embedding(query_text)
        results = faiss_idx.search(query_embedding, top_k=top_k)
        return results

    async def _bm25_search(
        self,
        query_text: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Perform BM25 search via PostgreSQL tsvector (parameterized queries only)."""
        if self._db_session is None:
            logger.warning("retriever.no_db_session_for_bm25")
            return []

        # Build the SQL query with optional year filters
        sql = text("""
            SELECT case_id,
                   ts_rank(text_search_vector, plainto_tsquery('english', :query)) AS bm25_score
            FROM cases
            WHERE text_search_vector @@ plainto_tsquery('english', :query)
            {year_filter}
            ORDER BY bm25_score DESC
            LIMIT :top_k
        """.format(
            year_filter=self._build_year_filter(filters)
        ))

        params: dict[str, Any] = {"query": query_text, "top_k": top_k}
        if filters:
            if filters.get("year_from"):
                params["year_from"] = filters["year_from"]
            if filters.get("year_to"):
                params["year_to"] = filters["year_to"]

        try:
            result = await self._db_session.execute(sql, params)
            rows = result.fetchall()
            return [
                {"case_id": row[0], "bm25_score": float(row[1])}
                for row in rows
            ]
        except Exception as e:
            logger.error("retriever.bm25_failed", error=str(e))
            return []

    @staticmethod
    def _build_year_filter(filters: dict[str, Any] | None) -> str:
        """Build year filter clause. Uses parameter placeholders, not f-strings."""
        if not filters:
            return ""
        parts: list[str] = []
        if filters.get("year_from"):
            parts.append("AND year >= :year_from")
        if filters.get("year_to"):
            parts.append("AND year <= :year_to")
        return " ".join(parts)

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute hybrid retrieval.

        Input: {
            "query_id": str,
            "original_query": str,
            "reformulated_queries": list[str],
            "filters": {year_from, year_to, domain},
            ...
        }
        Output: RetrieverOutput-compatible dict
        """
        query_id = input_data.get("query_id", "")
        original_query = input_data.get("original_query", "")
        reformulated = input_data.get("reformulated_queries", [])
        filters = input_data.get("filters", {})

        # Use original query + first reformulation for broader coverage
        search_queries = [original_query] + reformulated[:1]
        combined_query = " ".join(search_queries)

        top_k = settings.max_query_k

        try:
            # Run FAISS and BM25 in parallel conceptually (sequential here for simplicity)
            faiss_results = await self._faiss_search(combined_query, top_k)
            bm25_results = await self._bm25_search(combined_query, top_k, filters)

            # Merge with RRF
            merged = merge_rankings(faiss_results, bm25_results)
            final = merged[: settings.final_candidates]

            return {
                "query_id": query_id,
                "candidates": final,
                "faiss_hits": len(faiss_results),
                "bm25_hits": len(bm25_results),
                "after_rrf": len(final),
            }

        except Exception as e:
            raise AgentError(
                f"Retriever failed: {e}", query_id=query_id
            ) from e
