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

    @staticmethod
    def _build_or_tsquery(query_text: str) -> str:
        """
        Convert a natural language query into a PostgreSQL OR-based tsquery.
        Extracts meaningful words (length >= 4) and joins with | (OR).
        This gives much better recall than plainto_tsquery (AND logic).
        """
        import re
        # Remove common stop words and short words
        stop_words = {
            "the", "and", "for", "that", "this", "with", "from", "have",
            "been", "were", "they", "their", "what", "when", "where", "which",
            "under", "into", "upon", "also", "such", "case", "court", "high",
            "supreme", "india", "indian",
        }
        # Extract words, filter stop words and short words
        words = re.findall(r'\b[a-zA-Z]{4,}\b', query_text.lower())
        keywords = [w for w in words if w not in stop_words]
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                unique.append(w)
        # Use top 8 keywords max to avoid overly complex queries
        return " | ".join(unique[:8]) if unique else query_text

    async def _bm25_search(
        self,
        query_text: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Perform BM25 search via PostgreSQL tsvector.
        Uses OR-based tsquery for better recall than plainto_tsquery (AND logic).
        """
        if self._db_session is None:
            logger.warning("retriever.no_db_session_for_bm25")
            return []

        # Build OR-based tsquery for better recall
        or_query = self._build_or_tsquery(query_text)
        if not or_query:
            return []

        # Build the SQL query with optional year filters
        sql = text("""
            SELECT case_id,
                   ts_rank(text_search_vector, to_tsquery('english', :tsquery)) AS bm25_score
            FROM cases
            WHERE text_search_vector @@ to_tsquery('english', :tsquery)
            {year_filter}
            ORDER BY bm25_score DESC
            LIMIT :top_k
        """.format(
            year_filter=self._build_year_filter(filters)
        ))

        params: dict[str, Any] = {"tsquery": or_query, "top_k": top_k}
        if filters:
            if filters.get("year_from"):
                params["year_from"] = filters["year_from"]
            if filters.get("year_to"):
                params["year_to"] = filters["year_to"]

        try:
            result = await self._db_session.execute(sql, params)
            rows = result.fetchall()
            logger.info(
                "retriever.bm25_complete",
                tsquery=or_query,
                hits=len(rows),
            )
            return [
                {"case_id": row[0], "bm25_score": float(row[1])}
                for row in rows
            ]
        except Exception as e:
            logger.error("retriever.bm25_failed", error=str(e), tsquery=or_query)
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

        # The scheduler re-runs this agent with a different reformulation when the
        # evaluator reports a weak candidate pool. variant_index selects which of the
        # planner's alternatives to lead with; without it we would re-issue the same
        # search and get a bit-identical result (the fixed point this loop used to hit).
        variant_index = int(input_data.get("variant_index", 0) or 0)
        if reformulated and variant_index > 0:
            i = (variant_index - 1) % len(reformulated)
            lead = reformulated[i]
            # Lead with the alternative phrasing, keep the original for anchoring.
            search_queries = [lead, original_query]
            bm25_query = lead
        else:
            # FAISS: use combined query for broader semantic coverage
            search_queries = [original_query] + reformulated[:1]
            # BM25: only the original — combined queries are too long for tsvector matching
            bm25_query = original_query
        combined_query = " ".join(search_queries)

        top_k = int(input_data.get("top_k_override") or settings.max_query_k)

        try:
            # Run FAISS and BM25 concurrently
            import asyncio as _asyncio
            faiss_task = _asyncio.create_task(self._faiss_search(combined_query, top_k))
            bm25_task = _asyncio.create_task(self._bm25_search(bm25_query, top_k, filters))
            faiss_results, bm25_results = await _asyncio.gather(faiss_task, bm25_task)

            # Merge with RRF
            merged = merge_rankings(faiss_results, bm25_results)
            final = merged[: settings.final_candidates]

            return {
                "query_id": query_id,
                "candidates": final,
                "faiss_hits": len(faiss_results),
                "bm25_hits": len(bm25_results),
                "after_rrf": len(final),
                "variant_index": variant_index,
                "top_k_used": top_k,
            }

        except Exception as e:
            raise AgentError(
                f"Retriever failed: {e}", query_id=query_id
            ) from e
