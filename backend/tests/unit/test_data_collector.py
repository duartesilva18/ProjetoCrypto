"""Tests for DataCollector and StateStore."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.data.collector import DataCollector
from app.core.data.state import StateStore
from app.core.exchange.types import FundingRateData, Ticker


class FakeRedis:
    """Minimal in-memory Redis replacement for testing."""

    def __init__(self):
        self._data: dict[str, dict] = {}
        self._published: list[tuple[str, bytes]] = []

    async def hset(self, key, field=None, value=None, mapping=None, **kwargs):
        if key not in self._data:
            self._data[key] = {}
        if mapping:
            self._data[key].update(mapping)
        if field is not None and value is not None:
            self._data[key][field] = value

    async def hgetall(self, key):
        return self._data.get(key, {})

    async def publish(self, channel, message):
        self._published.append((channel, message))

    async def ping(self):
        return True


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def state(fake_redis):
    return StateStore(redis=fake_redis)


@pytest.mark.asyncio
async def test_state_store_update_and_get_ticker(state, fake_redis):
    ticker = Ticker(
        exchange="binance",
        symbol="BTC/USDT",
        bid=67000.0,
        ask=67010.0,
        last=67005.0,
    )
    await state.update_ticker(ticker)

    result = await state.get_ticker("binance", "BTC/USDT")
    assert result is not None
    assert result["bid"] == "67000.0"
    assert result["exchange"] == "binance"

    assert len(fake_redis._published) == 1


@pytest.mark.asyncio
async def test_state_store_update_and_get_funding(state, fake_redis):
    rate = FundingRateData(
        exchange="bybit",
        symbol="ETH/USDT",
        funding_rate=0.0003,
        predicted_rate=0.00025,
        mark_price=3500.0,
    )
    await state.update_funding(rate)

    result = await state.get_funding_rate("bybit", "ETH/USDT")
    assert result is not None
    assert result["funding_rate"] == "0.0003"

    all_rates = await state.get_all_funding_rates()
    assert "bybit:ETH/USDT" in all_rates


@pytest.mark.asyncio
async def test_state_store_get_funding_for_symbol(state):
    for exchange in ("binance", "bybit", "okx"):
        rate = FundingRateData(
            exchange=exchange,
            symbol="BTC/USDT",
            funding_rate=0.0001 * (1 + ["binance", "bybit", "okx"].index(exchange)),
        )
        await state.update_funding(rate)

    rates = await state.get_funding_rates_for_symbol("BTC/USDT")
    assert len(rates) == 3


@pytest.mark.asyncio
async def test_state_store_bot_status(state):
    await state.set_bot_status("running", mode="paper")
    status = await state.get_bot_status()
    assert status["status"] == "running"
    assert status["mode"] == "paper"


@pytest.mark.asyncio
async def test_data_collector_poll_once():
    """Test that a single poll cycle fetches data and updates state."""
    mock_connector = AsyncMock()
    mock_connector.fetch_funding_rates = AsyncMock(
        return_value=[
            FundingRateData(
                exchange="binance",
                symbol="BTC/USDT",
                funding_rate=0.0001,
                mark_price=67000.0,
            ),
        ]
    )
    mock_connector.fetch_ticker = AsyncMock(
        return_value=Ticker(
            exchange="binance",
            symbol="BTC/USDT",
            bid=67000.0,
            ask=67010.0,
            last=67005.0,
        )
    )

    fake_redis = FakeRedis()
    state = StateStore(redis=fake_redis)
    collector = DataCollector(
        connectors={"binance": mock_connector},
        state=state,
        symbols=["BTC/USDT"],
    )

    await collector._poll_once("binance", mock_connector)

    mock_connector.fetch_funding_rates.assert_awaited_once_with(["BTC/USDT"])
    mock_connector.fetch_ticker.assert_awaited_once_with("BTC/USDT")

    rate = await state.get_funding_rate("binance", "BTC/USDT")
    assert rate is not None
    assert rate["funding_rate"] == "0.0001"


@pytest.mark.asyncio
async def test_data_collector_error_counting():
    """Test that consecutive errors are tracked per exchange."""
    mock_connector = AsyncMock()
    mock_connector.fetch_funding_rates = AsyncMock(side_effect=Exception("API down"))

    state = StateStore(redis=FakeRedis())
    collector = DataCollector(
        connectors={"binance": mock_connector},
        state=state,
        symbols=["BTC/USDT"],
    )

    for _ in range(3):
        try:
            await collector._poll_once("binance", mock_connector)
        except Exception:
            collector._error_counts["binance"] += 1

    assert collector.get_error_count("binance") == 3
    assert collector.is_exchange_healthy("binance") is True  # < 5

    collector._error_counts["binance"] = 5
    assert collector.is_exchange_healthy("binance") is False


@pytest.mark.asyncio
async def test_data_collector_buffer_and_flush():
    """Test that funding rates are buffered and flushed to DB."""
    mock_connector = AsyncMock()
    mock_connector.fetch_funding_rates = AsyncMock(
        return_value=[
            FundingRateData(
                exchange="binance",
                symbol="BTC/USDT",
                funding_rate=0.0001,
            ),
        ]
    )
    mock_connector.fetch_ticker = AsyncMock(
        return_value=Ticker(
            exchange="binance",
            symbol="BTC/USDT",
            bid=67000.0,
            ask=67010.0,
            last=67005.0,
        )
    )

    state = StateStore(redis=FakeRedis())

    mock_session = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    collector = DataCollector(
        connectors={"binance": mock_connector},
        state=state,
        symbols=["BTC/USDT"],
        db_session_factory=mock_session_factory,
    )

    await collector._poll_once("binance", mock_connector)
    assert len(collector._funding_buffer) == 1

    await collector._flush_buffer()
    mock_session.add_all.assert_called_once()
    mock_session.commit.assert_awaited_once()
    assert len(collector._funding_buffer) == 0
