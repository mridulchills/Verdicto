"""
Evaluator Agent — predicts result quality WITHOUT relevance labels.

Why this is not an IR-metrics agent
-----------------------------------
At inference time there are no qrels, so P@K / nDCG / MRR cannot be computed. The
previous version computed them anyway, using the system's own output scores as the
relevance signal. That is circular, and it degenerated:

  * nDCG@10 compared the score list against `sorted(scores, reverse=True)` — but the
    precedent weighter had already sorted it descending, so actual DCG == ideal DCG and
    nDCG was identically 1.0. Measured: 0.96-1.0 over 33 evaluations, and the only
    values below 1.0 were where debate had reordered the top-3 and broken the sort.
  * MRR was 1/(rank of first result scoring >= 0.4); the top result always clears that,
    so MRR was 1.0 in 33/33.
  * P@5 took three distinct values ever, and was 1.0 in 27/33.

Confidence built from those numbers measures "did the scorer emit high numbers", not
"are these the right precedents", and it saturates — which makes any iteration loop
driven by it meaningless.

What replaces them
------------------
Post-retrieval QUERY PERFORMANCE PREDICTION: signals that are external to the ranker's
own score scale, in the clarity / NQC / WIG family. Every signal is bounded [0,1] and
each one is *owned by exactly one agent*, so the scheduler's routing falls out of the
confidence decomposition instead of being hand-wired:

  channel_agreement     0.30  FAISS and ts_rank independently pick the same cases -> retriever
  issue_coverage        0.25  the query's issues are grounded in the results      -> planner
  ranking_decisiveness  0.35  the ranking separates cases rather than tying them  -> weighter
  debate_consensus      0.10  the advocates agreed                                -> debate

score_dispersion and top_margin were originally separate signals, both owned by the
reweight remedy. They are anti-correlated under it: shifting weight onto factual
alignment lifts the whole top-k clear of the pool (dispersion +0.324) while compressing
the differences *within* the top-k (margin -0.334), so one remedy owned two signals it
moved in opposite directions and netted ~+0.015. They are now a single NQC predictor.

Weights sum to 1.0, so confidence spans the full [0,1] range: there is no structural
ceiling of the kind that capped the old formula at 0.80.

Calibration — PERCENTILE RANK, not min-max
------------------------------------------
QPP signals are collection-specific and none reaches 1.0 in practice, so on the raw
scale the best confidence attainable on this corpus is ~0.71 and any higher threshold is
unreachable by construction. The retrieval-side signals are therefore calibrated against
the DEV distribution by scripts/eval/fit_confidence_threshold.py.

Calibration is by PERCENTILE RANK against the dev empirical CDF. The first attempt used
min-max against dev p05-p95 and it manufactured a result: hard clipping piled mass at
exactly 1.0 (channel_agreement hit 1.0 in 21/30 queries, dispersion in 13/30), and since
the discarded top_margin weight was 0.15, the four remaining signals summed to exactly
0.85 — the threshold — so 10 of 15 "converged" queries landed on precisely 0.8500 and
every one of the 15 fell in [0.8500, 0.8599]. Convergence was an arithmetic coincidence
between the threshold and a subset sum of the weights, not a quality judgement.

Percentile rank spreads values uniformly over [0,1] with mass only at the true extremes,
so a signal has to genuinely sit high in the dev distribution to score high. Read a
calibrated value as "this query is at the Nth percentile of what this system achieves on
this collection".

The label-based metrics still belong in offline evaluation (scripts/eval/score.py),
where real qrels exist. They do not belong here.
"""
from __future__ import annotations

import bisect
import json
import math
import re
from pathlib import Path
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

# Confidence weights. Each signal is owned by one agent (see _SIGNAL_OWNER in
# scheduler.py) so that a deficient signal names the agent that can repair it.
SIGNAL_WEIGHTS: dict[str, float] = {
    "channel_agreement": 0.30,
    "issue_coverage": 0.25,
    "ranking_decisiveness": 0.35,
    "debate_consensus": 0.10,
}

_TOP_K = 10

# Signals whose raw range is collection-specific and does not reach 1.0 in practice.
# Calibrated against the dev distribution by scripts/eval/fit_confidence_threshold.py.
# issue_coverage and debate_consensus are excluded: they are true proportions already.
_CALIBRATED_SIGNALS = ("channel_agreement", "ranking_decisiveness")
_CALIBRATION_FILE = "qpp_calibration.json"


