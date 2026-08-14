"""
Property-based tests for EvaluatorAgent.

These were rewritten when the evaluator stopped computing label-free IR metrics.
The previous suite asserted, among other things, that "perfect scores" must produce
confidence >= the convergence threshold. That property was the bug: it is satisfiable
only if confidence is a function of the ranker's own score column, which is precisely
what made the old confidence circular and saturated (nDCG was identically 1.0 because
the list was pre-sorted; MRR was 1.0 in 33/33 traced queries).

Under the QPP design confidence is a function of evidence the ranker does not control —
channel agreement, issue coverage, dispersion against the pool, margin, debate consensus
— so a set of cases with perfect scores but no corroboration SHOULD score low. The tests
below assert the properties that actually hold.

**Validates: Requirements 5.1, 5.2, 5.3, 5.5, 5.6**
"""
from __future__ import annotations

import asyncio
from typing import Any

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from app.agents.evaluator import SIGNAL_WEIGHTS, EvaluatorAgent
from app.core.config import get_settings


def _run(payload: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(EvaluatorAgent().run(payload))


def _cases(n: int, *, final: float | None = None, authority: float = 0.0,
           text: str = "") -> list[dict[str, Any]]:
    out = []
    for i in range(n):
        c: dict[str, Any] = {"case_id": f"c{i}", "authority_score": authority,
                             "issues_text": text, "facts_text": text}
        if final is not None:
            c["final_score"] = final
        out.append(c)
    return out


# ── The score column: final_score preferred, authority_score as fallback ──────


def test_evaluator_prefers_final_score_over_authority_score() -> None:
    """final_score drives the score-shaped signals; authority_score is the fallback.

    Asserted through top_margin, which is computed from the score column: a spread of
    final_scores must produce a non-zero margin even when every authority_score is flat.
    Under the old suite this was asserted via precision_at_5, a metric that no longer
    exists because it required a relevance threshold the system cannot know.

    **Validates: Requirements 5.1, 5.2, 5.3**
    """
    spread_final = [
        {"case_id": f"c{i}", "final_score": 1.0 - i * 0.1, "authority_score": 0.5}
        for i in range(10)
    ]
    result = _run({"query_id": "t", "ranked_cases": spread_final,
                   "extracted_issues": [], "debate_result": {}, "candidates": []})
    assert result["signals"]["top_margin"] is not None
    assert result["signals"]["top_margin"] > 0, (
        "top_margin must be > 0 when final_scores are spread; a flat value indicates "
        "authority_score (constant 0.5 here) is being read instead of final_score"
    )


def test_evaluator_falls_back_to_authority_score() -> None:
    """With no final_score present, the authority_score column is used.

    **Validates: Requirements 5.2**
    """
    spread_authority = [
        {"case_id": f"c{i}", "authority_score": 1.0 - i * 0.1} for i in range(10)
    ]
    result = _run({"query_id": "t", "ranked_cases": spread_authority,
                   "extracted_issues": [], "debate_result": {}, "candidates": []})
    assert result["signals"]["top_margin"] is not None
    assert result["signals"]["top_margin"] > 0, (
        "top_margin must be > 0 when authority_scores are spread and final_score is absent"
    )


# ── Confidence is bounded and is NOT a function of score magnitude alone ──────


def test_confidence_is_bounded() -> None:
    """Confidence stays within [0,1] for any input. Weights sum to 1.0."""
    assert abs(sum(SIGNAL_WEIGHTS.values()) - 1.0) < 1e-9
    for cases in ([], _cases(1, final=0.0), _cases(10, final=1.0), _cases(50, final=0.5)):
        result = _run({"query_id": "t", "ranked_cases": cases, "extracted_issues": [],
                       "debate_result": {}, "candidates": []})
        assert 0.0 <= result["confidence"] <= 1.0


def test_uncorroborated_results_do_not_score_high() -> None:
    """Perfect scores with no corroborating evidence must NOT clear the threshold.

    This is the inverse of the property the old suite asserted, and it is the point of
    the redesign: a ranker cannot certify itself by emitting high numbers. With no
    candidates (so no channel agreement), no issues (no coverage) and no debate, the
    only measurable signals are the score-shaped ones, and a flat perfect list is not
    evidence of anything.

    **Validates: Requirements 5.5, 5.6**
    """
    flat_perfect = _cases(10, final=1.0)
    result = _run({"query_id": "t", "ranked_cases": flat_perfect,
                   "extracted_issues": [], "debate_result": {}, "candidates": []})
    assert result["confidence"] < get_settings().confidence_threshold, (
        f"a flat, uncorroborated result set scored {result['confidence']}, at or above "
        "the convergence threshold — confidence is being driven by score magnitude again"
    )


def test_corroborated_beats_uncorroborated() -> None:
    """Agreement between the two retrieval channels must raise confidence.

    Same ranking either way; the only difference is whether the shown cases were found
    by both channels or by one.
    """
    shown = _cases(10, final=0.9, text="privacy")
    both = [{"case_id": f"c{i}", "faiss_score": 0.9, "bm25_score": 0.8} for i in range(10)]
    one = [{"case_id": f"c{i}", "faiss_score": 0.9, "bm25_score": 0.0} for i in range(10)]
    # A single bm25-only case keeps the channel alive so the signal is measurable.
    one.append({"case_id": "other", "faiss_score": 0.0, "bm25_score": 0.5})

    high = _run({"query_id": "t", "ranked_cases": shown, "extracted_issues": [],
                 "debate_result": {}, "candidates": both})
    low = _run({"query_id": "t", "ranked_cases": shown, "extracted_issues": [],
                "debate_result": {}, "candidates": one})
    assert high["signals"]["channel_agreement"] > low["signals"]["channel_agreement"]
    assert high["confidence"] > low["confidence"]


# ── Missing signals are dropped, never scored zero ───────────────────────────


def test_unmeasurable_signals_are_dropped_not_zeroed() -> None:
    """A signal that cannot be measured must not silently deduct from confidence.

    Scoring an unmeasurable signal 0 is what capped the old formula at 0.80: coverage
    was structurally unmeasurable and its 0.2 weight was deducted on every query, so no
    threshold above 0.80 could ever be met.
    """
    cases = _cases(10, final=0.9)
    result = _run({"query_id": "t", "ranked_cases": cases, "extracted_issues": [],
                   "debate_result": {}, "candidates": []})
    assert "issue_coverage" in result["signals_missing"]
    assert result["signals"]["issue_coverage"] is None
    # Renormalisation: confidence must equal the weighted mean over AVAILABLE signals.
    available = {k: v for k, v in result["signals"].items() if v is not None}
    if available:
        tw = sum(SIGNAL_WEIGHTS[k] for k in available)
        expected = sum(SIGNAL_WEIGHTS[k] * v for k, v in available.items()) / tw
        assert abs(result["confidence"] - round(expected, 4)) < 1e-3


def test_empty_results_are_handled() -> None:
    """No cases at all must not raise, and must not report false confidence."""
    result = _run({"query_id": "t", "ranked_cases": [], "extracted_issues": [],
                   "debate_result": {}, "candidates": []})
    assert result["confidence"] == 0.0
    assert result["needs_refinement"] is True


# ── needs_refinement tracks the threshold exactly ────────────────────────────


@given(
    st.lists(
        st.fixed_dictionaries({
            "final_score": st.floats(min_value=0.0, max_value=1.0),
            "authority_score": st.floats(min_value=0.0, max_value=1.0),
        }),
        min_size=1, max_size=10,
    )
)
@h_settings(max_examples=100)
def test_needs_refinement_consistent_with_confidence(cases: list[dict[str, Any]]) -> None:
    """needs_refinement is exactly `confidence < threshold`, for any input.

    **Validates: Requirements 5.5, 5.6**
    """
    threshold = get_settings().confidence_threshold
    for i, c in enumerate(cases):
        c["case_id"] = f"c{i}"
    result = _run({"query_id": "t", "ranked_cases": cases, "extracted_issues": [],
                   "debate_result": {"disagreement_flags": []}, "candidates": []})
    assert result["needs_refinement"] is (result["confidence"] < threshold)
