"""
Integration tests for API endpoints using httpx.AsyncClient.
"""
from __future__ import annotations
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.mark.asyncio
async def test_root_endpoint():
    """Test the root endpoint returns basic info."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Verdicto Legal AI API"
        assert "version" in data


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test health check returns structured response."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "database" in data
        assert "faiss" in data


@pytest.mark.asyncio
async def test_stats_endpoint():
    """Test stats endpoint returns system statistics."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_cases" in data
        assert "years_covered" in data


@pytest.mark.asyncio
async def test_query_validation():
    """Test query endpoint validates input."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Too short query
        response = await client.post("/api/v1/query", json={"query": "ab"})
        assert response.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_case_not_found():
    """Test 404 for non-existent case."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/cases/NONEXISTENT_CASE_ID")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_query_debate_rounds_non_empty():
    """
    Validates: Requirements 3.2, 4.1, 4.2

    Mocks SchedulerAgent.run to return a pre-built response dict containing a
    non-empty debate_rounds list, then asserts the response JSON contains
    agent_trace.debate.details.debate_rounds as a non-empty list.

    The test mocks both the DB session (to avoid real DB connections) and
    SchedulerAgent.run so the pipeline returns the pre-built trace immediately.
    """
    import json
    import uuid
    from datetime import datetime, timezone
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    mock_scheduler_response = {
        "query_id": "test-qid",
        "status": "complete",
        "processing_time_ms": 100,
        "results": [],
        "agent_trace": {
            "debate": {
                "agent_name": "debate",
                "status": "complete",
                "latency_ms": 50,
                "input_size": 3,
                "output_size": 1,
                "details": {
                    "rounds": 2,
                    "disputes": 0,
                    "rationale_len": 30,
                    "debate_rounds": [
                        {
                            "round_number": 1,
                            "type": "advocate_opposing",
                            "entries": [
                                {
                                    "case_id": "case-001",
                                    "advocate": {
                                        "relevance_argument": "Highly relevant.",
                                        "key_principles": [],
                                        "confidence": 0.9,
                                    },
                                    "opposing": {
                                        "counterargument": "Distinguishable.",
                                        "weaknesses": [],
                                        "overruled_by": None,
                                        "confidence": 0.7,
                                    },
                                }
                            ],
                        }
                    ],
                    "final_ranking": ["case-001"],
                    "consensus_rationale": "Case 001 is most relevant.",
                    "disagreement_flags": [],
                },
            }
        },
    }

    # Build a fake QueryRecord that the mock DB session will return
    fake_query_id = uuid.uuid4()
    fake_record = MagicMock()
    fake_record.id = fake_query_id
    fake_record.query_text = "What are the landmark cases on fundamental rights?"
    fake_record.status = "complete"
    fake_record.filters = json.dumps({})
    fake_record.options = json.dumps({"enable_debate": True})
    fake_record.result = json.dumps([])
    fake_record.agent_trace = json.dumps(mock_scheduler_response["agent_trace"])
    fake_record.processing_time_ms = 100
    fake_record.created_at = datetime.now(timezone.utc)
    fake_record.completed_at = datetime.now(timezone.utc)

    # Mock async DB session used by the FastAPI dependency (get_db)
    mock_db_session = AsyncMock()
    mock_db_session.add = MagicMock()
    mock_db_session.commit = AsyncMock()
    mock_db_session.get = AsyncMock(return_value=fake_record)

    # Mock execute() for SELECT queries (used by get_query endpoint)
    mock_scalar_result = MagicMock()
    mock_scalar_result.scalar_one_or_none = MagicMock(return_value=fake_record)
    mock_db_session.execute = AsyncMock(return_value=mock_scalar_result)

    # Mock async_session_factory used in run_pipeline_background
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory = MagicMock(return_value=mock_session_ctx)

    async def override_get_db():
        yield mock_db_session

    with (
        patch("app.agents.scheduler.SchedulerAgent.run", new_callable=AsyncMock, return_value=mock_scheduler_response),
        patch("app.api.v1.query.async_session_factory", mock_session_factory),
    ):
        from app.core.database import get_db
        app.dependency_overrides[get_db] = override_get_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # POST the query — returns immediately with "processing" status
                post_response = await client.post(
                    "/api/v1/query",
                    json={
                        "query": "What are the landmark cases on fundamental rights?",
                        "options": {"enable_debate": True},
                    },
                )
                assert post_response.status_code == 200
                post_data = post_response.json()
                query_id = post_data["query_id"]

                # Background task runs after the response; give it a moment to complete
                await asyncio.sleep(0.3)

                # Retrieve the completed query result
                get_response = await client.get(f"/api/v1/query/{query_id}")
                assert get_response.status_code == 200, (
                    f"Expected 200 but got {get_response.status_code}: {get_response.text}"
                )
                result = get_response.json()

                # Assert debate_rounds is present and non-empty
                debate_details = result["agent_trace"]["debate"]["details"]
                assert "debate_rounds" in debate_details, (
                    "agent_trace.debate.details.debate_rounds is missing from response"
                )
                assert isinstance(debate_details["debate_rounds"], list), (
                    "debate_rounds should be a list"
                )
                assert len(debate_details["debate_rounds"]) > 0, (
                    "debate_rounds should be non-empty"
                )
        finally:
            app.dependency_overrides.pop(get_db, None)