def _load_calibration() -> dict[str, list[float]]:
    """Load the dev-fitted quantile grids, if present.

    Absent the file the raw signals are used unchanged, which is safe but means the
    threshold must be set far lower — the raw ceiling on this collection is ~0.71.
    """
    for base in (Path("../data"), Path("data"), Path(__file__).resolve().parents[3] / "data"):
        path = base / "eval" / _CALIBRATION_FILE
        try:
            if path.exists():
                blob = json.loads(path.read_text(encoding="utf-8"))
                logger.info("evaluator.calibration_loaded", path=str(path),
                            fitted_on=blob.get("fitted_on"), n=blob.get("n"),
                            method=blob.get("method"))
                return {k: v["quantiles"] for k, v in blob.get("signals", {}).items()
                        if isinstance(v, dict) and v.get("quantiles")}
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("evaluator.calibration_unreadable", path=str(path), error=str(exc))
    logger.warning("evaluator.calibration_missing", file=_CALIBRATION_FILE)
    return {}


_CALIBRATION = _load_calibration()


def _calibrate(signal: str, value: float | None) -> float | None:
    """Percentile rank of `value` within the dev distribution, linearly interpolated.

    Returns the fraction of the dev sample this query beats. Only a value at or beyond
    the dev extremes reaches exactly 0.0 or 1.0, so calibrated signals do not pile up at
    the boundary the way min-max clipping made them.
    """
    if value is None or signal not in _CALIBRATION:
        return value
    grid = _CALIBRATION[signal]
    if len(grid) < 2:
        return value
    if value <= grid[0]:
        return 0.0
    if value >= grid[-1]:
        return 1.0
    i = bisect.bisect_left(grid, value)
    lo, hi = grid[i - 1], grid[i]
    frac = 0.0 if hi == lo else (value - lo) / (hi - lo)
    return max(0.0, min(1.0, (i - 1 + frac) / (len(grid) - 1)))


def _tokens(text: str) -> set[str]:
    """Distinctive content words: 4+ letters, boilerplate removed."""
    return set(re.findall(r"[a-z]{4,}", text.lower())) - _STOPWORDS


def _channel_agreement(candidates: list[dict[str, Any]],
                       ranked_cases: list[dict[str, Any]],
                       k: int = _TOP_K) -> float | None:
    """Fraction of the shown top-k that BOTH channels independently retrieved.

    Two retrieval mechanisms with nothing in common — embedding geometry and term
    statistics — nominating the same case is evidence neither can manufacture alone.

    Measured as corroboration of what the user is actually shown, rather than as a
    Jaccard overlap of the two channels' own top-k lists. Jaccard punishes the system
    for the two channels ranking *different* things highly even when the cases finally
    surfaced are well supported, and on this corpus it sat near 0.02-0.05 for every
    query — no dynamic range, so no usable signal.

    Returns None when only one channel produced anything: there is then no agreement to
    measure, and scoring it 0 would blame the ranking for a dead channel.
    """
    faiss = {c["case_id"] for c in candidates if (c.get("faiss_score") or 0) > 0}
    bm25 = {c["case_id"] for c in candidates if (c.get("bm25_score") or 0) > 0}
    if not faiss or not bm25:
        return None
    shown = [c.get("case_id") for c in ranked_cases[:k]]
    if not shown:
        return None
    return sum(1 for cid in shown if cid in faiss and cid in bm25) / len(shown)


def _ranking_decisiveness(scores: list[float], pool_scores: list[float]) -> float | None:
    """NQC: how sharply the ranking separates cases, relative to the pool it drew from.

        std(top-k) / mean(pool)

    Normalized Query Commitment (Shtok et al.) is the standard post-retrieval predictor
    for exactly this question. A ranking that assigns near-identical scores has committed
    to nothing; one with real spread has discriminated. Dividing by the pool mean makes it
    invariant to any rescaling of the score column, so the ranker cannot inflate it by
    emitting larger numbers.

    This replaces the earlier pair of signals — score_dispersion (top-k standout from the
    pool) and top_margin (rank-1 separation from the median) — which were both owned by
    the reweight remedy and which reweight moved in OPPOSITE directions: +0.324 and
    -0.334 respectively across 29 queries, netting ~+0.015. A single measure that captures
    within-top-k spread cannot be gamed by trading one half against the other.
    """
    top = [s for s in scores[:_TOP_K] if s > 0]
    pool = [s for s in pool_scores if s > 0]
    if len(top) < 2 or len(pool) < 2:
        return None
    pool_mean = sum(pool) / len(pool)
    if pool_mean <= 0:
        return None
    mean_top = sum(top) / len(top)
    variance = sum((x - mean_top) ** 2 for x in top) / len(top)
    return math.sqrt(variance) / pool_mean


