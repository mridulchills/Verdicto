"""
Integration tests for API endpoints using httpx.AsyncClient.
"""
from __future__ import annotations
import pytest
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
