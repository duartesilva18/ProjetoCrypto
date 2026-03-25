"""WebSocket price feed manager for Binance and Bybit.

Provides real-time ticker updates via exchange WebSocket streams,
with automatic reconnection and fallback to REST polling.
"""

from __future__ import annotations

import asyncio
import json

import structlog

from app.core.data.state import StateStore
from app.core.exchange.types import Ticker
from app.core.metrics import websocket_connected

logger = structlog.get_logger(__name__)

_RECONNECT_DELAY_SECONDS = 5.0
_MAX_RECONNECT_DELAY_SECONDS = 60.0
_PING_INTERVAL_SECONDS = 30.0


def _binance_ws_url(symbols: list[str]) -> str:
    """Build a combined Binance ticker stream URL."""
    streams = [f"{s.replace('/', '').lower()}@ticker" for s in symbols]
    return f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"


def _bybit_ws_topics(symbols: list[str]) -> list[str]:
    """Build Bybit ticker subscription topics."""
    return [f"tickers.{s.replace('/', '')}" for s in symbols]


class WebSocketFeedManager:
    """Manages WebSocket connections to Binance and Bybit for real-time prices."""

    def __init__(self, state: StateStore, symbols: list[str]) -> None:
        self._state = state
        self._symbols = symbols
        self._running = False
        self._tasks: list[asyncio.Task] = []

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        self._tasks.append(asyncio.create_task(self._binance_loop(), name="ws_binance"))
        self._tasks.append(asyncio.create_task(self._bybit_loop(), name="ws_bybit"))
        logger.info("ws_feed_started", symbols=self._symbols)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("ws_feed_stopped")

    async def _binance_loop(self) -> None:
        """Connect to Binance combined ticker stream with reconnection."""
        delay = _RECONNECT_DELAY_SECONDS
        try:
            import websockets
        except ImportError:
            logger.warning("websockets_not_installed", hint="pip install websockets")
            return

        url = _binance_ws_url(self._symbols)

        while self._running:
            try:
                async with websockets.connect(url, ping_interval=_PING_INTERVAL_SECONDS) as ws:
                    websocket_connected.labels(exchange="binance_ws").set(1)
                    delay = _RECONNECT_DELAY_SECONDS
                    logger.info("binance_ws_connected")

                    async for raw_msg in ws:
                        if not self._running:
                            break
                        await self._handle_binance_message(raw_msg)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                websocket_connected.labels(exchange="binance_ws").set(0)
                logger.warning("binance_ws_error", error=str(exc), reconnect_in=delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, _MAX_RECONNECT_DELAY_SECONDS)

        websocket_connected.labels(exchange="binance_ws").set(0)

    async def _bybit_loop(self) -> None:
        """Connect to Bybit V5 public ticker stream with reconnection."""
        delay = _RECONNECT_DELAY_SECONDS
        try:
            import websockets
        except ImportError:
            logger.warning("websockets_not_installed")
            return

        url = "wss://stream.bybit.com/v5/public/spot"
        topics = _bybit_ws_topics(self._symbols)

        while self._running:
            try:
                async with websockets.connect(url, ping_interval=_PING_INTERVAL_SECONDS) as ws:
                    sub_msg = json.dumps({"op": "subscribe", "args": topics})
                    await ws.send(sub_msg)
                    websocket_connected.labels(exchange="bybit_ws").set(1)
                    delay = _RECONNECT_DELAY_SECONDS
                    logger.info("bybit_ws_connected")

                    async for raw_msg in ws:
                        if not self._running:
                            break
                        await self._handle_bybit_message(raw_msg)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                websocket_connected.labels(exchange="bybit_ws").set(0)
                logger.warning("bybit_ws_error", error=str(exc), reconnect_in=delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, _MAX_RECONNECT_DELAY_SECONDS)

        websocket_connected.labels(exchange="bybit_ws").set(0)

    async def _handle_binance_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
            data = msg.get("data", msg)
            symbol_raw = data.get("s", "")
            if not symbol_raw:
                return

            symbol = _binance_symbol_to_standard(symbol_raw)
            if symbol not in self._symbols:
                return

            bid = float(data.get("b", 0))
            ask = float(data.get("a", 0))
            last = float(data.get("c", 0))

            if bid > 0 and ask > 0:
                ticker = Ticker(exchange="binance", symbol=symbol, bid=bid, ask=ask, last=last)
                await self._state.update_ticker(ticker)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass

    async def _handle_bybit_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
            if msg.get("op") or not msg.get("data"):
                return

            data = msg["data"]
            symbol_raw = data.get("symbol", "")
            if not symbol_raw:
                return

            symbol = _bybit_symbol_to_standard(symbol_raw)
            if symbol not in self._symbols:
                return

            bid = float(data.get("bid1Price", 0))
            ask = float(data.get("ask1Price", 0))
            last = float(data.get("lastPrice", 0))

            if bid > 0 and ask > 0:
                ticker = Ticker(exchange="bybit", symbol=symbol, bid=bid, ask=ask, last=last)
                await self._state.update_ticker(ticker)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass


def _binance_symbol_to_standard(raw: str) -> str:
    """BTCUSDT -> BTC/USDT"""
    for quote in ("USDT", "USDC", "BUSD", "BTC", "ETH"):
        if raw.endswith(quote):
            base = raw[: -len(quote)]
            return f"{base}/{quote}"
    return raw


def _bybit_symbol_to_standard(raw: str) -> str:
    """BTCUSDT -> BTC/USDT"""
    for quote in ("USDT", "USDC", "BTC", "ETH"):
        if raw.endswith(quote):
            base = raw[: -len(quote)]
            return f"{base}/{quote}"
    return raw
