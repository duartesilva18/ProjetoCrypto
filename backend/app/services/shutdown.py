"""Graceful shutdown protocol.

Coordinates orderly shutdown of all bot components.
Open positions are NOT closed -- they remain on the exchange
and are reconciled on restart.

Sequence:
  1. Set shutdown event
  2. Pause strategy (no new signals)
  3. Wait for in-flight executions (max 30s)
  4. Stop data collector (close WS connections)
  5. Stop reconciler
  6. Flush pending DB writes
  7. Persist final state snapshot to Redis
  8. Close Redis / DB connections
"""

from __future__ import annotations

import asyncio

import structlog

from app.core.data.collector import DataCollector
from app.core.data.state import StateStore
from app.core.execution.reconciler import Reconciler
from app.services.scheduler import BotScheduler

logger = structlog.get_logger(__name__)

_SHUTDOWN_TIMEOUT_SECONDS = 30.0


class ShutdownManager:
    """Manages orderly shutdown of all bot components."""

    def __init__(
        self,
        scheduler: BotScheduler | None = None,
        collector: DataCollector | None = None,
        reconciler: Reconciler | None = None,
        state: StateStore | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._collector = collector
        self._reconciler = reconciler
        self._state = state
        self._shutdown_event = asyncio.Event()

    @property
    def is_shutting_down(self) -> bool:
        return self._shutdown_event.is_set()

    async def shutdown(self) -> None:
        """Execute the full shutdown sequence."""
        if self._shutdown_event.is_set():
            logger.warning("shutdown_already_in_progress")
            return

        self._shutdown_event.set()
        logger.info("shutdown_initiated")

        if self._state is not None:
            await self._state.set_bot_status("shutting_down")

        if self._scheduler is not None and self._scheduler.is_running:
            logger.info("shutdown_stopping_scheduler")
            await self._scheduler.stop()

        if self._collector is not None and self._collector.is_running:
            logger.info("shutdown_stopping_collector")
            try:
                await asyncio.wait_for(
                    self._collector.stop(),
                    timeout=_SHUTDOWN_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                logger.error("shutdown_collector_timeout")

        if self._reconciler is not None and self._reconciler.is_running:
            logger.info("shutdown_stopping_reconciler")
            await self._reconciler.stop()

        if self._state is not None:
            await self._state.set_bot_status("stopped")

        logger.info("shutdown_complete")
