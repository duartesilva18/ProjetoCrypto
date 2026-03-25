"""DataCollector: real-time market data ingestion from exchanges.

Connects to multiple exchanges via REST polling (WebSocket upgrade path in future).
Collects funding rates and prices, persists to TimescaleDB in batches,
and updates the Redis-backed StateStore for real-time access.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.data.models import FundingRate
from app.core.data.state import StateStore
from app.core.exchange.base import BaseExchangeConnector
from app.core.exchange.types import FundingRateData
from app.core.metrics import errors_total, funding_rate_current, websocket_connected

logger = structlog.get_logger(__name__)

_POLL_INTERVAL_SECONDS = 5.0
_BATCH_FLUSH_INTERVAL_SECONDS = 5.0
_MAX_CONSECUTIVE_ERRORS = 5
_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 30.0


class DataCollector:
    """Collects funding rates and prices from multiple exchanges.

    Manages polling loops per exchange, batches DB writes,
    and feeds the StateStore with real-time data.
    """

    def __init__(
        self,
        connectors: dict[str, BaseExchangeConnector],
        state: StateStore,
        symbols: list[str],
        db_session_factory=None,
    ) -> None:
        self._connectors = connectors
        self._state = state
        self._symbols = symbols
        self._db_session_factory = db_session_factory
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._funding_buffer: list[FundingRate] = []
        self._buffer_lock = asyncio.Lock()
        self._error_counts: dict[str, int] = {eid: 0 for eid in connectors}

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        logger.info(
            "data_collector_starting",
            exchanges=list(self._connectors.keys()),
            symbols=self._symbols,
        )

        for exchange_id, connector in self._connectors.items():
            task = asyncio.create_task(
                self._poll_loop(exchange_id, connector),
                name=f"poll_{exchange_id}",
            )
            self._tasks.append(task)

        flush_task = asyncio.create_task(self._flush_loop(), name="db_flush")
        self._tasks.append(flush_task)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        logger.info("data_collector_stopping")

        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        await self._flush_buffer()
        logger.info("data_collector_stopped")

    async def _poll_loop(self, exchange_id: str, connector: BaseExchangeConnector) -> None:
        """Continuously poll one exchange for funding rates and prices."""
        backoff = 0.0
        log = logger.bind(exchange=exchange_id)

        while self._running:
            try:
                if backoff > 0:
                    log.info("poll_backoff", seconds=backoff)
                    await asyncio.sleep(backoff)

                await self._poll_once(exchange_id, connector)

                self._error_counts[exchange_id] = 0
                backoff = 0.0
                websocket_connected.labels(exchange=exchange_id).set(1)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._error_counts[exchange_id] += 1
                errors_total.labels(component="data_collector", error_type=type(exc).__name__).inc()
                websocket_connected.labels(exchange=exchange_id).set(0)

                log.error(
                    "poll_error",
                    error=str(exc),
                    consecutive_errors=self._error_counts[exchange_id],
                )

                backoff = min(
                    _BACKOFF_BASE_SECONDS * (2 ** (self._error_counts[exchange_id] - 1)),
                    _BACKOFF_MAX_SECONDS,
                )

                if self._error_counts[exchange_id] >= _MAX_CONSECUTIVE_ERRORS:
                    log.critical(
                        "exchange_unhealthy",
                        consecutive_errors=self._error_counts[exchange_id],
                    )

            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    async def _poll_once(self, exchange_id: str, connector: BaseExchangeConnector) -> None:
        """Single poll cycle: fetch funding rates + tickers for all symbols."""
        now = datetime.now(UTC)

        funding_rates = await connector.fetch_funding_rates(self._symbols)
        for rate in funding_rates:
            await self._state.update_funding(rate)
            funding_rate_current.labels(exchange=exchange_id, symbol=rate.symbol).set(
                rate.funding_rate
            )
            await self._buffer_funding_rate(rate, now)

        for symbol in self._symbols:
            try:
                ticker = await connector.fetch_ticker(symbol)
                await self._state.update_ticker(ticker)
            except Exception as exc:
                logger.warning(
                    "fetch_ticker_failed",
                    exchange=exchange_id,
                    symbol=symbol,
                    error=str(exc),
                )

    async def _buffer_funding_rate(self, rate: FundingRateData, timestamp: datetime) -> None:
        """Add a funding rate record to the batch insert buffer."""
        record = FundingRate(
            timestamp=timestamp,
            exchange=rate.exchange,
            symbol=rate.symbol,
            funding_rate=rate.funding_rate,
            predicted_rate=rate.predicted_rate,
            mark_price=rate.mark_price,
            index_price=rate.index_price,
        )
        async with self._buffer_lock:
            self._funding_buffer.append(record)

    async def _flush_loop(self) -> None:
        """Periodically flush the funding rate buffer to TimescaleDB."""
        while self._running:
            try:
                await asyncio.sleep(_BATCH_FLUSH_INTERVAL_SECONDS)
                await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("flush_error", error=str(exc))
                errors_total.labels(component="data_collector", error_type="flush_error").inc()

    async def _flush_buffer(self) -> None:
        """Flush accumulated funding rate records to the database."""
        if self._db_session_factory is None:
            return

        async with self._buffer_lock:
            if not self._funding_buffer:
                return
            to_flush = list(self._funding_buffer)
            self._funding_buffer.clear()

        try:
            async with self._db_session_factory() as session:
                session: AsyncSession
                session.add_all(to_flush)
                await session.commit()
                logger.debug("buffer_flushed", records=len(to_flush))
        except Exception as exc:
            logger.error("flush_to_db_failed", error=str(exc), records=len(to_flush))
            async with self._buffer_lock:
                self._funding_buffer.extend(to_flush)

    def get_error_count(self, exchange_id: str) -> int:
        return self._error_counts.get(exchange_id, 0)

    def is_exchange_healthy(self, exchange_id: str) -> bool:
        return self._error_counts.get(exchange_id, 0) < _MAX_CONSECUTIVE_ERRORS
