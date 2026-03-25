"""Bot event log endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import AuthDep
from app.core.data.models import BotEvent, EventLevel
from app.core.database import get_db

router = APIRouter(prefix="/api/v1/events", tags=["events"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("")
async def list_events(
    _auth: AuthDep,
    db: DbDep,
    level: Annotated[EventLevel | None, Query()] = None,
    component: Annotated[str | None, Query()] = None,
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> dict:
    """List bot events with filters."""
    since = datetime.now(UTC) - timedelta(hours=hours)

    stmt = select(BotEvent).where(BotEvent.timestamp >= since).order_by(BotEvent.timestamp.desc())

    if level is not None:
        stmt = stmt.where(BotEvent.level == level)
    if component:
        stmt = stmt.where(BotEvent.component == component)

    stmt = stmt.limit(limit)
    rows = (await db.execute(stmt)).scalars().all()

    return {
        "count": len(rows),
        "data": [
            {
                "id": str(e.id),
                "timestamp": e.timestamp.isoformat(),
                "level": e.level.value if e.level else "",
                "component": e.component,
                "message": e.message,
                "metadata": e.metadata_,
            }
            for e in rows
        ],
    }
