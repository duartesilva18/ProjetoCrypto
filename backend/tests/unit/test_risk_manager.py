"""Tests for RiskManager and CircuitBreaker."""

from __future__ import annotations

from app.core.risk.circuit_breaker import BreakerState, CircuitBreaker
from app.core.risk.limits import RiskLimits
from app.core.risk.manager import PortfolioSnapshot, RiskManager
from app.core.strategy.signals import Opportunity


def _make_opportunity(
    exchange: str = "binance",
    symbol: str = "BTC/USDT",
    rate: float = 0.0003,
    score: float = 0.7,
    spread_bps: float = 3.0,
) -> Opportunity:
    return Opportunity(
        exchange=exchange,
        symbol=symbol,
        funding_rate=rate,
        predicted_rate=rate * 0.8,
        time_to_funding_seconds=7200,
        spread_bps=spread_bps,
        score=score,
    )


def _make_manager(
    capital: float = 50_000,
    exchange_exposure: dict | None = None,
    pair_exposure: dict | None = None,
) -> RiskManager:
    rm = RiskManager(limits=RiskLimits())
    rm.update_portfolio(
        PortfolioSnapshot(
            total_capital=capital,
            exposure_by_exchange=exchange_exposure or {},
            exposure_by_pair=pair_exposure or {},
        )
    )
    return rm


# ── RiskManager Tests ─────────────────────────


def test_valid_opportunity_passes():
    rm = _make_manager(capital=50_000)
    opp = _make_opportunity()
    assert rm.is_valid(opp, position_size_usd=2_500) is True


def test_exchange_exposure_limit():
    rm = _make_manager(
        capital=50_000,
        exchange_exposure={"binance": 14_000},
    )
    opp = _make_opportunity(exchange="binance")
    assert rm.is_valid(opp, position_size_usd=3_000) is False


def test_pair_exposure_limit():
    rm = _make_manager(
        capital=50_000,
        pair_exposure={"BTC/USDT": 4_500},
    )
    opp = _make_opportunity(symbol="BTC/USDT")
    assert rm.is_valid(opp, position_size_usd=1_500) is False


def test_no_capital_fails():
    rm = _make_manager(capital=0)
    opp = _make_opportunity()
    assert rm.is_valid(opp, position_size_usd=100) is False


def test_excessive_spread_fails():
    rm = _make_manager(capital=50_000)
    opp = _make_opportunity(spread_bps=60.0)
    assert rm.is_valid(opp, position_size_usd=2_500) is False


def test_multiple_exchanges_independent():
    rm = _make_manager(
        capital=50_000,
        exchange_exposure={"binance": 14_000},
    )
    binance_opp = _make_opportunity(exchange="binance")
    bybit_opp = _make_opportunity(exchange="bybit")

    assert rm.is_valid(binance_opp, position_size_usd=3_000) is False
    assert rm.is_valid(bybit_opp, position_size_usd=3_000) is True


def test_validate_returns_all_checks():
    rm = _make_manager(capital=50_000)
    opp = _make_opportunity()
    results = rm.validate(opp, position_size_usd=2_500)
    assert len(results) == 5
    assert all(r.passed for r in results)


# ── CircuitBreaker Tests ──────────────────────


def test_circuit_breaker_starts_closed():
    cb = CircuitBreaker()
    assert cb.state == BreakerState.CLOSED
    assert cb.is_tripped is False


def test_hard_drawdown_trips_breaker():
    cb = CircuitBreaker(limits=RiskLimits(max_daily_drawdown_hard=0.03))
    cb.set_start_equity(100_000)
    cb.update_pnl(96_900)
    assert cb.is_tripped is True


def test_soft_drawdown_does_not_trip():
    cb = CircuitBreaker(limits=RiskLimits(max_daily_drawdown=0.02, max_daily_drawdown_hard=0.03))
    cb.set_start_equity(100_000)
    cb.update_pnl(97_500)
    assert cb.is_tripped is False
    assert cb.check_drawdown_warning() is True


def test_exchange_errors_trip():
    cb = CircuitBreaker(limits=RiskLimits(max_consecutive_exchange_errors=3))
    cb.check_exchange_errors("binance", 2)
    assert cb.is_tripped is False
    cb.check_exchange_errors("binance", 3)
    assert cb.is_tripped is True


def test_delta_imbalance_trip():
    cb = CircuitBreaker(limits=RiskLimits(max_delta_imbalance_pct=0.02))
    cb.check_delta_imbalance(spot_value=10_000, perp_value=9_700, position_value=10_000)
    assert cb.is_tripped is True


def test_ws_downtime_trip():
    cb = CircuitBreaker(limits=RiskLimits(max_ws_downtime_seconds=60))
    cb.check_ws_downtime("binance", 61)
    assert cb.is_tripped is True
    assert len(cb.trip_events) == 1
    assert cb.trip_events[0].trigger == "ws_downtime"


def test_manual_trip():
    cb = CircuitBreaker()
    cb.manual_trip("Testing")
    assert cb.is_tripped is True
    assert cb.trip_events[0].trigger == "manual"


def test_reset_clears_breaker():
    cb = CircuitBreaker()
    cb.manual_trip()
    assert cb.is_tripped is True
    cb.reset()
    assert cb.is_tripped is False
    assert len(cb.trip_events) == 0


def test_tripped_breaker_blocks_risk():
    rm = _make_manager(capital=50_000)
    rm.circuit_breaker.manual_trip()
    opp = _make_opportunity()
    assert rm.is_valid(opp, position_size_usd=2_500) is False


def test_double_trip_no_duplicate():
    cb = CircuitBreaker()
    cb.manual_trip("First")
    cb.manual_trip("Second")
    assert len(cb.trip_events) == 1
