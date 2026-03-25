"""P&L and performance metrics endpoints."""

from __future__ import annotations

from collections import defaultdict
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


@router.get("/analytics")
async def get_analytics(
    _auth: AuthDep,
    db: DbDep,
    period: Annotated[str, Query(pattern="^(daily|monthly|yearly)$")] = "daily",
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict:
    """P&L analytics with per-strategy breakdown over time.

    Returns cumulative P&L line data for each strategy, grouped by
    day, month, or year. Data comes from both DB funding_payments
    and live paper position profits.
    """
    from app.main import get_paper_executor

    now = datetime.now(UTC)
    since = now - timedelta(days=days)

    if period == "monthly":
        trunc_fn = func.date_trunc("month", FundingPayment.timestamp)
    elif period == "yearly":
        trunc_fn = func.date_trunc("year", FundingPayment.timestamp)
    else:
        trunc_fn = func.date_trunc("day", FundingPayment.timestamp)

    stmt = (
        select(
            trunc_fn.label("period"),
            FundingPayment.exchange,
            func.coalesce(func.sum(FundingPayment.payment), 0).label("total_pnl"),
        )
        .where(FundingPayment.timestamp >= since)
        .group_by("period", FundingPayment.exchange)
        .order_by("period")
    )
    rows = (await db.execute(stmt)).all()

    series: dict[str, list[dict]] = defaultdict(list)
    period_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for row in rows:
        ts = row.period.isoformat() if row.period else ""
        period_totals[ts]["funding_arb"] += float(row.total_pnl)

    paper = get_paper_executor()
    if paper is not None:
        for pos in paper.all_positions:
            strategy = getattr(pos, "strategy", "funding_arb")
            opened = pos.opened_at

            if period == "monthly":
                key = opened.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            elif period == "yearly":
                key = opened.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                key = opened.replace(hour=0, minute=0, second=0, microsecond=0)

            ts = key.isoformat()
            period_totals[ts][strategy] += pos.funding_collected

    all_strategies = ["funding_arb", "grid", "carry"]
    sorted_periods = sorted(period_totals.keys())

    cumulative = {s: 0.0 for s in all_strategies}
    combined_total = 0.0

    for ts in sorted_periods:
        point: dict = {"period": ts}
        for strat in all_strategies:
            amount = period_totals[ts].get(strat, 0.0)
            cumulative[strat] += amount
            point[strat] = round(cumulative[strat], 6)
            combined_total += amount
        point["total"] = round(sum(cumulative[s] for s in all_strategies), 6)
        series["data"].append(point)

    strategy_summary = {}
    for strat in all_strategies:
        strategy_summary[strat] = round(cumulative[strat], 6)
    strategy_summary["total"] = round(combined_total, 6)

    return {
        "period": period,
        "days": days,
        "strategies": all_strategies,
        "summary": strategy_summary,
        "data": series.get("data", []),
    }
