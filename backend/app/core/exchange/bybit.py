"""Bybit exchange connector via ccxt async."""

from __future__ import annotations

from datetime import UTC, datetime

import ccxt.async_support as ccxt

from app.config import get_settings
from app.core.exchange.base import BaseExchangeConnector
from app.core.exchange.types import (
    Balance,
    FundingRateData,
    OrderBook,
    OrderBookLevel,
    OrderResult,
    Ticker,
)


class BybitConnector(BaseExchangeConnector):
    def __init__(self) -> None:
        super().__init__("bybit")

    async def connect(self) -> None:
        settings = get_settings()
        self._exchange = ccxt.bybit(
            {
                "apiKey": settings.bybit_api_key or None,
                "secret": settings.bybit_api_secret or None,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "spot",
                },
            }
        )
        await self._exchange.load_markets()
        self.logger.info("exchange_connected", markets=len(self._exchange.markets))

    async def fetch_ticker(self, symbol: str) -> Ticker:
        raw = await self._exchange.fetch_ticker(symbol)
        return Ticker(
            exchange=self.exchange_id,
            symbol=symbol,
            bid=float(raw.get("bid", 0)),
            ask=float(raw.get("ask", 0)),
            last=float(raw.get("last", 0)),
        )

    async def fetch_funding_rate(self, symbol: str) -> FundingRateData:
        perp = self._perp_symbol(symbol)
        raw = await self._exchange.fetch_funding_rate(perp)

        next_time = None
        if raw.get("fundingDatetime"):
            next_time = datetime.fromisoformat(raw["fundingDatetime"].replace("Z", "+00:00"))
        elif raw.get("fundingTimestamp"):
            next_time = datetime.fromtimestamp(raw["fundingTimestamp"] / 1000, tz=UTC)

        return FundingRateData(
            exchange=self.exchange_id,
            symbol=symbol,
            funding_rate=float(raw.get("fundingRate", 0)),
            predicted_rate=_safe_float(raw.get("nextFundingRate")),
            mark_price=_safe_float(raw.get("markPrice")),
            index_price=_safe_float(raw.get("indexPrice")),
            next_funding_time=next_time,
        )

    async def fetch_order_book(self, symbol: str, limit: int = 20) -> OrderBook:
        raw = await self._exchange.fetch_order_book(symbol, limit=limit)
        return OrderBook(
            exchange=self.exchange_id,
            symbol=symbol,
            bids=[OrderBookLevel(price=b[0], qty=b[1]) for b in raw.get("bids", [])],
            asks=[OrderBookLevel(price=a[0], qty=a[1]) for a in raw.get("asks", [])],
        )

    async def fetch_balance(self) -> list[Balance]:
        raw = await self._exchange.fetch_balance()
        balances = []
        for currency, data in raw.get("total", {}).items():
            total = float(data) if data else 0
            if total > 0:
                free = float(raw.get("free", {}).get(currency, 0) or 0)
                used = float(raw.get("used", {}).get(currency, 0) or 0)
                balances.append(Balance(currency=currency, free=free, used=used))
        return balances

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        *,
        is_perp: bool = False,
    ) -> OrderResult:
        target = self._perp_symbol(symbol) if is_perp else symbol
        raw = await self._exchange.create_limit_order(target, side, amount, price)
        return _parse_order(self.exchange_id, symbol, raw)

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        *,
        is_perp: bool = False,
    ) -> OrderResult:
        target = self._perp_symbol(symbol) if is_perp else symbol
        raw = await self._exchange.create_market_order(target, side, amount)
        return _parse_order(self.exchange_id, symbol, raw)

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        try:
            await self._exchange.cancel_order(order_id, symbol)
            return True
        except ccxt.OrderNotFound:
            self.logger.warning("cancel_order_not_found", order_id=order_id)
            return False

    async def fetch_order(self, order_id: str, symbol: str) -> OrderResult:
        raw = await self._exchange.fetch_order(order_id, symbol)
        return _parse_order(self.exchange_id, symbol, raw)


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_order(exchange_id: str, symbol: str, raw: dict) -> OrderResult:
    return OrderResult(
        order_id=str(raw.get("id", "")),
        exchange=exchange_id,
        symbol=symbol,
        side=raw.get("side", ""),
        qty=float(raw.get("amount", 0)),
        price=float(raw.get("price", 0) or raw.get("average", 0) or 0),
        filled_qty=float(raw.get("filled", 0)),
        status=raw.get("status", "unknown"),
        fee=float(raw.get("fee", {}).get("cost", 0) or 0) if raw.get("fee") else 0.0,
    )
