"""Persists structured bot events to the bot_events table.

Provides a simple async interface for any service to log events
that appear in the dashboard Events page.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.data.models import BotEvent, EventLevel

logger = structlog.get_logger(__name__)


class EventLogger:
    """Writes bot events to TimescaleDB."""

    def __init__(self, db_session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._db_factory = db_session_factory

    async def log(
        self,
        level: EventLevel,
        component: str,
        message: str,
        metadata: dict | None = None,
    ) -> None:
        event = BotEvent(
            id=uuid.uuid4(),
            timestamp=datetime.now(UTC),
            level=level,
            component=component,
            message=message,
            metadata_=metadata,
        )
        try:
            async with self._db_factory() as session:
                session.add(event)
                await session.commit()
        except Exception as exc:
            logger.warning("event_log_db_error", error=str(exc))

    async def info(self, component: str, message: str, **meta) -> None:
        await self.log(EventLevel.INFO, component, message, meta or None)

    async def warning(self, component: str, message: str, **meta) -> None:
        await self.log(EventLevel.WARNING, component, message, meta or None)

    async def error(self, component: str, message: str, **meta) -> None:
        await self.log(EventLevel.ERROR, component, message, meta or None)

    async def critical(self, component: str, message: str, **meta) -> None:
        await self.log(EventLevel.CRITICAL, component, message, meta or None)
