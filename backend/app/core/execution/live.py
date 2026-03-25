"""Live executor: real order execution with graduated TWAP.

Splits orders into multiple steps to reduce market impact.
Ensures atomic position opening -- both legs (spot + perp) must fill
or the entire operation is rolled back.
"""

from __future__ import annotations

import asyncio
import time
import uuid

import structlog

from app.core.exchange.base import BaseExchangeConnector
from app.core.exchange.types import OrderResult
from app.core.execution.engine import BaseExecutor, ExecutionResult
from app.core.metrics import execution_latency_seconds, trades_executed_total
from app.core.strategy.signals import Signal

logger = structlog.get_logger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 0.5


class LiveExecutor(BaseExecutor):
    """Executes real orders on exchanges with TWAP and rollback."""

    def __init__(
        self,
        connectors: dict[str, BaseExchangeConnector],
        twap_steps: int = 3,
        step_delay_seconds: float = 3.0,
    ) -> None:
        self._connectors = connectors
        self._twap_steps = max(1, twap_steps)
        self._step_delay = step_delay_seconds
        self._open_positions: dict[str, dict] = {}
        self._log = logger.bind(executor="live")

    async def execute_entry(self, signal: Signal) -> ExecutionResult:
        opp = signal.opportunity
        if opp is None:
            return ExecutionResult(success=False, error="No opportunity in signal")

        connector = self._connectors.get(opp.exchange)
        if connector is None or not connector.is_connected:
            return ExecutionResult(
                success=False,
                error=f"Exchange {opp.exchange} not connected",
            )

        position_id = str(uuid.uuid4())
        start = time.monotonic()
        log = self._log.bind(
            position_id=position_id,
            exchange=opp.exchange,
            symbol=opp.symbol,
        )

        spot_fills: list[OrderResult] = []
        perp_fills: list[OrderResult] = []

        try:
            total_qty = await self._calculate_qty(connector, opp.symbol)
            step_qty = round(total_qty / self._twap_steps, 8)

            spot_side = "buy" if opp.funding_rate > 0 else "sell"
            perp_side = "sell" if opp.funding_rate > 0 else "buy"

            for step in range(self._twap_steps):
                log.info("twap_step", step=step + 1, total=self._twap_steps)

                spot_result = await self._place_with_retry(
                    connector, opp.symbol, spot_side, step_qty, is_perp=False
                )
                spot_fills.append(spot_result)

                if not spot_result.is_filled:
                    raise ExecutionError(
                        f"Spot order failed at step {step + 1}: {spot_result.status}"
                    )

                perp_result = await self._place_with_retry(
                    connector, opp.symbol, perp_side, step_qty, is_perp=True
                )
                perp_fills.append(perp_result)

                if not perp_result.is_filled:
                    raise ExecutionError(
                        f"Perp order failed at step {step + 1}: {perp_result.status}"
                    )

                trades_executed_total.labels(
                    exchange=opp.exchange,
                    symbol=opp.symbol,
                    side=spot_side,
                    market="SPOT",
                ).inc()
                trades_executed_total.labels(
                    exchange=opp.exchange,
                    symbol=opp.symbol,
                    side=perp_side,
                    market="PERP",
                ).inc()

                if step < self._twap_steps - 1:
                    await asyncio.sleep(self._step_delay)

            position = self._build_position(position_id, opp, spot_fills, perp_fills)
            self._open_positions[position_id] = position

            elapsed = time.monotonic() - start
            execution_latency_seconds.labels(exchange=opp.exchange).observe(elapsed)

            log.info(
                "position_opened",
                elapsed_s=round(elapsed, 3),
                spot_fills=len(spot_fills),
                perp_fills=len(perp_fills),
            )

            return ExecutionResult(
                success=True,
                position_id=position_id,
                mode="live",
                details=position,
            )

        except ExecutionError as exc:
            log.error("execution_failed", error=str(exc))
            await self._rollback(connector, opp.symbol, spot_fills, perp_fills, log)
            return ExecutionResult(
                success=False,
                mode="live",
                error=str(exc),
            )

        except Exception as exc:
            log.error("execution_unexpected_error", error=str(exc))
            await self._rollback(connector, opp.symbol, spot_fills, perp_fills, log)
            return ExecutionResult(
                success=False,
                mode="live",
                error=f"Unexpected: {exc}",
            )

    async def execute_exit(self, signal: Signal) -> ExecutionResult:
        pos_id = signal.position_id
        if pos_id is None or pos_id not in self._open_positions:
            return ExecutionResult(success=False, error=f"Position {pos_id} not found")

        pos = self._open_positions[pos_id]
        exchange = pos["exchange"]
        symbol = pos["symbol"]
        connector = self._connectors.get(exchange)

        if connector is None or not connector.is_connected:
            return ExecutionResult(success=False, error=f"Exchange {exchange} not connected")

        log = self._log.bind(position_id=pos_id, exchange=exchange, symbol=symbol)
        start = time.monotonic()

        try:
            close_spot_side = "sell" if pos["spot_side"] == "buy" else "buy"
            close_perp_side = "buy" if pos["perp_side"] == "sell" else "sell"

            await self._place_with_retry(
                connector, symbol, close_spot_side, pos["spot_qty"], is_perp=False
            )
            await self._place_with_retry(
                connector, symbol, close_perp_side, pos["perp_qty"], is_perp=True
            )

            del self._open_positions[pos_id]

            elapsed = time.monotonic() - start
            execution_latency_seconds.labels(exchange=exchange).observe(elapsed)
            log.info("position_closed", elapsed_s=round(elapsed, 3))

            return ExecutionResult(success=True, position_id=pos_id, mode="live")

        except Exception as exc:
            log.error("exit_failed", error=str(exc))
            return ExecutionResult(success=False, mode="live", error=str(exc))

    def get_open_positions(self) -> list[dict]:
        return list(self._open_positions.values())

    # ── Private Helpers ───────────────────────

    async def _calculate_qty(self, connector: BaseExchangeConnector, symbol: str) -> float:
        """Calculate order quantity. Uses a fixed notional for now."""
        ticker = await connector.fetch_ticker(symbol)
        if ticker.last <= 0:
            raise ExecutionError(f"Invalid price for {symbol}")
        notional = 100.0
        return round(notional / ticker.last, 8)

    async def _place_with_retry(
        self,
        connector: BaseExchangeConnector,
        symbol: str,
        side: str,
        qty: float,
        *,
        is_perp: bool,
    ) -> OrderResult:
        """Place a market order with exponential backoff retry."""
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                result = await connector.place_market_order(symbol, side, qty, is_perp=is_perp)
                return result
            except Exception as exc:
                last_error = exc
                wait = _RETRY_BACKOFF_BASE * (2**attempt)
                self._log.warning(
                    "order_retry",
                    attempt=attempt + 1,
                    max_retries=_MAX_RETRIES,
                    error=str(exc),
                    wait_s=wait,
                )
                await asyncio.sleep(wait)

        raise ExecutionError(f"Order failed after {_MAX_RETRIES} retries: {last_error}")

    async def _rollback(
        self,
        connector: BaseExchangeConnector,
        symbol: str,
        spot_fills: list[OrderResult],
        perp_fills: list[OrderResult],
        log,
    ) -> None:
        """Close any filled orders to restore delta-neutral state."""
        log.warning(
            "rollback_starting",
            spot_fills=len(spot_fills),
            perp_fills=len(perp_fills),
        )

        for fill in spot_fills:
            if fill.is_filled and fill.filled_qty > 0:
                reverse_side = "sell" if fill.side == "buy" else "buy"
                try:
                    await connector.place_market_order(
                        symbol, reverse_side, fill.filled_qty, is_perp=False
                    )
                    log.info("rollback_spot_ok", order_id=fill.order_id)
                except Exception as exc:
                    log.error(
                        "rollback_spot_failed",
                        order_id=fill.order_id,
                        error=str(exc),
                    )

        for fill in perp_fills:
            if fill.is_filled and fill.filled_qty > 0:
                reverse_side = "buy" if fill.side == "sell" else "sell"
                try:
                    await connector.place_market_order(
                        symbol, reverse_side, fill.filled_qty, is_perp=True
                    )
                    log.info("rollback_perp_ok", order_id=fill.order_id)
                except Exception as exc:
                    log.error(
                        "rollback_perp_failed",
                        order_id=fill.order_id,
                        error=str(exc),
                    )

        log.warning("rollback_complete")

    def _build_position(
        self,
        position_id: str,
        opp,
        spot_fills: list[OrderResult],
        perp_fills: list[OrderResult],
    ) -> dict:
        spot_qty = sum(f.filled_qty for f in spot_fills)
        perp_qty = sum(f.filled_qty for f in perp_fills)
        spot_avg = sum(f.price * f.filled_qty for f in spot_fills) / spot_qty if spot_qty > 0 else 0
        perp_avg = sum(f.price * f.filled_qty for f in perp_fills) / perp_qty if perp_qty > 0 else 0
        spot_side = "buy" if opp.funding_rate > 0 else "sell"
        perp_side = "sell" if opp.funding_rate > 0 else "buy"

        return {
            "id": position_id,
            "exchange": opp.exchange,
            "symbol": opp.symbol,
            "spot_side": spot_side,
            "perp_side": perp_side,
            "spot_qty": spot_qty,
            "perp_qty": perp_qty,
            "entry_price_spot": round(spot_avg, 8),
            "entry_price_perp": round(perp_avg, 8),
            "total_fees": sum(f.fee for f in spot_fills + perp_fills),
        }


class ExecutionError(Exception):
    """Raised when order execution fails in a recoverable way."""
