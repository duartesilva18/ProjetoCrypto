"""Redis-backed hot state store for real-time market data.

Provides sub-ms reads for prices, funding rates, and position state.
Also handles pub-sub event distribution to WebSocket clients.
"""

from __future__ import annotations

import orjson
import structlog
from redis.asyncio import Redis

from app.core.exchange.types import FundingRateData, Ticker
from app.core.redis import get_redis

logger = structlog.get_logger(__name__)

_KEY_TICKER = "ticker:{exchange}:{symbol}"
_KEY_FUNDING = "funding:{exchange}:{symbol}"
_KEY_ALL_FUNDING = "funding:all"
_KEY_BOT_STATUS = "bot:status"
_CHANNEL_MARKET = "ch:market_update"
_CHANNEL_POSITIONS = "ch:positions"
_CHANNEL_BOT = "ch:bot_status"


class StateStore:
    """Central in-memory + Redis state for the trading bot."""

    def __init__(self, redis: Redis | None = None) -> None:
        self._redis = redis

    async def _get_redis(self) -> Redis:
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis

    # ── Ticker / Prices ───────────────────────

    async def update_ticker(self, ticker: Ticker) -> None:
        r = await self._get_redis()
        key = _KEY_TICKER.format(exchange=ticker.exchange, symbol=ticker.symbol)
        data = {
            "exchange": ticker.exchange,
            "symbol": ticker.symbol,
            "bid": str(ticker.bid),
            "ask": str(ticker.ask),
            "last": str(ticker.last),
            "mid": str(ticker.mid),
            "spread_bps": str(ticker.spread_bps),
            "ts": ticker.timestamp.isoformat(),
        }
        await r.hset(key, mapping=data)
        await r.publish(_CHANNEL_MARKET, orjson.dumps(data))

    async def get_ticker(self, exchange: str, symbol: str) -> dict | None:
        r = await self._get_redis()
        key = _KEY_TICKER.format(exchange=exchange, symbol=symbol)
        data = await r.hgetall(key)
        return data if data else None

    # ── Funding Rates ─────────────────────────

    async def update_funding(self, rate: FundingRateData) -> None:
        r = await self._get_redis()
        key = _KEY_FUNDING.format(exchange=rate.exchange, symbol=rate.symbol)
        data = {
            "exchange": rate.exchange,
            "symbol": rate.symbol,
            "funding_rate": str(rate.funding_rate),
            "predicted_rate": str(rate.predicted_rate) if rate.predicted_rate else "",
            "mark_price": str(rate.mark_price) if rate.mark_price else "",
            "index_price": str(rate.index_price) if rate.index_price else "",
            "next_funding_time": (
                rate.next_funding_time.isoformat() if rate.next_funding_time else ""
            ),
            "time_to_funding_s": str(rate.time_to_funding_seconds or ""),
            "ts": rate.timestamp.isoformat(),
        }
        await r.hset(key, mapping=data)
        await r.hset(
            _KEY_ALL_FUNDING,
            f"{rate.exchange}:{rate.symbol}",
            orjson.dumps(data),
        )
        await r.publish(_CHANNEL_MARKET, orjson.dumps({"type": "funding", **data}))

    async def get_funding_rate(self, exchange: str, symbol: str) -> dict | None:
        r = await self._get_redis()
        key = _KEY_FUNDING.format(exchange=exchange, symbol=symbol)
        data = await r.hgetall(key)
        return data if data else None

    async def get_all_funding_rates(self) -> dict[str, dict]:
        """Return all funding rates keyed by 'exchange:symbol'."""
        r = await self._get_redis()
        raw = await r.hgetall(_KEY_ALL_FUNDING)
        result = {}
        for composite_key, json_bytes in raw.items():
            try:
                result[composite_key] = orjson.loads(json_bytes)
            except (orjson.JSONDecodeError, TypeError):
                continue
        return result

    async def get_funding_rates_for_symbol(self, symbol: str) -> dict[str, dict]:
        """Return funding rates for a symbol across all exchanges."""
        all_rates = await self.get_all_funding_rates()
        return {key: data for key, data in all_rates.items() if data.get("symbol") == symbol}

    # ── Bot Status ────────────────────────────

    async def set_bot_status(self, status: str, **extra: str) -> None:
        r = await self._get_redis()
        data = {"status": status, **extra}
        await r.hset(_KEY_BOT_STATUS, mapping=data)
        await r.publish(_CHANNEL_BOT, orjson.dumps(data))

    async def get_bot_status(self) -> dict | None:
        r = await self._get_redis()
        data = await r.hgetall(_KEY_BOT_STATUS)
        return data if data else None

    # ── Pub/Sub Helpers ───────────────────────

    async def publish_position_event(self, event: dict) -> None:
        r = await self._get_redis()
        await r.publish(_CHANNEL_POSITIONS, orjson.dumps(event))
