"""Funding rate API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.data.models import FundingRate
from app.core.data.state import StateStore
from app.core.database import get_db

router = APIRouter(prefix="/api/v1/funding", tags=["funding"])
logger = structlog.get_logger(__name__)

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _get_state() -> StateStore:
    return StateStore()


StateDep = Annotated[StateStore, Depends(_get_state)]


@router.get("/rates")
async def get_live_funding_rates(state: StateDep) -> dict:
    """Get current funding rates from all exchanges (live from Redis)."""
    rates = await state.get_all_funding_rates()
    return {"rates": rates, "count": len(rates)}


@router.get("/rates/{exchange}/{symbol}")
async def get_funding_rate(exchange: str, symbol: str, state: StateDep) -> dict:
    """Get current funding rate for a specific exchange and symbol."""
    rate = await state.get_funding_rate(exchange, symbol)
    if rate is None:
        return {"rate": None, "message": "No data available"}
    return {"rate": rate}


@router.get("/history")
async def get_funding_history(
    db: DbDep,
    symbol: Annotated[str, Query(description="e.g. BTC/USDT")],
    exchange: Annotated[str | None, Query(description="Filter by exchange")] = None,
    hours: Annotated[int, Query(ge=1, le=720, description="Lookback hours")] = 24,
) -> dict:
    """Get historical funding rates from TimescaleDB."""
    since = datetime.now(UTC) - timedelta(hours=hours)

    stmt = (
        select(FundingRate)
        .where(FundingRate.symbol == symbol, FundingRate.timestamp >= since)
        .order_by(FundingRate.timestamp.desc())
    )

    if exchange:
        stmt = stmt.where(FundingRate.exchange == exchange)

    result = await db.execute(stmt.limit(1000))
    rows = result.scalars().all()

    return {
        "symbol": symbol,
        "exchange": exchange,
        "hours": hours,
        "count": len(rows),
        "data": [
            {
                "timestamp": r.timestamp.isoformat(),
                "exchange": r.exchange,
                "symbol": r.symbol,
                "funding_rate": float(r.funding_rate),
                "predicted_rate": float(r.predicted_rate) if r.predicted_rate else None,
                "mark_price": float(r.mark_price) if r.mark_price else None,
                "index_price": float(r.index_price) if r.index_price else None,
            }
            for r in rows
        ],
    }
