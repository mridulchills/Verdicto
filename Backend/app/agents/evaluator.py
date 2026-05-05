"""
Evaluator Agent — Scores result quality using retrieval metrics.
Computes P@K, nDCG@K, MRR, Coverage, and overall confidence.
"""
from __future__ import annotations
import math
from typing import Any
import structlog
from app.agents.base_agent import BaseAgent
from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


def _dcg(relevance_scores: list[float], k: int) -> float:
    """Discounted Cumulative Gain at K."""
    dcg = 0.0
    for i, rel in enumerate(relevance_scores[:k]):
        dcg += rel / math.log2(i + 2)
    return dcg


def _ndcg(relevance_scores: list[float], k: int) -> float:
    """Normalized DCG at K."""
    actual = _dcg(relevance_scores, k)
    ideal = _dcg(sorted(relevance_scores, reverse=True), k)
    if ideal == 0:
        return 0.0
    return actual / ideal


class EvaluatorAgent(BaseAgent):
    name: str = "evaluator"

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        qid = input_data.get("query_id", "")
        ranked_cases = input_data.get("ranked_cases", [])
        query_issues = input_data.get("extracted_issues", [])
        debate_result = input_data.get("debate_result", {})

        # Use authority_score as relevance proxy
        scores = [c.get("authority_score", 0.0) for c in ranked_cases]

        # P@K: fraction of top-K results above threshold
        threshold = 0.5
        p_at_5 = sum(1 for s in scores[:5] if s >= threshold) / min(5, len(scores)) if scores else 0.0
        p_at_10 = sum(1 for s in scores[:10] if s >= threshold) / min(10, len(scores)) if scores else 0.0

        # nDCG@10
        ndcg_10 = _ndcg(scores, 10) if scores else 0.0

        # MRR: reciprocal rank of first highly relevant result
        mrr = 0.0
        for i, s in enumerate(scores):
            if s >= threshold:
                mrr = 1.0 / (i + 1)
                break

        # Coverage: % of query issues addressed
        coverage = 0.0
        if query_issues and ranked_cases:
            all_case_text = " ".join(
                (c.get("issues_text", "") + " " + c.get("facts_text", "")).lower()
                for c in ranked_cases[:10]
            )
            matched = sum(1 for issue in query_issues if issue.lower()[:20] in all_case_text)
            coverage = matched / len(query_issues)

        # Overall confidence
        confidence = (p_at_5 * 0.3 + ndcg_10 * 0.3 + mrr * 0.2 + coverage * 0.2)

        # Check debate disagreement
        disagreements = debate_result.get("disagreement_flags", [])
        disagreement_rate = len(disagreements) / max(len(ranked_cases[:5]), 1)
        needs_refinement = confidence < settings.confidence_threshold or disagreement_rate > 0.3

        return {
            "query_id": qid,
            "precision_at_5": round(p_at_5, 4),
            "precision_at_10": round(p_at_10, 4),
            "ndcg_at_10": round(ndcg_10, 4),
            "mrr": round(mrr, 4),
            "coverage": round(coverage, 4),
            "confidence": round(confidence, 4),
            "needs_refinement": needs_refinement,
            "disagreement_rate": round(disagreement_rate, 4),
        }
