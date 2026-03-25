"""Multi-strategy scheduler: orchestrates Funding Arb, Grid, and Carry strategies.

Runs each strategy on its own tick interval and routes signals to the
appropriate executor. All positions are tracked with a strategy label.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid

import structlog

from app.core.data.state import StateStore
from app.core.execution.paper import PaperExecutor, PaperPosition
from app.core.metrics import evaluation_cycle_duration_seconds, signals_generated_total
from app.core.risk.manager import RiskManager
from app.core.strategy.carry import CarryPosition, CarryStrategy
from app.core.strategy.funding_arb import FundingArbStrategy
from app.core.strategy.grid import GridPosition, GridStrategy
from app.core.strategy.signals import SignalType
from app.services.event_logger import EventLogger

logger = structlog.get_logger(__name__)

_FUNDING_TICK_SECONDS = 2.0
_GRID_TICK_SECONDS = 5.0
_CARRY_TICK_SECONDS = 10.0


class MultiStrategyScheduler:
    """Runs three strategies in parallel with separate tick loops."""

    def __init__(
        self,
        funding_strategy: FundingArbStrategy,
        grid_strategy: GridStrategy,
        carry_strategy: CarryStrategy,
        risk_manager: RiskManager,
        executor: PaperExecutor,
        state: StateStore,
        event_logger: EventLogger | None = None,
    ) -> None:
        self._funding = funding_strategy
        self._grid = grid_strategy
        self._carry = carry_strategy
        self._risk = risk_manager
        self._executor = executor
        self._state = state
        self._event_logger = event_logger
        self._running = False
        self._tasks: list[asyncio.Task] = []

        self._grid_positions: dict[str, GridPosition] = {}
        self._carry_positions: dict[str, CarryPosition] = {}

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def grid_positions(self) -> dict[str, GridPosition]:
        return self._grid_positions

    @property
    def carry_positions(self) -> dict[str, CarryPosition]:
        return self._carry_positions

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self._state.set_bot_status("running")

        self._tasks = [
            asyncio.create_task(
                self._loop(self._funding_tick, _FUNDING_TICK_SECONDS),
                name="funding_loop",
            ),
            asyncio.create_task(
                self._loop(self._grid_tick, _GRID_TICK_SECONDS),
                name="grid_loop",
            ),
            asyncio.create_task(
                self._loop(self._carry_tick, _CARRY_TICK_SECONDS),
                name="carry_loop",
            ),
        ]
        logger.info("multi_scheduler_started")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        await self._state.set_bot_status("stopped")

        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        logger.info("multi_scheduler_stopped")

    async def _loop(self, tick_fn, interval: float) -> None:
        while self._running:
            try:
                await tick_fn()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("tick_error", fn=tick_fn.__name__, error=str(exc))
            await asyncio.sleep(interval)

    async def _funding_tick(self) -> None:
        start = time.monotonic()
        open_positions = self._executor.get_open_positions_as_dicts()

        signal = await self._funding.evaluate(
            state=self._state,
            risk_manager=self._risk,
            open_positions=open_positions,
        )

        signals_generated_total.labels(type=signal.type.value).inc()

        if signal.type != SignalType.HOLD:
            size_usd = None
            if signal.opportunity is not None:
                capital = self._risk._portfolio.total_capital
                size_usd = self._funding._dynamic_size(signal.opportunity.score, capital)

            result = await self._executor.execute_signal(signal, position_size_usd=size_usd)
            if result is not None:
                result.strategy = "funding_arb"
                logger.info(
                    "funding_signal_executed",
                    position_id=result.id,
                    reason=signal.reason,
                )
                if self._event_logger and signal.opportunity:
                    opp = signal.opportunity
                    await self._event_logger.info(
                        "funding_arb",
                        f"Position opened: {opp.exchange}:{opp.symbol}"
                        f" | ${size_usd or 0:.2f}"
                        f" | rate={opp.funding_rate:.6f}",
                        position_id=result.id,
                        exchange=opp.exchange,
                        symbol=opp.symbol,
                        strategy="funding_arb",
                    )

        evaluation_cycle_duration_seconds.observe(time.monotonic() - start)

    async def _grid_tick(self) -> None:
        signal = await self._grid.evaluate(
            state=self._state,
            open_grids=self._grid_positions,
        )

        if signal.action == "open":
            pos_id = str(uuid.uuid4())
            ticker = await self._state.get_ticker(signal.exchange, signal.symbol)
            mid_price = 0.0
            if ticker:
                with contextlib.suppress(TypeError, ValueError):
                    mid_price = (float(ticker.get("bid", 0)) + float(ticker.get("ask", 0))) / 2

            capital = self._risk._portfolio.total_capital
            size_usd = min(capital * 0.05, 200.0) * max(0.5, signal.score)
            qty_per = size_usd / mid_price / 10 if mid_price > 0 else 0

            grid = GridPosition(
                id=pos_id,
                exchange=signal.exchange,
                symbol=signal.symbol,
                grid_low=signal.grid_low,
                grid_high=signal.grid_high,
                qty_per_level=qty_per,
            )
            self._grid_positions[signal.symbol] = grid

            paper_pos = PaperPosition(
                id=pos_id,
                exchange=signal.exchange,
                symbol=signal.symbol,
                side="GRID",
                spot_qty=qty_per * 10,
                entry_price_spot=mid_price,
            )
            paper_pos.strategy = "grid"
            self._executor._positions[pos_id] = paper_pos

            logger.info(
                "grid_position_opened",
                position_id=pos_id,
                exchange=signal.exchange,
                symbol=signal.symbol,
                grid_range=f"${signal.grid_low:.2f}-${signal.grid_high:.2f}",
            )
            if self._event_logger:
                await self._event_logger.info(
                    "grid",
                    f"Grid opened: {signal.exchange}:{signal.symbol}"
                    f" | range ${signal.grid_low:.2f}-${signal.grid_high:.2f}"
                    f" | score={signal.score:.3f}",
                    position_id=pos_id,
                    exchange=signal.exchange,
                    symbol=signal.symbol,
                    strategy="grid",
                )

        elif signal.action == "close" and signal.symbol in self._grid_positions:
            grid = self._grid_positions.pop(signal.symbol)
            paper_pos = self._executor._positions.get(grid.id)
            if paper_pos:
                from datetime import UTC, datetime

                paper_pos.closed_at = datetime.now(UTC)

            logger.info(
                "grid_position_closed",
                symbol=signal.symbol,
                reason=signal.reason,
            )
            if self._event_logger:
                await self._event_logger.info(
                    "grid",
                    f"Grid closed: {signal.exchange}:{signal.symbol} | {signal.reason}",
                    strategy="grid",
                )

    async def _carry_tick(self) -> None:
        signal = await self._carry.evaluate(
            state=self._state,
            open_positions=self._carry_positions,
        )

        if signal.action == "entry":
            pos_id = str(uuid.uuid4())
            ticker = await self._state.get_ticker(signal.exchange, signal.symbol)
            if not ticker:
                return

            try:
                ask = float(ticker.get("ask", 0))
                bid = float(ticker.get("bid", 0))
            except (TypeError, ValueError):
                return

            if ask <= 0 or bid <= 0:
                return

            capital = self._risk._portfolio.total_capital
            size_usd = min(capital * 0.05, 200.0) * max(0.5, signal.score)
            qty = size_usd / ask if ask > 0 else 0

            carry = CarryPosition(
                id=pos_id,
                exchange=signal.exchange,
                symbol=signal.symbol,
                spot_qty=qty,
                perp_qty=qty,
                entry_price_spot=ask,
                entry_price_perp=bid,
                entry_premium_bps=signal.premium_bps,
            )
            self._carry_positions[pos_id] = carry

            paper_pos = PaperPosition(
                id=pos_id,
                exchange=signal.exchange,
                symbol=signal.symbol,
                side="LONG_SPOT_SHORT_PERP",
                spot_qty=qty,
                perp_qty=qty,
                entry_price_spot=ask,
                entry_price_perp=bid,
            )
            paper_pos.strategy = "carry"
            self._executor._positions[pos_id] = paper_pos

            logger.info(
                "carry_position_opened",
                position_id=pos_id,
                exchange=signal.exchange,
                symbol=signal.symbol,
                premium_bps=round(signal.premium_bps, 2),
            )
            if self._event_logger:
                await self._event_logger.info(
                    "carry",
                    f"Carry opened: {signal.exchange}:{signal.symbol}"
                    f" | premium={signal.premium_bps:.1f}bps"
                    f" | ${size_usd:.2f}",
                    position_id=pos_id,
                    exchange=signal.exchange,
                    symbol=signal.symbol,
                    strategy="carry",
                )

        elif signal.action == "exit" and signal.position_id in self._carry_positions:
            carry = self._carry_positions.pop(signal.position_id)
            paper_pos = self._executor._positions.get(carry.id)
            if paper_pos:
                from datetime import UTC, datetime

                paper_pos.closed_at = datetime.now(UTC)
                paper_pos.funding_collected = carry.total_profit

            logger.info(
                "carry_position_closed",
                symbol=carry.symbol,
                profit=round(carry.total_profit, 4),
                reason=signal.reason,
            )
            if self._event_logger:
                await self._event_logger.info(
                    "carry",
                    f"Carry closed: {carry.exchange}:{carry.symbol}"
                    f" | profit=${carry.total_profit:.4f}"
                    f" | {signal.reason}",
                    strategy="carry",
                )
