"""Tests for LiveExecutor, Reconciler, and ShutdownManager."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.exchange.types import Balance, OrderResult, Ticker
from app.core.execution.live import LiveExecutor
from app.core.execution.reconciler import Reconciler
from app.core.risk.circuit_breaker import CircuitBreaker
from app.core.strategy.signals import Opportunity, Signal


def _make_opportunity(
    exchange: str = "binance",
    symbol: str = "BTC/USDT",
    rate: float = 0.0005,
) -> Opportunity:
    return Opportunity(
        exchange=exchange,
        symbol=symbol,
        funding_rate=rate,
        predicted_rate=rate * 0.8,
        time_to_funding_seconds=7200,
        spread_bps=2.0,
        score=0.8,
    )


def _make_filled_order(
    side: str = "buy", qty: float = 0.001, price: float = 67000.0
) -> OrderResult:
    return OrderResult(
        order_id="ord-123",
        exchange="binance",
        symbol="BTC/USDT",
        side=side,
        qty=qty,
        price=price,
        filled_qty=qty,
        status="closed",
        fee=0.01,
    )


def _make_mock_connector(
    fill_spot: bool = True,
    fill_perp: bool = True,
) -> AsyncMock:
    connector = AsyncMock()
    connector.exchange_id = "binance"
    connector.is_connected = True
    connector.fetch_ticker = AsyncMock(
        return_value=Ticker(
            exchange="binance",
            symbol="BTC/USDT",
            bid=67000.0,
            ask=67010.0,
            last=67005.0,
        )
    )

    spot_result = _make_filled_order("buy", 0.001, 67010.0)
    perp_result = _make_filled_order("sell", 0.001, 67000.0)

    if not fill_spot:
        spot_result = OrderResult(
            order_id="ord-fail",
            exchange="binance",
            symbol="BTC/USDT",
            side="buy",
            qty=0.001,
            price=0,
            filled_qty=0,
            status="cancelled",
        )
    if not fill_perp:
        perp_result = OrderResult(
            order_id="ord-fail",
            exchange="binance",
            symbol="BTC/USDT",
            side="sell",
            qty=0.001,
            price=0,
            filled_qty=0,
            status="cancelled",
        )

    call_count = {"n": 0}

    async def mock_market_order(symbol, side, amount, *, is_perp=False):
        call_count["n"] += 1
        return perp_result if is_perp else spot_result

    connector.place_market_order = mock_market_order
    return connector


# ── LiveExecutor Tests ────────────────────────


@pytest.mark.asyncio
async def test_live_executor_successful_entry():
    connector = _make_mock_connector()
    executor = LiveExecutor(connectors={"binance": connector}, twap_steps=2, step_delay_seconds=0)

    opp = _make_opportunity()
    signal = Signal.entry(opp)
    result = await executor.execute_entry(signal)

    assert result.success is True
    assert result.position_id != ""
    assert result.mode == "live"
    assert len(executor.get_open_positions()) == 1


@pytest.mark.asyncio
async def test_live_executor_rollback_on_perp_failure():
    connector = _make_mock_connector(fill_perp=False)

    original_place = connector.place_market_order

    async def tracking_place(symbol, side, amount, *, is_perp=False):
        result = await original_place(symbol, side, amount, is_perp=is_perp)
        if not result.is_filled:
            raise Exception("Simulated perp failure")
        return result

    # Only fail on perp, not on rollback
    call_count = {"n": 0}

    async def smart_place(symbol, side, amount, *, is_perp=False):
        call_count["n"] += 1
        if is_perp and call_count["n"] <= 2:
            return OrderResult(
                order_id="fail",
                exchange="binance",
                symbol=symbol,
                side=side,
                qty=amount,
                price=0,
                filled_qty=0,
                status="cancelled",
            )
        return _make_filled_order(side, amount, 67000.0)

    connector.place_market_order = smart_place

    executor = LiveExecutor(connectors={"binance": connector}, twap_steps=1, step_delay_seconds=0)

    opp = _make_opportunity()
    signal = Signal.entry(opp)
    result = await executor.execute_entry(signal)

    assert result.success is False
    assert "failed" in result.error.lower() or "Perp" in result.error
    assert len(executor.get_open_positions()) == 0


@pytest.mark.asyncio
async def test_live_executor_exit():
    connector = _make_mock_connector()
    executor = LiveExecutor(connectors={"binance": connector}, twap_steps=1, step_delay_seconds=0)

    opp = _make_opportunity()
    entry_result = await executor.execute_entry(Signal.entry(opp))
    assert entry_result.success is True
    pos_id = entry_result.position_id

    exit_signal = Signal.exit(pos_id)
    exit_result = await executor.execute_exit(exit_signal)
    assert exit_result.success is True
    assert len(executor.get_open_positions()) == 0


@pytest.mark.asyncio
async def test_live_executor_exit_unknown_position():
    connector = _make_mock_connector()
    executor = LiveExecutor(connectors={"binance": connector})

    signal = Signal.exit("nonexistent-id")
    result = await executor.execute_exit(signal)
    assert result.success is False


@pytest.mark.asyncio
async def test_live_executor_no_connector():
    executor = LiveExecutor(connectors={})
    opp = _make_opportunity(exchange="unknown")
    signal = Signal.entry(opp)
    result = await executor.execute_entry(signal)
    assert result.success is False
    assert "not connected" in result.error


# ── Reconciler Tests ──────────────────────────


@pytest.mark.asyncio
async def test_reconciler_healthy_exchange():
    connector = AsyncMock()
    connector.is_connected = True
    connector.fetch_balance = AsyncMock(
        return_value=[Balance(currency="USDT", free=10000, used=5000)]
    )

    cb = CircuitBreaker()
    reconciler = Reconciler(connectors={"binance": connector}, circuit_breaker=cb)

    results = await reconciler.reconcile_once([])
    assert len(results) == 1
    assert results[0].healthy is True
    assert results[0].exchange == "binance"


@pytest.mark.asyncio
async def test_reconciler_disconnected_exchange():
    connector = AsyncMock()
    connector.is_connected = False

    cb = CircuitBreaker()
    reconciler = Reconciler(connectors={"binance": connector}, circuit_breaker=cb)

    results = await reconciler.reconcile_once([])
    assert results[0].healthy is False
    assert "not connected" in results[0].discrepancies[0].lower()


@pytest.mark.asyncio
async def test_reconciler_delta_imbalance_trips_breaker():
    connector = AsyncMock()
    connector.is_connected = True
    connector.fetch_balance = AsyncMock(
        return_value=[Balance(currency="USDT", free=10000, used=5000)]
    )

    cb = CircuitBreaker()
    reconciler = Reconciler(connectors={"binance": connector}, circuit_breaker=cb)

    positions = [
        {
            "id": "pos-1",
            "exchange": "binance",
            "spot_qty": 1.0,
            "entry_price_spot": 67000,
            "perp_qty": 1.0,
            "entry_price_perp": 60000,
        }
    ]

    results = await reconciler.reconcile_once(positions)
    assert results[0].healthy is False
    assert cb.is_tripped is True


@pytest.mark.asyncio
async def test_reconciler_balanced_position_ok():
    connector = AsyncMock()
    connector.is_connected = True
    connector.fetch_balance = AsyncMock(
        return_value=[Balance(currency="USDT", free=10000, used=5000)]
    )

    cb = CircuitBreaker()
    reconciler = Reconciler(connectors={"binance": connector}, circuit_breaker=cb)

    positions = [
        {
            "id": "pos-1",
            "exchange": "binance",
            "spot_qty": 1.0,
            "entry_price_spot": 67000,
            "perp_qty": 1.0,
            "entry_price_perp": 67000,
        }
    ]

    results = await reconciler.reconcile_once(positions)
    assert results[0].healthy is True
    assert cb.is_tripped is False
