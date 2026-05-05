"""
Search service — orchestrates retrieval logic.
"""
from __future__ import annotations
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.retriever import RetrieverAgent


async def search_cases(query: str, filters: dict[str, Any], db: AsyncSession, top_k: int = 50) -> list[dict[str, Any]]:
    """Convenience wrapper for case search."""
    retriever = RetrieverAgent(db_session=db)
    result = await retriever.execute({
        "query_id": "", "original_query": query,
        "reformulated_queries": [query], "filters": filters,
    })
    return result.get("candidates", [])[:top_k]
