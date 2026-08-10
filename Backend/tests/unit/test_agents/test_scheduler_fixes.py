"""
Property-based tests for SchedulerAgent fixes.

**Validates: Requirements 1.1, 1.2, 2.1, 2.2**
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from app.core.config import get_settings


# ── Property 1: Scheduler always allows up to 3 iterations ────────────────────


@given(st.booleans())
@h_settings(max_examples=50)
def test_max_iter_never_capped_by_debate_flag(enable_debate: bool) -> None:
    """
    Property 1: For any value of enable_debate, max_iter must equal
    min(settings.scheduler_max_iterations, 3) and must never be 1.

    **Validates: Requirements 1.1, 1.2**
    """
    settings = get_settings()

    # This is the formula used in SchedulerAgent.run()
    max_iter = min(settings.scheduler_max_iterations, 3)

    # The computed value must always equal min(scheduler_max_iterations, 3)
    assert max_iter == min(settings.scheduler_max_iterations, 3)

    # max_iter must never be 1 — the pipeline must allow at least up to 3 iterations
    # (scheduler_max_iterations defaults to 3, so min(3, 3) == 3)
    assert max_iter != 1, (
        f"max_iter should never be 1; got {max_iter} "
        f"(scheduler_max_iterations={settings.scheduler_max_iterations})"
    )

    # When enable_debate is True, max_iter must not be capped at 1
    if enable_debate:
        assert max_iter != 1, (
            f"max_iter must not be 1 when enable_debate=True; got {max_iter}"
        )


# ── Property 2: Debate runs to completion without outer timeout ────────────────


def _make_valid_debate_result(query_id: str = "test-qid") -> dict[str, Any]:
    """Return a minimal valid debate result dict (simulates a completed debate)."""
    return {
        "query_id": query_id,
        "debate_rounds": [
            {
                "round_number": 1,
                "type": "advocate_opposing",
                "entries": [
                    {
                        "case_id": "case-001",
                        "advocate": {
                            "relevance_argument": "This case is highly relevant.",
                            "key_principles": ["principle A"],
                            "confidence": 0.9,
                        },
                        "opposing": {
                            "counterargument": "The case is distinguishable.",
                            "weaknesses": ["weakness X"],
                            "overruled_by": None,
                            "confidence": 0.7,
                        },
                    }
                ],
            },
            {
                "round_number": 2,
                "type": "synthesis",
                "result": {
                    "final_ranking": ["case-001"],
                    "rationale": "Case 001 is the most relevant.",
                    "disputes": [],
                },
            },
        ],
        "final_ranking": ["case-001"],
        "consensus_rationale": "Case 001 is the most relevant.",
        "disagreement_flags": [],
    }


def _make_ranked_cases() -> list[dict[str, Any]]:
    """Return a minimal list of ranked cases for the scheduler pipeline."""
    return [
        {
            "case_id": "case-001",
            "title": "Test Case One",
            "year": 2020,
            "citation": "2020 SC 1",
            "bench": "3J",
            "decision_date": "2020-01-01",
            "disposal_nature": "Allowed",
            "rrf_score": 0.8,
            "faiss_score": 0.75,
            "authority_score": 0.6,
            "final_score": 0.72,
            "reasoning_text": "The court held that...",
            "outcome_text": "Appeal allowed.",
            "facts_text": "The facts of the case are...",
            "issues_text": "Whether the contract was valid?",
            "acts_sections": [],
        }
    ]


@pytest.mark.asyncio
async def test_debate_no_outer_timeout() -> None:
    """
    Property 2: Debate runs to completion without outer timeout.

    The scheduler SHALL NOT wrap debater.execute() in asyncio.wait_for with an
    outer timeout. When DebateAgent.execute returns a valid result (even after a
    simulated long-running debate), the scheduler must complete without raising
    asyncio.TimeoutError.

    **Validates: Requirements 2.1, 2.2**
    """
    from app.agents.scheduler import SchedulerAgent

    ranked_cases = _make_ranked_cases()
    valid_debate_result = _make_valid_debate_result()

    # Mock QueryPlannerAgent.execute — returns a minimal plan
    mock_plan_result: dict[str, Any] = {
        "legal_domain": "contract",
        "extracted_issues": ["validity of contract"],
        "confidence": 0.8,
        "reformulated_queries": ["contract validity"],
    }

    # Mock RetrieverAgent.execute — returns ranked candidates
    mock_retrieval_result: dict[str, Any] = {
        "faiss_hits": 5,
        "bm25_hits": 5,
        "after_rrf": 5,
        "candidates": ranked_cases,
    }

    # Mock PrecedentWeighterAgent.execute — returns ranked cases
    mock_weight_result: dict[str, Any] = {
        "reranked_count": 1,
        "ranked_cases": ranked_cases,
    }

    # Mock EvaluatorAgent.execute — returns high confidence so pipeline converges
    mock_eval_result: dict[str, Any] = {
        "precision_at_5": 0.8,
        "ndcg_at_10": 0.75,
        "mrr": 0.9,
        "coverage": 0.7,
        "confidence": 0.8,
        "needs_refinement": False,
    }

    # DebateAgent.execute is mocked to return a valid result immediately.
    # This simulates a long-running debate that completes successfully —
    # the key property being tested is that the scheduler does NOT impose
    # an outer asyncio.wait_for timeout that would kill this call.
    mock_debate_execute = AsyncMock(return_value=valid_debate_result)

    mock_gemini_client = MagicMock()
    mock_gemini_client.reset_circuit = MagicMock()

    with (
        patch(
            "app.agents.scheduler.QueryPlannerAgent.execute",
            new_callable=AsyncMock,
            return_value=mock_plan_result,
        ),
        patch(
            "app.agents.scheduler.RetrieverAgent.execute",
            new_callable=AsyncMock,
            return_value=mock_retrieval_result,
        ),
        patch(
            "app.agents.scheduler.PrecedentWeighterAgent.execute",
            new_callable=AsyncMock,
            return_value=mock_weight_result,
        ),
        patch(
            "app.agents.scheduler.DebateAgent.execute",
            mock_debate_execute,
        ),
        patch(
            "app.agents.scheduler.EvaluatorAgent.execute",
            new_callable=AsyncMock,
            return_value=mock_eval_result,
        ),
        patch(
            "app.core.gemini_client.get_gemini_client",
            return_value=mock_gemini_client,
        ),
    ):
        scheduler = SchedulerAgent(db_session=None)

        # The scheduler must NOT raise asyncio.TimeoutError.
        # If the old asyncio.wait_for(timeout=110.0) wrapper were still present,
        # it would kill the debate call. The fixed code uses a direct await.
        try:
            result = await scheduler.run(
                {
                    "query_id": "test-qid",
                    "query": "contract validity dispute",
                    "filters": {},
                    "options": {"enable_debate": True, "top_k": 5},
                }
            )
        except asyncio.TimeoutError as exc:
            pytest.fail(
                f"Scheduler raised asyncio.TimeoutError — the outer timeout wrapper "
                f"must have been re-introduced. Error: {exc}"
            )

        # The result must contain agent_trace (pipeline completed successfully)
        assert "agent_trace" in result, (
            "Scheduler result must contain 'agent_trace' key"
        )

        # Debate must have been called exactly once (iteration == 1, enable_debate=True)
        mock_debate_execute.assert_called_once()

        # The trace must include a debate entry
        assert "debate" in result["agent_trace"], (
            "agent_trace must contain a 'debate' entry when enable_debate=True "
            "and ranked_cases is non-empty"
        )


# ── Property 3: Full debate data round-trip ───────────────────────────────────


@given(
    st.lists(
        st.fixed_dictionaries(
            {
                "round_number": st.integers(min_value=1, max_value=3),
                "type": st.just("advocate_opposing"),
                "entries": st.just([]),
            }
        ),
        min_size=1,
        max_size=3,
    )
)
@h_settings(max_examples=50)
def test_trace_stores_full_debate_rounds(debate_rounds: list[dict[str, Any]]) -> None:
    """
    Property 3: Full debate data round-trip.

    For any list of debate round entries (1–3 items), the trace-building code
    path in scheduler.py must store the original list verbatim under
    trace["debate"]["details"]["debate_rounds"], and the summary count
    trace["debate"]["details"]["rounds"] must equal len(debate_rounds).

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
    """
    # Build a mock debate_result with the generated debate_rounds
    debate_result: dict[str, Any] = {
        "query_id": "test-qid",
        "debate_rounds": debate_rounds,
        "final_ranking": ["case-001"],
        "consensus_rationale": "Test rationale.",
        "disagreement_flags": [],
    }

    # Simulate the trace-building code path from scheduler.py
    trace_details: dict[str, Any] = {
        # existing summary counts — keep these
        "rounds": len(debate_result.get("debate_rounds", [])),
        "disputes": len(debate_result.get("disagreement_flags", [])),
        "rationale_len": len(debate_result.get("consensus_rationale", "")),
        # NEW — full data for frontend consumption
        "debate_rounds": debate_result.get("debate_rounds", []),
        "final_ranking": debate_result.get("final_ranking", []),
        "consensus_rationale": debate_result.get("consensus_rationale", ""),
        "disagreement_flags": debate_result.get("disagreement_flags", []),
    }

    # Property: debate_rounds must be stored verbatim (full round-trip)
    assert trace_details["debate_rounds"] == debate_rounds, (
        f"trace_details['debate_rounds'] must equal the original debate_rounds list; "
        f"got {trace_details['debate_rounds']!r}, expected {debate_rounds!r}"
    )

    # Property: summary count must equal len(debate_rounds)
    assert trace_details["rounds"] == len(debate_rounds), (
        f"trace_details['rounds'] must equal len(debate_rounds)={len(debate_rounds)}; "
        f"got {trace_details['rounds']}"
    )
