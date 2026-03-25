"""Position management API endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import AuthDep
from app.core.data.models import FundingPayment, Position, PositionStatus
from app.core.database import get_db

router = APIRouter(prefix="/api/v1/positions", tags=["positions"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("")
async def list_positions(
    _auth: AuthDep,
    db: DbDep,
    status_filter: Annotated[PositionStatus | None, Query(alias="status")] = None,
    exchange: Annotated[str | None, Query()] = None,
    symbol: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """List positions -- merges DB positions with live paper positions."""
    from app.main import get_paper_executor

    paper = get_paper_executor()
    paper_positions = []
    if paper is not None:
        for p in paper.all_positions:
            d = p.to_dict()
            d["status"] = "OPEN" if p.is_open else "CLOSED"
            d["is_paper"] = True
            paper_positions.append(d)

    stmt = select(Position).order_by(Position.opened_at.desc())
    if status_filter is not None:
        stmt = stmt.where(Position.status == status_filter)
    if exchange:
        stmt = stmt.where(Position.exchange == exchange)
    if symbol:
        stmt = stmt.where(Position.symbol == symbol)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    db_total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.offset(offset).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    db_positions = [_serialize_position(p) for p in rows]

    all_positions = paper_positions + db_positions
    total = len(paper_positions) + db_total

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": all_positions[:limit],
    }


@router.get("/{position_id}")
async def get_position(_auth: AuthDep, db: DbDep, position_id: str) -> dict:
    """Get position detail with funding payment history."""
    from app.main import get_paper_executor

    paper = get_paper_executor()
    if paper is not None:
        for p in paper.all_positions:
            if p.id == position_id:
                d = p.to_dict()
                d["status"] = "OPEN" if p.is_open else "CLOSED"
                d["is_paper"] = True
                return {"position": d, "funding_payments": []}

    stmt = select(Position).where(Position.id == position_id)
    pos = (await db.execute(stmt)).scalar_one_or_none()

    if pos is None:
        return {"error": "Position not found"}

    payments_stmt = (
        select(FundingPayment)
        .where(FundingPayment.position_id == position_id)
        .order_by(FundingPayment.timestamp.desc())
    )
    payments = (await db.execute(payments_stmt)).scalars().all()

    return {
        "position": _serialize_position(pos),
        "funding_payments": [
            {
                "timestamp": fp.timestamp.isoformat(),
                "payment": float(fp.payment),
                "rate": float(fp.rate),
            }
            for fp in payments
        ],
    }


def _serialize_position(p: Position) -> dict:
    return {
        "id": str(p.id),
        "exchange": p.exchange,
        "symbol": p.symbol,
        "side": p.side.value if p.side else "",
        "spot_qty": float(p.spot_qty),
        "perp_qty": float(p.perp_qty),
        "entry_price_spot": float(p.entry_price_spot),
        "entry_price_perp": float(p.entry_price_perp),
        "status": p.status.value if p.status else "",
        "funding_collected": float(p.funding_collected),
        "opened_at": p.opened_at.isoformat() if p.opened_at else None,
        "closed_at": p.closed_at.isoformat() if p.closed_at else None,
        "is_paper": p.is_paper,
    }
