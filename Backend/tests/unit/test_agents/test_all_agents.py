"""
Unit tests for all agents using pytest + pytest-asyncio.
Gemini API calls are mocked with unittest.mock.AsyncMock.
"""
from __future__ import annotations
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# ── Query Planner Tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_planner_basic():
    """Test query planner returns structured output."""
    mock_response = json.dumps({
        "legal_domain": "constitutional",
        "extracted_issues": ["Right to privacy under Article 21"],
        "extracted_facts": "Petitioner challenges surveillance",
        "target_outcome": "Declaration of right",
        "temporal_hint": "recent",
        "reformulated_queries": ["privacy fundamental right Article 21"],
        "confidence": 0.85,
    })

    with patch("app.core.gemini_client.get_gemini_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.generate_text = AsyncMock(return_value=mock_response)
        mock_client_fn.return_value = mock_client

        from app.agents.query_planner import QueryPlannerAgent
        agent = QueryPlannerAgent()
        result = await agent.execute({
            "query_id": str(uuid.uuid4()),
            "query": "Right to privacy as fundamental right under Article 21",
        })

        assert result["legal_domain"] == "constitutional"
        assert len(result["extracted_issues"]) > 0
        assert result["confidence"] == 0.85
        mock_client.generate_text.assert_called_once()


@pytest.mark.asyncio
async def test_query_planner_graceful_degradation():
    """Test query planner handles malformed Gemini response."""
    with patch("app.core.gemini_client.get_gemini_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.generate_text = AsyncMock(return_value="not valid json at all")
        mock_client_fn.return_value = mock_client

        from app.agents.query_planner import QueryPlannerAgent
        agent = QueryPlannerAgent()
        result = await agent.execute({
            "query_id": "test-123",
            "query": "test query about property law",
        })

        # Should gracefully degrade, not crash
        assert result["legal_domain"] == "general"
        assert result["confidence"] == 0.3


@pytest.mark.asyncio
async def test_query_planner_empty_query():
    """Test query planner raises error on empty query."""
    from app.agents.query_planner import QueryPlannerAgent
    from app.core.exceptions import AgentError

    agent = QueryPlannerAgent()
    with pytest.raises(AgentError):
        await agent.execute({"query_id": "test", "query": ""})


# ── Evaluator Tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evaluator_basic():
    """Test evaluator computes metrics correctly."""
    from app.agents.evaluator import EvaluatorAgent

    agent = EvaluatorAgent()
    result = await agent.execute({
        "query_id": "test",
        "ranked_cases": [
            {"case_id": "c1", "authority_score": 0.9, "issues_text": "privacy", "facts_text": "test"},
            {"case_id": "c2", "authority_score": 0.7, "issues_text": "", "facts_text": ""},
            {"case_id": "c3", "authority_score": 0.3, "issues_text": "", "facts_text": ""},
        ],
        "extracted_issues": ["privacy"],
        "debate_result": {"disagreement_flags": []},
    })

    assert "precision_at_5" in result
    assert "ndcg_at_10" in result
    assert "mrr" in result
    assert "confidence" in result
    assert 0 <= result["confidence"] <= 1


@pytest.mark.asyncio
async def test_evaluator_empty_results():
    """Test evaluator handles empty results gracefully."""
    from app.agents.evaluator import EvaluatorAgent

    agent = EvaluatorAgent()
    result = await agent.execute({
        "query_id": "test",
        "ranked_cases": [],
        "extracted_issues": [],
        "debate_result": {},
    })

    assert result["precision_at_5"] == 0.0
    assert result["mrr"] == 0.0


# ── Debate Agent Tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_debate_agent_basic():
    """Test debate agent runs 3 rounds."""
    advocate_resp = json.dumps({"relevance_argument": "highly relevant", "key_principles": ["separability"], "confidence": 0.9})
    opposing_resp = json.dumps({"counterargument": "different facts", "weaknesses": ["factual distinction"], "overruled_by": None, "confidence": 0.7})
    synthesis_resp = json.dumps({"final_ranking": ["case_1"], "rationale": "case_1 is most relevant", "disputes": []})

    with patch("app.core.gemini_client.get_gemini_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.generate_text = AsyncMock(side_effect=[advocate_resp, opposing_resp, synthesis_resp])
        mock_client_fn.return_value = mock_client

        from app.agents.debate import DebateAgent
        agent = DebateAgent()
        result = await agent.execute({
            "query_id": "test",
            "original_query": "test query",
            "ranked_cases": [{"case_id": "case_1", "title": "Test Case", "year": 2023, "bench": "3-Judge", "facts_text": "test facts"}],
        })

        assert len(result["debate_rounds"]) == 3
        assert "case_1" in result["final_ranking"]


@pytest.mark.asyncio
async def test_debate_agent_empty_cases():
    """Test debate agent handles no cases gracefully."""
    from app.agents.debate import DebateAgent

    agent = DebateAgent()
    result = await agent.execute({
        "query_id": "test",
        "original_query": "test",
        "ranked_cases": [],
    })

    assert result["final_ranking"] == []
    assert result["debate_rounds"] == []


# ── Base Agent Tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_base_agent_execute_logging():
    """Test that execute() wraps run() with timing."""
    from app.agents.base_agent import BaseAgent

    class TestAgent(BaseAgent):
        name = "test_agent"
        async def run(self, input_data):
            return {"result": "ok"}

    agent = TestAgent()
    result = await agent.execute({"query_id": "test"})
    assert result["result"] == "ok"


@pytest.mark.asyncio
async def test_base_agent_execute_error_propagation():
    """Test that execute() propagates errors with logging."""
    from app.agents.base_agent import BaseAgent

    class FailingAgent(BaseAgent):
        name = "failing_agent"
        async def run(self, input_data):
            raise ValueError("intentional failure")

    agent = FailingAgent()
    with pytest.raises(ValueError, match="intentional failure"):
        await agent.execute({"query_id": "test"})


# ── Ranking Service Tests ──────────────────────────────────────────────


def test_rrf_score():
    """Test RRF score computation."""
    from app.services.ranking_service import rrf_score
    assert rrf_score(1) == 1.0 / 61
    assert rrf_score(1, k=60) == pytest.approx(1.0 / 61)
    assert rrf_score(10) < rrf_score(1)


def test_final_score():
    """Test final score formula."""
    from app.services.ranking_service import compute_final_score
    score = compute_final_score(semantic=1.0, authority=1.0, structural=1.0)
    assert score == pytest.approx(1.0)

    score = compute_final_score(semantic=0.0, authority=0.0, structural=0.0)
    assert score == pytest.approx(0.0)

    # 0.5 * 0.8 + 0.3 * 0.6 + 0.2 * 0.4 = 0.4 + 0.18 + 0.08 = 0.66
    score = compute_final_score(semantic=0.8, authority=0.6, structural=0.4)
    assert score == pytest.approx(0.66)
