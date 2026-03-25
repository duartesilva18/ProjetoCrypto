"""Tests for exchange connectors -- mocked ccxt."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.exchange.binance import BinanceConnector
from app.core.exchange.bybit import BybitConnector
from app.core.exchange.factory import SUPPORTED_EXCHANGES, create_connector
from app.core.exchange.okx import OKXConnector


def test_factory_creates_binance():
    c = create_connector("binance")
    assert isinstance(c, BinanceConnector)
    assert c.exchange_id == "binance"


def test_factory_creates_bybit():
    c = create_connector("bybit")
    assert isinstance(c, BybitConnector)


def test_factory_creates_okx():
    c = create_connector("okx")
    assert isinstance(c, OKXConnector)


def test_factory_raises_on_unknown():
    with pytest.raises(ValueError, match="Unsupported exchange"):
        create_connector("kraken")


def test_supported_exchanges():
    assert "binance" in SUPPORTED_EXCHANGES
    assert "bybit" in SUPPORTED_EXCHANGES
    assert "okx" in SUPPORTED_EXCHANGES


def test_perp_symbol_conversion():
    c = create_connector("binance")
    assert c._perp_symbol("BTC/USDT") == "BTC/USDT:USDT"
    assert c._perp_symbol("ETH/USDT:USDT") == "ETH/USDT:USDT"


@pytest.mark.asyncio
async def test_binance_fetch_ticker():
    connector = BinanceConnector()
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ticker = AsyncMock(
        return_value={
            "bid": 67000.0,
            "ask": 67010.0,
            "last": 67005.0,
        }
    )
    connector._exchange = mock_exchange

    ticker = await connector.fetch_ticker("BTC/USDT")
    assert ticker.exchange == "binance"
    assert ticker.symbol == "BTC/USDT"
    assert ticker.bid == 67000.0
    assert ticker.ask == 67010.0


@pytest.mark.asyncio
async def test_binance_fetch_funding_rate():
    connector = BinanceConnector()
    mock_exchange = AsyncMock()
    mock_exchange.fetch_funding_rate = AsyncMock(
        return_value={
            "fundingRate": 0.0001,
            "nextFundingRate": 0.00008,
            "markPrice": 67000.0,
            "indexPrice": 66990.0,
            "fundingTimestamp": 1711382400000,
        }
    )
    connector._exchange = mock_exchange

    rate = await connector.fetch_funding_rate("BTC/USDT")
    assert rate.exchange == "binance"
    assert rate.funding_rate == 0.0001
    assert rate.predicted_rate == 0.00008
    assert rate.mark_price == 67000.0
    assert rate.next_funding_time is not None


@pytest.mark.asyncio
async def test_binance_fetch_order_book():
    connector = BinanceConnector()
    mock_exchange = AsyncMock()
    mock_exchange.fetch_order_book = AsyncMock(
        return_value={
            "bids": [[67000.0, 1.5], [66990.0, 2.0]],
            "asks": [[67010.0, 1.0], [67020.0, 3.0]],
        }
    )
    connector._exchange = mock_exchange

    ob = await connector.fetch_order_book("BTC/USDT")
    assert len(ob.bids) == 2
    assert len(ob.asks) == 2
    assert ob.bids[0].price == 67000.0
    assert ob.asks[0].qty == 1.0


@pytest.mark.asyncio
async def test_binance_fetch_balance():
    connector = BinanceConnector()
    mock_exchange = AsyncMock()
    mock_exchange.fetch_balance = AsyncMock(
        return_value={
            "total": {"USDT": 10000.0, "BTC": 0.5},
            "free": {"USDT": 8000.0, "BTC": 0.3},
            "used": {"USDT": 2000.0, "BTC": 0.2},
        }
    )
    connector._exchange = mock_exchange

    balances = await connector.fetch_balance()
    assert len(balances) == 2
    usdt = next(b for b in balances if b.currency == "USDT")
    assert usdt.free == 8000.0
    assert usdt.total == 10000.0


@pytest.mark.asyncio
async def test_connector_disconnect():
    connector = BinanceConnector()
    mock_exchange = AsyncMock()
    connector._exchange = mock_exchange

    assert connector.is_connected is True
    await connector.disconnect()
    assert connector.is_connected is False
    mock_exchange.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_funding_rates_handles_partial_failures():
    """If one symbol fails, others should still be collected."""
    connector = BinanceConnector()
    mock_exchange = AsyncMock()

    call_count = 0

    async def mock_fetch(symbol):
        nonlocal call_count
        call_count += 1
        if "ETH" in symbol:
            raise Exception("rate limit")
        return {
            "fundingRate": 0.0001,
            "markPrice": 67000.0,
        }

    mock_exchange.fetch_funding_rate = mock_fetch
    connector._exchange = mock_exchange

    rates = await connector.fetch_funding_rates(["BTC/USDT", "ETH/USDT", "SOL/USDT"])
    assert len(rates) == 2  # ETH failed, BTC and SOL succeeded
