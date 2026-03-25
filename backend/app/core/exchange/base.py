"""Abstract base class for exchange connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod

import structlog

from app.core.exchange.types import (
    Balance,
    FundingRateData,
    OrderBook,
    OrderResult,
    Ticker,
)

logger = structlog.get_logger(__name__)


class BaseExchangeConnector(ABC):
    """Unified interface for all exchange interactions.

    Each concrete connector wraps ccxt async and normalizes
    exchange-specific quirks into a consistent API.
    """

    def __init__(self, exchange_id: str) -> None:
        self.exchange_id = exchange_id
        self._exchange = None
        self.logger = logger.bind(exchange=exchange_id)

    # ── Lifecycle ─────────────────────────────

    @abstractmethod
    async def connect(self) -> None:
        """Initialize the ccxt exchange instance and load markets."""

    async def disconnect(self) -> None:
        """Close the exchange connection gracefully."""
        if self._exchange is not None:
            await self._exchange.close()
            self._exchange = None
            self.logger.info("exchange_disconnected")

    @property
    def is_connected(self) -> bool:
        return self._exchange is not None

    # ── Market Data ───────────────────────────

    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> Ticker:
        """Fetch the latest ticker for a symbol."""

    @abstractmethod
    async def fetch_funding_rate(self, symbol: str) -> FundingRateData:
        """Fetch current funding rate for a perpetual symbol."""

    @abstractmethod
    async def fetch_order_book(self, symbol: str, limit: int = 20) -> OrderBook:
        """Fetch order book up to `limit` levels deep."""

    async def fetch_funding_rates(self, symbols: list[str]) -> list[FundingRateData]:
        """Fetch funding rates for multiple symbols. Override for batch support."""
        results = []
        for symbol in symbols:
            try:
                rate = await self.fetch_funding_rate(symbol)
                results.append(rate)
            except Exception as exc:
                self.logger.warning("fetch_funding_rate_failed", symbol=symbol, error=str(exc))
        return results

    # ── Account ───────────────────────────────

    @abstractmethod
    async def fetch_balance(self) -> list[Balance]:
        """Fetch account balances."""

    # ── Trading ───────────────────────────────

    @abstractmethod
    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        *,
        is_perp: bool = False,
    ) -> OrderResult:
        """Place a limit order. Set `is_perp=True` for perpetual futures."""

    @abstractmethod
    async def place_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        *,
        is_perp: bool = False,
    ) -> OrderResult:
        """Place a market order. Set `is_perp=True` for perpetual futures."""

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an open order. Returns True if successfully cancelled."""

    @abstractmethod
    async def fetch_order(self, order_id: str, symbol: str) -> OrderResult:
        """Fetch the current state of an order."""

    # ── Helpers ───────────────────────────────

    def _perp_symbol(self, symbol: str) -> str:
        """Convert spot symbol to perpetual symbol if needed.

        Override per exchange if the naming convention differs.
        Default: BTC/USDT -> BTC/USDT:USDT
        """
        if ":" not in symbol:
            base_quote = symbol.split("/")
            if len(base_quote) == 2:
                return f"{symbol}:{base_quote[1]}"
        return symbol
