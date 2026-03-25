"""Simulated funding payment loop for paper trading.

Applies fake funding payments to open paper positions every interval,
using the real funding rate from Redis but calculating a simulated payment
based on position notional value.

In production (live mode), this would be replaced by reading actual
funding payments from the exchange API.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.data.models import FundingPayment
from app.core.data.state import StateStore
from app.core.execution.paper import PaperExecutor
from app.core.metrics import funding_payments_total
from app.services.event_logger import EventLogger

logger = structlog.get_logger(__name__)

_DEFAULT_INTERVAL_SECONDS = 60.0


class FundingPaymentLoop:
    """Periodically applies simulated funding payments to paper positions."""

    def __init__(
        self,
        executor: PaperExecutor,
        state: StateStore,
        db_session_factory: async_sessionmaker[AsyncSession] | None = None,
        interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
        event_logger: EventLogger | None = None,
    ) -> None:
        self._executor = executor
        self._state = state
        self._db_factory = db_session_factory
        self._interval = interval_seconds
        self._event_logger = event_logger
        self._running = False
        self._task: asyncio.Task | None = None
        self._total_paid: float = 0.0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def total_paid(self) -> float:
        return self._total_paid

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="funding_payment_loop")
        logger.info("funding_loop_started", interval_s=self._interval)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("funding_loop_stopped", total_paid=self._total_paid)

    async def _loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self._interval)
                await self._apply_payments()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("funding_loop_error", error=str(exc))

    async def _apply_payments(self) -> None:
        """Calculate and apply funding payments to all open positions."""
        positions = self._executor.open_positions
        if not positions:
            return

        now = datetime.now(UTC)
        db_records: list[FundingPayment] = []

        for pos in positions:
            rate_data = await self._state.get_funding_rate(pos.exchange, pos.symbol)
            if rate_data is None:
                continue

            try:
                rate = float(rate_data.get("funding_rate", 0))
            except (TypeError, ValueError):
                continue

            if rate == 0:
                continue

            notional = pos.notional_value
            if pos.side == "LONG_SPOT_SHORT_PERP":
                payment = notional * abs(rate) if rate > 0 else -notional * abs(rate)
            else:
                payment = notional * abs(rate) if rate < 0 else -notional * abs(rate)

            self._executor.apply_funding_payment(pos.id, payment)
            self._total_paid += payment

            funding_payments_total.labels(exchange=pos.exchange).inc()

            logger.info(
                "funding_payment_applied",
                position_id=pos.id,
                exchange=pos.exchange,
                symbol=pos.symbol,
                rate=rate,
                payment=round(payment, 6),
                total_collected=round(pos.funding_collected, 6),
            )

            if self._event_logger:
                await self._event_logger.info(
                    "funding_loop",
                    f"Funding payment: ${payment:+.6f} on {pos.exchange}:{pos.symbol}"
                    f" (rate={rate:.6f}, total=${pos.funding_collected:.4f})",
                    position_id=pos.id,
                    exchange=pos.exchange,
                    symbol=pos.symbol,
                    rate=rate,
                    payment=round(payment, 6),
                )

            db_records.append(
                FundingPayment(
                    id=uuid.uuid4(),
                    timestamp=now,
                    position_id=None,
                    exchange=pos.exchange,
                    symbol=pos.symbol,
                    payment=payment,
                    rate=rate,
                )
            )

        if db_records and self._db_factory is not None:
            try:
                async with self._db_factory() as session:
                    session.add_all(db_records)
                    await session.commit()
            except Exception as exc:
                logger.error("funding_payment_db_error", error=str(exc))

        await self._state.publish_position_event(
            {
                "type": "funding_payment",
                "count": len(db_records),
                "total": round(self._total_paid, 4),
                "timestamp": now.isoformat(),
            }
        )
