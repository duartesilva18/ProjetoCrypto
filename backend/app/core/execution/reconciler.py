"""Reconciler: validates internal state against exchange reality.

Periodically polls exchange balances and positions via REST
and compares them to the bot's internal state. Flags discrepancies
and triggers circuit breaker if delta imbalance is detected.
"""

from __future__ import annotations

import asyncio
import contextlib

import structlog

from app.core.exchange.base import BaseExchangeConnector
from app.core.metrics import errors_total
from app.core.risk.circuit_breaker import CircuitBreaker

logger = structlog.get_logger(__name__)

_RECONCILE_INTERVAL_SECONDS = 30.0


class ReconcileResult:
    __slots__ = ("exchange", "healthy", "discrepancies")

    def __init__(
        self,
        exchange: str,
        healthy: bool = True,
        discrepancies: list[str] | None = None,
    ) -> None:
        self.exchange = exchange
        self.healthy = healthy
        self.discrepancies = discrepancies or []


class Reconciler:
    """Periodic state reconciliation between bot and exchanges."""

    def __init__(
        self,
        connectors: dict[str, BaseExchangeConnector],
        circuit_breaker: CircuitBreaker,
    ) -> None:
        self._connectors = connectors
        self._circuit_breaker = circuit_breaker
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_results: dict[str, ReconcileResult] = {}

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def last_results(self) -> dict[str, ReconcileResult]:
        return dict(self._last_results)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="reconciler")
        logger.info("reconciler_started")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("reconciler_stopped")

    async def reconcile_once(self, open_positions: list[dict]) -> list[ReconcileResult]:
        """Run one reconciliation cycle across all exchanges."""
        results = []

        for exchange_id, connector in self._connectors.items():
            result = await self._reconcile_exchange(exchange_id, connector, open_positions)
            self._last_results[exchange_id] = result
            results.append(result)

        return results

    async def _loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(_RECONCILE_INTERVAL_SECONDS)
                await self.reconcile_once([])
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("reconcile_loop_error", error=str(exc))
                errors_total.labels(component="reconciler", error_type=type(exc).__name__).inc()

    async def _reconcile_exchange(
        self,
        exchange_id: str,
        connector: BaseExchangeConnector,
        open_positions: list[dict],
    ) -> ReconcileResult:
        """Reconcile one exchange."""
        log = logger.bind(exchange=exchange_id)
        discrepancies: list[str] = []

        try:
            if not connector.is_connected:
                discrepancies.append("Exchange not connected")
                return ReconcileResult(
                    exchange=exchange_id,
                    healthy=False,
                    discrepancies=discrepancies,
                )

            balances = await connector.fetch_balance()
            usdt_balance = next((b for b in balances if b.currency == "USDT"), None)

            if usdt_balance is not None:
                log.debug(
                    "reconcile_balance",
                    free=usdt_balance.free,
                    used=usdt_balance.used,
                    total=usdt_balance.total,
                )

            exchange_positions = [p for p in open_positions if p.get("exchange") == exchange_id]

            for pos in exchange_positions:
                spot_value = pos.get("spot_qty", 0) * pos.get("entry_price_spot", 0)
                perp_value = pos.get("perp_qty", 0) * pos.get("entry_price_perp", 0)
                total_value = max(spot_value, perp_value)

                if total_value > 0:
                    imbalance = abs(spot_value - perp_value) / total_value
                    if imbalance > 0.02:
                        msg = f"Position {pos.get('id')}: delta imbalance {imbalance:.4%}"
                        discrepancies.append(msg)
                        log.warning("delta_imbalance", position_id=pos.get("id"))
                        self._circuit_breaker.check_delta_imbalance(
                            spot_value, perp_value, total_value
                        )

            healthy = len(discrepancies) == 0
            if not healthy:
                log.warning(
                    "reconcile_discrepancies",
                    count=len(discrepancies),
                    details=discrepancies,
                )

            return ReconcileResult(
                exchange=exchange_id,
                healthy=healthy,
                discrepancies=discrepancies,
            )

        except Exception as exc:
            log.error("reconcile_exchange_error", error=str(exc))
            errors_total.labels(component="reconciler", error_type=type(exc).__name__).inc()
            return ReconcileResult(
                exchange=exchange_id,
                healthy=False,
                discrepancies=[f"Error: {exc}"],
            )
