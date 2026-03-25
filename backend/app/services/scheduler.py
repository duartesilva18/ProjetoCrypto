"""Bot scheduler: orchestrates the strategy evaluation loop.

Runs the 2-second tick cycle:
  Health -> Risk -> Strategy -> Execution
"""

from __future__ import annotations

import asyncio
import contextlib
import time

import structlog

from app.core.data.state import StateStore
from app.core.execution.paper import PaperExecutor
from app.core.metrics import evaluation_cycle_duration_seconds, signals_generated_total
from app.core.risk.manager import RiskManager
from app.core.strategy.funding_arb import FundingArbStrategy
from app.core.strategy.signals import SignalType

logger = structlog.get_logger(__name__)

_TICK_INTERVAL_SECONDS = 2.0


class BotScheduler:
    """Main evaluation loop for the trading bot."""

    def __init__(
        self,
        strategy: FundingArbStrategy,
        risk_manager: RiskManager,
        executor: PaperExecutor,
        state: StateStore,
    ) -> None:
        self._strategy = strategy
        self._risk = risk_manager
        self._executor = executor
        self._state = state
        self._running = False
        self._task: asyncio.Task | None = None
        self._tick_count: int = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def tick_count(self) -> int:
        return self._tick_count

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self._state.set_bot_status("running")
        self._task = asyncio.create_task(self._loop(), name="bot_scheduler")
        logger.info("scheduler_started")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        await self._state.set_bot_status("stopped")

        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        logger.info("scheduler_stopped", total_ticks=self._tick_count)

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("tick_error", error=str(exc))
            await asyncio.sleep(_TICK_INTERVAL_SECONDS)

    async def _tick(self) -> None:
        """One evaluation cycle."""
        self._tick_count += 1
        start = time.monotonic()

        open_positions = self._executor.get_open_positions_as_dicts()

        signal = await self._strategy.evaluate(
            state=self._state,
            risk_manager=self._risk,
            open_positions=open_positions,
        )

        signals_generated_total.labels(type=signal.type.value).inc()

        if signal.type != SignalType.HOLD:
            result = await self._executor.execute_signal(signal)
            if result is not None:
                logger.info(
                    "signal_executed",
                    signal_type=signal.type.value,
                    position_id=result.id,
                    reason=signal.reason,
                )

        elapsed = time.monotonic() - start
        evaluation_cycle_duration_seconds.observe(elapsed)
