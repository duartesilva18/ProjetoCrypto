"""Tests for exchange data transfer objects."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.exchange.types import (
    Balance,
    FundingRateData,
    OrderBook,
    OrderBookLevel,
    OrderResult,
    Ticker,
)


def test_ticker_mid_and_spread():
    t = Ticker(exchange="binance", symbol="BTC/USDT", bid=100.0, ask=100.10, last=100.05)
    assert t.mid == 100.05
    assert round(t.spread_bps, 2) == 10.0


def test_ticker_zero_mid():
    t = Ticker(exchange="binance", symbol="X/Y", bid=0.0, ask=0.0, last=0.0)
    assert t.spread_bps == 0.0


def test_funding_rate_time_to_funding():
    future = datetime.now(UTC) + timedelta(hours=4)
    fr = FundingRateData(
        exchange="bybit",
        symbol="BTC/USDT",
        funding_rate=0.0001,
        next_funding_time=future,
    )
    ttf = fr.time_to_funding_seconds
    assert ttf is not None
    assert 14300 < ttf < 14500  # ~4 hours in seconds


def test_funding_rate_no_next_time():
    fr = FundingRateData(exchange="okx", symbol="ETH/USDT", funding_rate=-0.0002)
    assert fr.time_to_funding_seconds is None


def test_order_book_depth():
    ob = OrderBook(
        exchange="binance",
        symbol="BTC/USDT",
        bids=[
            OrderBookLevel(price=100.0, qty=1.0),
            OrderBookLevel(price=99.95, qty=2.0),
            OrderBookLevel(price=99.80, qty=5.0),
        ],
        asks=[
            OrderBookLevel(price=100.10, qty=1.5),
            OrderBookLevel(price=100.20, qty=3.0),
            OrderBookLevel(price=100.50, qty=10.0),
        ],
    )
    bid_depth = ob.bid_depth_at(slippage_bps=10.0)
    assert bid_depth == 3.0  # 100.0 and 99.95 within 10bps of 100.0

    ask_depth = ob.ask_depth_at(slippage_bps=10.0)
    assert ask_depth == 4.5  # 100.10 and 100.20 within 10bps of 100.10


def test_order_book_empty():
    ob = OrderBook(exchange="bybit", symbol="X/Y", bids=[], asks=[])
    assert ob.bid_depth_at() == 0.0
    assert ob.ask_depth_at() == 0.0


def test_balance_total():
    b = Balance(currency="USDT", free=1000.0, used=500.0)
    assert b.total == 1500.0


def test_order_result_is_filled():
    filled = OrderResult(
        order_id="123",
        exchange="binance",
        symbol="BTC/USDT",
        side="buy",
        qty=1.0,
        price=100.0,
        filled_qty=1.0,
        status="closed",
    )
    assert filled.is_filled is True

    pending = OrderResult(
        order_id="456",
        exchange="binance",
        symbol="BTC/USDT",
        side="sell",
        qty=1.0,
        price=100.0,
        filled_qty=0.0,
        status="open",
    )
    assert pending.is_filled is False
