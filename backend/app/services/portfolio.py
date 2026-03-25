"""Portfolio state and P&L calculation service."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.data.models import (
    EquitySnapshot,
    FundingPayment,
    Position,
    PositionStatus,
)
from app.core.data.state import StateStore
from app.core.risk.manager import PortfolioSnapshot


async def compute_portfolio_snapshot(
    db: AsyncSession,
    state: StateStore,
) -> PortfolioSnapshot:
    """Build a portfolio snapshot from DB + live state."""
    open_stmt = select(Position).where(Position.status == PositionStatus.OPEN)
    result = await db.execute(open_stmt)
    open_positions = result.scalars().all()

    exposure_by_exchange: dict[str, float] = {}
    exposure_by_pair: dict[str, float] = {}

    for pos in open_positions:
        notional = float(pos.spot_qty) * float(pos.entry_price_spot)
        exchange = pos.exchange
        symbol = pos.symbol

        exposure_by_exchange[exchange] = exposure_by_exchange.get(exchange, 0.0) + notional
        exposure_by_pair[symbol] = exposure_by_pair.get(symbol, 0.0) + notional

    total_funding_stmt = select(func.coalesce(func.sum(FundingPayment.payment), 0))
    total_funding = float((await db.execute(total_funding_stmt)).scalar() or 0)

    return PortfolioSnapshot(
        total_capital=total_funding,
        exposure_by_exchange=exposure_by_exchange,
        exposure_by_pair=exposure_by_pair,
        open_position_count=len(open_positions),
    )


async def save_equity_snapshot(
    db: AsyncSession,
    total_equity: float,
    unrealized_pnl: float = 0.0,
    realized_pnl: float = 0.0,
    funding_pnl: float = 0.0,
    positions_count: int = 0,
) -> None:
    """Persist an equity snapshot to TimescaleDB."""
    snapshot = EquitySnapshot(
        timestamp=datetime.now(UTC),
        total_equity=total_equity,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=realized_pnl,
        funding_pnl=funding_pnl,
        positions_count=positions_count,
    )
    db.add(snapshot)
    await db.commit()
