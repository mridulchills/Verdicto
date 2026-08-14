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

  channel_agreement  0.30  FAISS and ts_rank independently pick the same cases  -> retriever
  issue_coverage     0.25  the query's issues are grounded in the results       -> planner
  score_dispersion   0.20  the ranking discriminates rather than being flat     -> weighter
  top_margin         0.15  there is a clear winner, not a tie                   -> weighter
  debate_consensus   0.10  the advocates agreed                                 -> debate

Weights sum to 1.0, so confidence spans the full [0,1] range: there is no structural
ceiling of the kind that capped the old formula at 0.80.

Calibration
-----------
QPP signals are collection-specific and none of them reaches 1.0 in practice here —
score_dispersion tops out near 0.42, channel_agreement medians ~0.45 — so on the RAW
scale the highest confidence any query can attain on this corpus is ~0.71. A threshold
above that is unreachable by construction, and the scheduler would iterate to the cap
forever without ever converging. The three retrieval-side signals are therefore min-max
calibrated against their dev-observed p05-p95 range (fitted by
scripts/eval/fit_confidence_threshold.py, DEV ONLY). After calibration the threshold
means "this fraction of the quality this system actually achieves on this collection",
which is the only reading of an absolute confidence number that survives scrutiny.

The label-based metrics still belong in offline evaluation (scripts/eval/score.py),
where real qrels exist. They do not belong here.
"""
from __future__ import annotations

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
    "score_dispersion": 0.20,
    "top_margin": 0.15,
    "debate_consensus": 0.10,
}

_TOP_K = 10

# Signals whose raw range is collection-specific and does not reach 1.0 in practice.
# Calibrated against the dev distribution by scripts/eval/fit_confidence_threshold.py.
# issue_coverage and debate_consensus are excluded: they are true proportions already.
_CALIBRATED_SIGNALS = ("channel_agreement", "score_dispersion", "top_margin")
_CALIBRATION_FILE = "qpp_calibration.json"


def _load_calibration() -> dict[str, dict[str, float]]:
    """Load the dev-fitted min-max ranges, if present.

    Without calibration, confidence cannot approach 1.0 on this collection —
    score_dispersion tops out near 0.42 and channel_agreement medians ~0.45 — so any
    threshold above ~0.71 would be unreachable by construction and the scheduler would
    iterate to the cap on every query forever. Absent the file the raw signals are used
    unchanged, which is safe but means the threshold must be set much lower.
    """
    for base in (Path("../data"), Path("data"), Path(__file__).resolve().parents[3] / "data"):
        path = base / "eval" / _CALIBRATION_FILE
        try:
            if path.exists():
                blob = json.loads(path.read_text(encoding="utf-8"))
                logger.info("evaluator.calibration_loaded", path=str(path),
                            fitted_on=blob.get("fitted_on"), n=blob.get("n"))
                return blob.get("signals", {})
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("evaluator.calibration_unreadable", path=str(path), error=str(exc))
    logger.warning("evaluator.calibration_missing", file=_CALIBRATION_FILE)
    return {}


_CALIBRATION = _load_calibration()


def _calibrate(signal: str, value: float | None) -> float | None:
    """Map a raw signal onto [0,1] using its dev-observed p05-p95 range."""
    if value is None or signal not in _CALIBRATION:
        return value
    lo = _CALIBRATION[signal].get("lo", 0.0)
    hi = _CALIBRATION[signal].get("hi", 1.0)
    if hi <= lo:
        return value
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


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


def _score_dispersion(scores: list[float], pool_scores: list[float]) -> float | None:
    """How far the shown top-k stands out from the whole candidate pool (WIG-style).

    A ranking that scores its top-k barely above the pool average has not discriminated.
    Normalised by the pool's own headroom so it stays in [0,1] with no calibration
    constant, and so it is invariant to any affine rescaling of the score column:

        (mean(top-k) - mean(pool)) / (max(pool) - mean(pool))

    Note the earlier attempt here — normalised entropy of the top-k scores — is
    mathematically clean but useless in practice: authority scores live in a narrow band
    (~0.45-0.62), so the distribution is near-uniform and the measure pinned at ~0.005
    for every query regardless of ranking quality.
    """
    top = [s for s in scores[:_TOP_K] if s > 0]
    pool = [s for s in pool_scores if s > 0]
    if len(top) < 2 or len(pool) < 2:
        return None
    pool_mean = sum(pool) / len(pool)
    headroom = max(pool) - pool_mean
    if headroom <= 0:
        return None
    top_mean = sum(top) / len(top)
    return max(0.0, min(1.0, (top_mean - pool_mean) / headroom))


def _top_margin(scores: list[float]) -> float | None:
    """Relative gap between the best case and the median of the top-k.

    Expressed as a fraction of the top score so it needs no calibration constant and
    stays in [0,1]. A decisive result set has one case standing clear of the pack.
    """
    vals = sorted((s for s in scores[:_TOP_K] if s > 0), reverse=True)
    if len(vals) < 2:
        return None
    top = vals[0]
    if top <= 0:
        return None
    mid = vals[len(vals) // 2]
    return max(0.0, min(1.0, (top - mid) / top))


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
            "score_dispersion": _score_dispersion(scores, ranked_pool or pool_scores),
            "top_margin": _top_margin(scores),
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
