"""P&L and performance metrics endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import AuthDep
from app.core.data.models import EquitySnapshot, FundingPayment, Position, PositionStatus
from app.core.database import get_db

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/pnl")
async def get_pnl_summary(_auth: AuthDep, db: DbDep) -> dict:
    """P&L summary: daily, weekly, monthly, all-time."""
    now = datetime.now(UTC)

    async def _funding_sum(since: datetime) -> float:
        stmt = select(func.coalesce(func.sum(FundingPayment.payment), 0)).where(
            FundingPayment.timestamp >= since
        )
        result = await db.execute(stmt)
        return float(result.scalar() or 0)

    daily = await _funding_sum(now - timedelta(days=1))
    weekly = await _funding_sum(now - timedelta(weeks=1))
    monthly = await _funding_sum(now - timedelta(days=30))
    all_time = await _funding_sum(datetime.min.replace(tzinfo=UTC))

    open_count_stmt = select(func.count()).where(Position.status == PositionStatus.OPEN)
    open_count = (await db.execute(open_count_stmt)).scalar() or 0

    closed_count_stmt = select(func.count()).where(Position.status == PositionStatus.CLOSED)
    closed_count = (await db.execute(closed_count_stmt)).scalar() or 0

    return {
        "funding_pnl": {
            "daily": daily,
            "weekly": weekly,
            "monthly": monthly,
            "all_time": all_time,
        },
        "positions": {
            "open": open_count,
            "closed": closed_count,
        },
    }


@router.get("/equity")
async def get_equity_curve(
    _auth: AuthDep,
    db: DbDep,
    hours: Annotated[int, Query(ge=1, le=720)] = 24,
) -> dict:
    """Equity curve data points for charting."""
    since = datetime.now(UTC) - timedelta(hours=hours)

    stmt = (
        select(EquitySnapshot)
        .where(EquitySnapshot.timestamp >= since)
        .order_by(EquitySnapshot.timestamp.asc())
        .limit(2000)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return {
        "hours": hours,
        "count": len(rows),
        "data": [
            {
                "timestamp": r.timestamp.isoformat(),
                "total_equity": float(r.total_equity),
                "unrealized_pnl": float(r.unrealized_pnl),
                "realized_pnl": float(r.realized_pnl),
                "funding_pnl": float(r.funding_pnl),
                "positions_count": r.positions_count,
            }
            for r in rows
        ],
    }
