"""Tests for WebSocket connection manager."""

from __future__ import annotations

import pytest

from app.api.websocket import ConnectionManager


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[bytes] = []
        self.closed = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_bytes(self, data: bytes) -> None:
        if self.closed:
            raise RuntimeError("Connection closed")
        self.sent.append(data)


@pytest.mark.asyncio
async def test_connect_and_disconnect():
    mgr = ConnectionManager()
    ws = FakeWebSocket()
    await mgr.connect(ws)
    assert mgr.count == 1

    mgr.disconnect(ws)
    assert mgr.count == 0


@pytest.mark.asyncio
async def test_broadcast():
    mgr = ConnectionManager()
    ws1, ws2 = FakeWebSocket(), FakeWebSocket()
    await mgr.connect(ws1)
    await mgr.connect(ws2)

    await mgr.broadcast(b'{"test": 1}')
    assert len(ws1.sent) == 1
    assert len(ws2.sent) == 1
    assert ws1.sent[0] == b'{"test": 1}'


@pytest.mark.asyncio
async def test_broadcast_removes_dead_connections():
    mgr = ConnectionManager()
    alive = FakeWebSocket()
    dead = FakeWebSocket()
    dead.closed = True

    await mgr.connect(alive)
    await mgr.connect(dead)
    assert mgr.count == 2

    await mgr.broadcast(b"hello")
    assert mgr.count == 1
    assert len(alive.sent) == 1


@pytest.mark.asyncio
async def test_disconnect_nonexistent():
    mgr = ConnectionManager()
    ws = FakeWebSocket()
    mgr.disconnect(ws)
    assert mgr.count == 0
