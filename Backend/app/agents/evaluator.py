"""
Evaluator Agent — Scores result quality using retrieval metrics.
Computes P@K, nDCG@K, MRR, Coverage, and overall confidence.
"""
from __future__ import annotations
import math
import re
from typing import Any
import structlog
from app.agents.base_agent import BaseAgent
from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# Legal boilerplate carries no topical signal — every judgment contains it, so leaving
# these in would make coverage look high for any pair of unrelated cases.
_STOPWORDS = {
    "that", "this", "with", "from", "have", "been", "were", "which", "their", "there",
    "would", "could", "shall", "such", "than", "then", "them", "these", "those", "under",
    "upon", "into", "when", "what", "whether", "case", "cases", "court", "courts",
    "appeal", "appellant", "respondent", "petitioner", "judgment", "order", "orders",
    "section", "sections", "act", "acts", "law", "legal", "india", "supreme", "high",
    "learned", "counsel", "para", "paragraph", "hon", "ble", "also", "shall", "said",
}


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

        # Use final_score as relevance proxy, fall back to authority_score
        scores = [c.get("final_score", c.get("authority_score", 0.0)) for c in ranked_cases]

        # P@K: fraction of top-K results above threshold
        threshold = 0.4
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

        # Coverage: % of query issues addressed.
        #
        # This used to test `issue.lower()[:20] in all_case_text` — an exact 20-character
        # prefix match of a generated natural-language issue against the concatenated case
        # text. That essentially never fires, so coverage was ~always 0.0, which silently
        # capped confidence at 0.80 (= 0.3 + 0.3 + 0.2) and made any threshold above 0.80
        # unreachable by construction. Compare distinctive content words instead.
        coverage = 0.0
        coverage_applicable = bool(query_issues and ranked_cases)
        if coverage_applicable:
            all_case_text = " ".join(
                (c.get("issues_text", "") + " " + c.get("facts_text", "")).lower()
                for c in ranked_cases[:10]
            )
            case_tokens = set(re.findall(r"[a-z]{4,}", all_case_text)) - _STOPWORDS
            matched = 0
            scored_issues = 0
            for issue in query_issues:
                terms = set(re.findall(r"[a-z]{4,}", issue.lower())) - _STOPWORDS
                if not terms:
                    continue
                scored_issues += 1
                # An issue counts as addressed when half its distinctive terms appear
                # somewhere in the top-10 case text.
                if len(terms & case_tokens) / len(terms) >= 0.5:
                    matched += 1
            if scored_issues:
                coverage = matched / scored_issues
            else:
                # Every issue was pure boilerplate — nothing measurable to cover.
                coverage_applicable = False

        # Overall confidence — round before threshold comparison to avoid
        # floating-point edge cases where 0.6499999... < 0.65 but rounds to 0.65.
        #
        # When the planner extracted no issues there is nothing for coverage to measure,
        # so it is dropped and the remaining weights are renormalised. Scoring it as 0.0
        # would deduct 0.2 for a fact about the QUERY rather than about the results, and
        # would cap confidence at 0.80 — below the 0.85 threshold, making convergence
        # impossible however good the ranking is.
        weighted = p_at_5 * 0.3 + ndcg_10 * 0.3 + mrr * 0.2
        if coverage_applicable:
            confidence_rounded = round(weighted + coverage * 0.2, 4)
        else:
            confidence_rounded = round(weighted / 0.8, 4)

        # Check debate disagreement
        disagreements = debate_result.get("disagreement_flags", [])
        disagreement_rate = len(disagreements) / max(len(ranked_cases[:5]), 1)
        needs_refinement = confidence_rounded < settings.confidence_threshold or disagreement_rate > 0.3

        return {
            "query_id": qid,
            "precision_at_5": round(p_at_5, 4),
            "precision_at_10": round(p_at_10, 4),
            "ndcg_at_10": round(ndcg_10, 4),
            "mrr": round(mrr, 4),
            "coverage": round(coverage, 4),
            "confidence": confidence_rounded,
            "needs_refinement": needs_refinement,
            "disagreement_rate": round(disagreement_rate, 4),
        }
