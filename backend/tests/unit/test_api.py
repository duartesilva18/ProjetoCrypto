"""Tests for REST API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.auth import create_access_token
from app.main import app


@pytest.fixture
def auth_headers():
    token = create_access_token()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Health ────────────────────────────────────


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Auth ──────────────────────────────────────


@pytest.mark.asyncio
async def test_login_success(client):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"password": "admin"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"password": "wrong"},
    )
    assert resp.status_code == 401


# ── Funding Rates ─────────────────────────────


@pytest.mark.asyncio
async def test_funding_rates_live(client):
    mock_redis = AsyncMock()
    mock_redis.hgetall = AsyncMock(return_value={})

    with patch("app.core.data.state.get_redis", return_value=mock_redis):
        resp = await client.get("/api/v1/funding/rates")
    assert resp.status_code == 200
    data = resp.json()
    assert "rates" in data
    assert "count" in data


# ── Protected Endpoints Need Auth ─────────────


@pytest.mark.asyncio
async def test_positions_requires_auth(client):
    resp = await client.get("/api/v1/positions")
    assert resp.status_code == 401 or resp.status_code == 403


@pytest.mark.asyncio
async def test_bot_status_requires_auth(client):
    resp = await client.get("/api/v1/bot/status")
    assert resp.status_code == 401 or resp.status_code == 403


@pytest.mark.asyncio
async def test_pnl_requires_auth(client):
    resp = await client.get("/api/v1/metrics/pnl")
    assert resp.status_code == 401 or resp.status_code == 403


# ── Prometheus ────────────────────────────────


@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint(client):
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    text = resp.text
    assert "evaluation_cycle_duration_seconds" in text
    assert "positions_open" in text


# ── Docs ──────────────────────────────────────


@pytest.mark.asyncio
async def test_openapi_docs(client):
    resp = await client.get("/docs")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_openapi_schema(client):
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"] == "ProjetoCrypto - Funding Rate Arbitrage Bot"
    paths = schema["paths"]
    assert "/health" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/funding/rates" in paths
    assert "/api/v1/positions" in paths
    assert "/api/v1/metrics/pnl" in paths
    assert "/api/v1/bot/status" in paths
    assert "/api/v1/events" in paths
