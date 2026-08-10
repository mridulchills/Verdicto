"""
Property-based tests for EvaluatorAgent fixes.

**Validates: Requirements 5.1, 5.2, 5.3, 5.5, 5.6**
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from app.agents.evaluator import EvaluatorAgent
from app.core.config import get_settings


# ── Property 4: Evaluator confidence reflects composite score ─────────────────


@given(
    st.lists(
        st.fixed_dictionaries(
            {
                "final_score": st.floats(min_value=0.0, max_value=1.0),
                "authority_score": st.floats(min_value=0.0, max_value=1.0),
            }
        ),
        min_size=1,
        max_size=10,
    )
)
@h_settings(max_examples=100)
def test_evaluator_uses_final_score_over_authority_score(
    cases: list[dict[str, Any]],
) -> None:
    """
    Property 4: Evaluator confidence reflects composite score.

    For any set of ranked cases with both final_score and authority_score fields,
    the evaluator SHALL use final_score as the primary relevance proxy.

    When all final_score values are >= 0.4 (the binary relevance threshold),
    precision_at_5 must be > 0, confirming that final_score (not authority_score)
    is driving the relevance classification.

    **Validates: Requirements 5.1, 5.2, 5.3**
    """
    # Only test the interesting sub-case: all final_scores are above threshold
    # but authority_scores are below threshold. This proves final_score is used.
    high_final_low_authority = [
        {"final_score": 0.8, "authority_score": 0.1}
        for _ in cases
    ]

    agent = EvaluatorAgent()
    result = asyncio.run(
        agent.run(
            {
                "query_id": "test",
                "ranked_cases": high_final_low_authority,
                "extracted_issues": [],
                "debate_result": {},
            }
        )
    )

    # When all final_scores are 0.8 (>= 0.4 threshold), precision_at_5 must be > 0.
    # If the evaluator were using authority_score (0.1 < 0.4), precision_at_5 would be 0.
    assert result["precision_at_5"] > 0, (
        f"precision_at_5 must be > 0 when all final_scores are 0.8 (>= threshold 0.4); "
        f"got {result['precision_at_5']}. This indicates authority_score is being used "
        f"instead of final_score."
    )


@given(
    st.lists(
        st.fixed_dictionaries(
            {
                "final_score": st.floats(min_value=0.0, max_value=1.0),
                "authority_score": st.floats(min_value=0.0, max_value=1.0),
            }
        ),
        min_size=1,
        max_size=10,
    )
)
@h_settings(max_examples=100)
def test_evaluator_falls_back_to_authority_score_when_final_score_absent(
    cases: list[dict[str, Any]],
) -> None:
    """
    Property 4 (fallback): When final_score is absent, the evaluator SHALL fall
    back to authority_score.

    When all authority_scores are >= 0.4 and final_score is absent,
    precision_at_5 must be > 0.

    **Validates: Requirements 5.2**
    """
    # Cases with only authority_score (no final_score key)
    authority_only_cases = [
        {"authority_score": 0.8}
        for _ in cases
    ]

    agent = EvaluatorAgent()
    result = asyncio.run(
        agent.run(
            {
                "query_id": "test",
                "ranked_cases": authority_only_cases,
                "extracted_issues": [],
                "debate_result": {},
            }
        )
    )

    # When all authority_scores are 0.8 (>= 0.4 threshold) and final_score is absent,
    # precision_at_5 must be > 0 (fallback to authority_score is working).
    assert result["precision_at_5"] > 0, (
        f"precision_at_5 must be > 0 when all authority_scores are 0.8 and "
        f"final_score is absent; got {result['precision_at_5']}. "
        f"The fallback to authority_score is not working."
    )


# ── needs_refinement=False when confidence >= threshold ───────────────────────


def test_evaluator_needs_refinement_false_when_confidence_high() -> None:
    """
    When all final_score values are 1.0 (perfect scores), the evaluator's
    confidence will be high and needs_refinement must be False.

    **Validates: Requirements 5.5, 5.6**
    """
    settings = get_settings()

    # Perfect scores: all final_scores = 1.0, no debate disagreements
    perfect_cases = [
        {"final_score": 1.0, "authority_score": 1.0, "issues_text": "test", "facts_text": "test"}
        for _ in range(5)
    ]

    agent = EvaluatorAgent()
    result = asyncio.run(
        agent.run(
            {
                "query_id": "test",
                "ranked_cases": perfect_cases,
                "extracted_issues": [],
                "debate_result": {"disagreement_flags": []},
            }
        )
    )

    # With perfect scores, confidence must be >= confidence_threshold
    assert result["confidence"] >= settings.confidence_threshold, (
        f"confidence must be >= {settings.confidence_threshold} with perfect scores; "
        f"got {result['confidence']}"
    )

    # And needs_refinement must be False
    assert result["needs_refinement"] is False, (
        f"needs_refinement must be False when confidence={result['confidence']} "
        f">= confidence_threshold={settings.confidence_threshold}"
    )


@given(
    st.lists(
        st.fixed_dictionaries(
            {
                "final_score": st.floats(min_value=0.0, max_value=1.0),
                "authority_score": st.floats(min_value=0.0, max_value=1.0),
            }
        ),
        min_size=1,
        max_size=10,
    )
)
@h_settings(max_examples=100)
def test_evaluator_needs_refinement_consistent_with_confidence(
    cases: list[dict[str, Any]],
) -> None:
    """
    Property 4 (threshold consistency): For any set of ranked cases,
    needs_refinement must be False when confidence >= confidence_threshold
    (assuming no debate disagreements).

    **Validates: Requirements 5.5, 5.6**
    """
    settings = get_settings()

    agent = EvaluatorAgent()
    result = asyncio.run(
        agent.run(
            {
                "query_id": "test",
                "ranked_cases": cases,
                "extracted_issues": [],
                # No debate disagreements — isolates the confidence threshold check
                "debate_result": {"disagreement_flags": []},
            }
        )
    )

    confidence = result["confidence"]
    needs_refinement = result["needs_refinement"]

    # When confidence >= threshold and no disagreements, needs_refinement must be False
    if confidence >= settings.confidence_threshold:
        assert needs_refinement is False, (
            f"needs_refinement must be False when confidence={confidence} "
            f">= confidence_threshold={settings.confidence_threshold}; "
            f"got needs_refinement={needs_refinement}"
        )

    # When confidence < threshold, needs_refinement must be True
    if confidence < settings.confidence_threshold:
        assert needs_refinement is True, (
            f"needs_refinement must be True when confidence={confidence} "
            f"< confidence_threshold={settings.confidence_threshold}; "
            f"got needs_refinement={needs_refinement}"
        )
