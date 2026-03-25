"""Tests for FundingArbStrategy and PaperExecutor."""

from __future__ import annotations

import pytest

from app.core.data.state import StateStore
from app.core.exchange.types import FundingRateData, Ticker
from app.core.execution.paper import PaperExecutor
from app.core.risk.manager import PortfolioSnapshot, RiskManager
from app.core.strategy.funding_arb import FundingArbStrategy
from app.core.strategy.signals import SignalType


class FakeRedis:
    def __init__(self):
        self._data: dict[str, dict] = {}

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
        pass

    async def ping(self):
        return True


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def state(fake_redis):
    return StateStore(redis=fake_redis)


@pytest.fixture
def risk_manager():
    rm = RiskManager()
    rm.update_portfolio(PortfolioSnapshot(total_capital=50_000))
    return rm


@pytest.fixture
def strategy():
    return FundingArbStrategy(
        symbols=["BTC/USDT", "ETH/USDT"],
        entry_threshold=0.0001,
        exit_threshold=0.00005,
        min_score=0.3,
    )


# ── Strategy Tests ────────────────────────────


@pytest.mark.asyncio
async def test_strategy_hold_when_no_data(strategy, state, risk_manager):
    signal = await strategy.evaluate(state, risk_manager, [])
    assert signal.type == SignalType.HOLD


@pytest.mark.asyncio
async def test_strategy_hold_when_rate_below_threshold(strategy, state, risk_manager):
    rate = FundingRateData(
        exchange="binance",
        symbol="BTC/USDT",
        funding_rate=0.00005,
    )
    await state.update_funding(rate)

    signal = await strategy.evaluate(state, risk_manager, [])
    assert signal.type == SignalType.HOLD


@pytest.mark.asyncio
async def test_strategy_entry_signal_on_high_rate(strategy, state, risk_manager):
    rate = FundingRateData(
        exchange="binance",
        symbol="BTC/USDT",
        funding_rate=0.0005,
        predicted_rate=0.0004,
    )
    await state.update_funding(rate)

    signal = await strategy.evaluate(state, risk_manager, [])
    assert signal.type == SignalType.ENTRY
    assert signal.opportunity is not None
    assert signal.opportunity.exchange == "binance"
    assert signal.opportunity.symbol == "BTC/USDT"


@pytest.mark.asyncio
async def test_strategy_exit_signal_when_rate_drops(strategy, state, risk_manager):
    rate = FundingRateData(
        exchange="binance",
        symbol="BTC/USDT",
        funding_rate=0.00002,
    )
    await state.update_funding(rate)

    open_positions = [
        {"id": "pos-123", "exchange": "binance", "symbol": "BTC/USDT"},
    ]

    signal = await strategy.evaluate(state, risk_manager, open_positions)
    assert signal.type == SignalType.EXIT
    assert signal.position_id == "pos-123"


@pytest.mark.asyncio
async def test_strategy_hold_when_circuit_breaker_tripped(strategy, state, risk_manager):
    rate = FundingRateData(
        exchange="binance",
        symbol="BTC/USDT",
        funding_rate=0.001,
    )
    await state.update_funding(rate)

    risk_manager.circuit_breaker.manual_trip()
    signal = await strategy.evaluate(state, risk_manager, [])
    assert signal.type == SignalType.HOLD
    assert "Circuit breaker" in signal.reason


@pytest.mark.asyncio
async def test_strategy_picks_best_score():
    """When multiple opportunities exist, the highest score wins."""
    fake_redis = FakeRedis()
    s = StateStore(redis=fake_redis)

    for exchange, rate_val in [("binance", 0.0003), ("bybit", 0.0008)]:
        rate = FundingRateData(
            exchange=exchange,
            symbol="BTC/USDT",
            funding_rate=rate_val,
            predicted_rate=rate_val * 0.9,
        )
        await s.update_funding(rate)

    rm = RiskManager()
    rm.update_portfolio(PortfolioSnapshot(total_capital=50_000))

    strat = FundingArbStrategy(
        symbols=["BTC/USDT"],
        entry_threshold=0.0001,
        min_score=0.3,
    )

    signal = await strat.evaluate(s, rm, [])
    assert signal.type == SignalType.ENTRY
    assert signal.opportunity.exchange == "bybit"


# ── PaperExecutor Tests ──────────────────────


@pytest.mark.asyncio
async def test_paper_executor_entry(state):
    ticker = Ticker(
        exchange="binance",
        symbol="BTC/USDT",
        bid=67000.0,
        ask=67010.0,
        last=67005.0,
    )
    await state.update_ticker(ticker)

    executor = PaperExecutor(state=state)

    from app.core.strategy.signals import Opportunity, Signal

    opp = Opportunity(
        exchange="binance",
        symbol="BTC/USDT",
        funding_rate=0.0005,
        predicted_rate=0.0004,
        time_to_funding_seconds=7200,
        spread_bps=2.0,
        score=0.8,
    )
    signal = Signal.entry(opp)
    pos = await executor.execute_signal(signal)

    assert pos is not None
    assert pos.exchange == "binance"
    assert pos.symbol == "BTC/USDT"
    assert pos.is_open is True
    assert pos.spot_qty > 0
    assert len(executor.open_positions) == 1


@pytest.mark.asyncio
async def test_paper_executor_exit(state):
    ticker = Ticker(
        exchange="binance",
        symbol="BTC/USDT",
        bid=67000.0,
        ask=67010.0,
        last=67005.0,
    )
    await state.update_ticker(ticker)

    executor = PaperExecutor(state=state)

    from app.core.strategy.signals import Opportunity, Signal

    opp = Opportunity(
        exchange="binance",
        symbol="BTC/USDT",
        funding_rate=0.0005,
        predicted_rate=None,
        time_to_funding_seconds=None,
        spread_bps=2.0,
        score=0.7,
    )
    pos = await executor.execute_signal(Signal.entry(opp))
    assert pos is not None
    assert len(executor.open_positions) == 1

    exit_signal = Signal.exit(pos.id)
    closed = await executor.execute_signal(exit_signal)
    assert closed is not None
    assert closed.is_open is False
    assert len(executor.open_positions) == 0


@pytest.mark.asyncio
async def test_paper_executor_funding_payment(state):
    ticker = Ticker(
        exchange="binance",
        symbol="BTC/USDT",
        bid=67000.0,
        ask=67010.0,
        last=67005.0,
    )
    await state.update_ticker(ticker)

    executor = PaperExecutor(state=state)

    from app.core.strategy.signals import Opportunity, Signal

    opp = Opportunity(
        exchange="binance",
        symbol="BTC/USDT",
        funding_rate=0.0005,
        predicted_rate=None,
        time_to_funding_seconds=None,
        spread_bps=2.0,
        score=0.7,
    )
    pos = await executor.execute_signal(Signal.entry(opp))

    executor.apply_funding_payment(pos.id, 1.50)
    executor.apply_funding_payment(pos.id, 1.25)

    assert pos.funding_collected == 2.75


@pytest.mark.asyncio
async def test_paper_executor_no_ticker_returns_none(state):
    executor = PaperExecutor(state=state)

    from app.core.strategy.signals import Opportunity, Signal

    opp = Opportunity(
        exchange="binance",
        symbol="MISSING/USDT",
        funding_rate=0.0005,
        predicted_rate=None,
        time_to_funding_seconds=None,
        spread_bps=2.0,
        score=0.7,
    )
    pos = await executor.execute_signal(Signal.entry(opp))
    assert pos is None
