"""WebSocket handler for real-time streaming to the dashboard.

Clients connect to /ws and subscribe to channels:
  - funding_rates: real-time funding rate updates
  - positions: position open/close/pnl events
  - equity: equity snapshots every 60s
  - logs: bot log stream
  - bot_status: state changes
"""

from __future__ import annotations

import asyncio

import orjson
import structlog
from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from app.core.redis import get_redis

logger = structlog.get_logger(__name__)

_CHANNELS = {
    "funding_rates": "ch:market_update",
    "positions": "ch:positions",
    "bot_status": "ch:bot_status",
}


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info("ws_client_connected", total=len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info("ws_client_disconnected", total=len(self._connections))

    async def broadcast(self, message: bytes) -> None:
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_bytes(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


async def websocket_endpoint(ws: WebSocket) -> None:
    """Main WebSocket handler.

    After connecting, the client sends JSON messages to subscribe:
      {"subscribe": ["funding_rates", "bot_status"]}

    The server then forwards matching Redis pub-sub events.
    """
    await manager.connect(ws)
    subscribed_channels: set[str] = set()
    pubsub_task: asyncio.Task | None = None

    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = orjson.loads(data)
            except (orjson.JSONDecodeError, TypeError):
                await ws.send_bytes(orjson.dumps({"error": "Invalid JSON"}))
                continue

            if "subscribe" in msg and isinstance(msg["subscribe"], list):
                for ch_name in msg["subscribe"]:
                    if ch_name in _CHANNELS:
                        subscribed_channels.add(_CHANNELS[ch_name])

                if pubsub_task is not None:
                    pubsub_task.cancel()

                if subscribed_channels:
                    pubsub_task = asyncio.create_task(_relay_pubsub(ws, subscribed_channels))

                await ws.send_bytes(
                    orjson.dumps(
                        {
                            "subscribed": list(subscribed_channels),
                        }
                    )
                )

            elif "ping" in msg:
                await ws.send_bytes(orjson.dumps({"pong": True}))

    except WebSocketDisconnect:
        pass
    finally:
        if pubsub_task is not None:
            pubsub_task.cancel()
        manager.disconnect(ws)


async def _relay_pubsub(ws: WebSocket, channels: set[str]) -> None:
    """Subscribe to Redis channels and forward messages to a WS client."""
    r: Redis = await get_redis()
    pubsub = r.pubsub()

    try:
        await pubsub.subscribe(*channels)

        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg is not None and msg.get("type") == "message":
                payload = msg.get("data", b"")
                if isinstance(payload, str):
                    payload = payload.encode()
                await ws.send_bytes(payload)
            else:
                await asyncio.sleep(0.1)

    except asyncio.CancelledError:
        pass
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(*channels)
        await pubsub.close()
