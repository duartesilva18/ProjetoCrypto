"""Tests for graceful shutdown manager."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.shutdown import ShutdownManager


class FakeState:
    def __init__(self):
        self.status_calls = []

    async def set_bot_status(self, status, **extra):
        self.status_calls.append(status)


@pytest.mark.asyncio
async def test_shutdown_sequence():
    scheduler = AsyncMock()
    scheduler.is_running = True
    collector = AsyncMock()
    collector.is_running = True
    reconciler = AsyncMock()
    reconciler.is_running = True
    state = FakeState()

    mgr = ShutdownManager(
        scheduler=scheduler,
        collector=collector,
        reconciler=reconciler,
        state=state,
    )

    assert mgr.is_shutting_down is False

    await mgr.shutdown()

    assert mgr.is_shutting_down is True
    scheduler.stop.assert_awaited_once()
    collector.stop.assert_awaited_once()
    reconciler.stop.assert_awaited_once()
    assert state.status_calls == ["shutting_down", "stopped"]


@pytest.mark.asyncio
async def test_shutdown_idempotent():
    state = FakeState()
    mgr = ShutdownManager(state=state)

    await mgr.shutdown()
    await mgr.shutdown()

    assert state.status_calls == ["shutting_down", "stopped"]


@pytest.mark.asyncio
async def test_shutdown_skips_stopped_components():
    scheduler = AsyncMock()
    scheduler.is_running = False
    collector = AsyncMock()
    collector.is_running = False

    mgr = ShutdownManager(scheduler=scheduler, collector=collector)
    await mgr.shutdown()

    scheduler.stop.assert_not_awaited()
    collector.stop.assert_not_awaited()


@pytest.mark.asyncio
async def test_shutdown_with_no_components():
    mgr = ShutdownManager()
    await mgr.shutdown()
    assert mgr.is_shutting_down is True