def _issue_coverage(query_issues: list[str],
                    ranked_cases: list[dict[str, Any]]) -> float | None:
    """Fraction of the query's legal issues grounded in the top-k case text.

    External to the ranking: it compares the results against the QUERY, so no amount of
    score inflation moves it. Returns None when the planner extracted no usable issues —
    scoring that 0 would penalise the results for a fact about the query.
    """
    if not query_issues or not ranked_cases:
        return None
    case_tokens = _tokens(" ".join(
        (c.get("issues_text", "") or "") + " " + (c.get("facts_text", "") or "")
        for c in ranked_cases[:_TOP_K]
    ))
    if not case_tokens:
        return None

    matched = scored = 0
    for issue in query_issues:
        terms = _tokens(issue)
        if not terms:
            continue
        scored += 1
        # An issue counts as addressed when half its distinctive terms appear.
        if len(terms & case_tokens) / len(terms) >= 0.5:
            matched += 1
    return matched / scored if scored else None


def _debate_consensus(debate_result: dict[str, Any],
                      ranked_cases: list[dict[str, Any]]) -> float | None:
    """1 - disagreement rate. None when debate did not run on this pass."""
    if not debate_result:
        return None
    flags = debate_result.get("disagreement_flags", [])
    rate = len(flags) / max(len(ranked_cases[:5]), 1)
    return max(0.0, min(1.0, 1.0 - rate))


class EvaluatorAgent(BaseAgent):
    name: str = "evaluator"

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        qid = input_data.get("query_id", "")
        ranked_cases = input_data.get("ranked_cases", [])
        query_issues = input_data.get("extracted_issues", [])
        debate_result = input_data.get("debate_result", {}) or {}
        # Per-channel scores survive RRF (see retriever.merge_rankings), which is what
        # makes channel agreement computable at all.
        candidates = input_data.get("candidates", []) or []

        scores = [c.get("final_score", c.get("authority_score", 0.0)) or 0.0
                  for c in ranked_cases]
        # The full pool the ranking was drawn from — the reference the top-k must beat.
        pool_scores = [c.get("rrf_score", 0.0) or 0.0 for c in candidates]
        ranked_pool = [c.get("authority_score", 0.0) or 0.0 for c in ranked_cases]

        raw_signals: dict[str, float | None] = {
            "channel_agreement": _channel_agreement(candidates, ranked_cases),
            "issue_coverage": _issue_coverage(query_issues, ranked_cases),
            "ranking_decisiveness": _ranking_decisiveness(
                scores, ranked_pool or pool_scores),
            "debate_consensus": _debate_consensus(debate_result, ranked_cases),
        }
        signals: dict[str, float | None] = {
            k: (_calibrate(k, v) if k in _CALIBRATED_SIGNALS else v)
            for k, v in raw_signals.items()
        }

        # Renormalise over the signals that are actually measurable for this query, so a
        # missing signal neither deducts silently nor caps the achievable confidence.
        available = {k: v for k, v in signals.items() if v is not None}
        total_weight = sum(SIGNAL_WEIGHTS[k] for k in available)
        if total_weight > 0:
            confidence = sum(SIGNAL_WEIGHTS[k] * v for k, v in available.items()) / total_weight
        else:
            confidence = 0.0
        # Round before comparing so 0.8499999... does not fail a 0.85 threshold.
        confidence = round(confidence, 4)

        needs_refinement = confidence < settings.confidence_threshold

        logger.info("evaluator.signals", query_id=qid, confidence=confidence,
                    **{k: round(v, 4) for k, v in available.items()})

        return {
            "query_id": qid,
            "confidence": confidence,
            "needs_refinement": needs_refinement,
            "signals": {k: (round(v, 4) if v is not None else None)
                        for k, v in signals.items()},
            "signals_raw": {k: (round(v, 4) if v is not None else None)
                            for k, v in raw_signals.items()},
            "calibrated": sorted(k for k in _CALIBRATED_SIGNALS if k in _CALIBRATION),
            "signals_available": sorted(available),
            "signals_missing": sorted(k for k, v in signals.items() if v is None),
            # Kept as a named field because the scheduler and the debate stage both
            # read it directly.
            "disagreement_rate": round(
                1.0 - (signals["debate_consensus"] or 1.0), 4),
            "coverage": signals["issue_coverage"],
        }
