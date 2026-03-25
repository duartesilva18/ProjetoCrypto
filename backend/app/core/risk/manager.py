"""Pre-trade risk validation.

Every signal must pass all risk checks before the execution engine acts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from app.core.risk.circuit_breaker import CircuitBreaker
from app.core.risk.limits import RiskLimits
from app.core.strategy.signals import Opportunity

logger = structlog.get_logger(__name__)


@dataclass
class PortfolioSnapshot:
    """Current state of the portfolio for risk evaluation."""

    total_capital: float = 0.0
    exposure_by_exchange: dict[str, float] = field(default_factory=dict)
    exposure_by_pair: dict[str, float] = field(default_factory=dict)
    open_position_count: int = 0


@dataclass
class RiskCheckResult:
    """Result of a single risk check."""

    passed: bool
    check_name: str
    reason: str = ""


class RiskManager:
    """Validates that a trade opportunity passes all risk constraints."""

    def __init__(
        self,
        limits: RiskLimits | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._limits = limits or RiskLimits()
        self._circuit_breaker = circuit_breaker or CircuitBreaker(self._limits)
        self._portfolio = PortfolioSnapshot()

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._circuit_breaker

    @property
    def limits(self) -> RiskLimits:
        return self._limits

    def update_portfolio(self, snapshot: PortfolioSnapshot) -> None:
        self._portfolio = snapshot

    def validate(self, opportunity: Opportunity, position_size_usd: float) -> list[RiskCheckResult]:
        """Run all pre-trade checks. Returns list of results (all must pass)."""
        checks = [
            self._check_circuit_breaker(),
            self._check_drawdown_warning(),
            self._check_exchange_exposure(opportunity.exchange, position_size_usd),
            self._check_pair_exposure(opportunity.symbol, position_size_usd),
            self._check_spread(opportunity.spread_bps),
        ]
        return checks

    def is_valid(self, opportunity: Opportunity, position_size_usd: float) -> bool:
        """Convenience: returns True only if ALL checks pass."""
        results = self.validate(opportunity, position_size_usd)
        for r in results:
            if not r.passed:
                logger.info(
                    "risk_check_failed",
                    check=r.check_name,
                    reason=r.reason,
                    exchange=opportunity.exchange,
                    symbol=opportunity.symbol,
                )
                return False
        return True

    def _check_circuit_breaker(self) -> RiskCheckResult:
        if self._circuit_breaker.is_tripped:
            return RiskCheckResult(
                passed=False,
                check_name="circuit_breaker",
                reason="Circuit breaker is OPEN",
            )
        return RiskCheckResult(passed=True, check_name="circuit_breaker")

    def _check_drawdown_warning(self) -> RiskCheckResult:
        if self._circuit_breaker.check_drawdown_warning():
            return RiskCheckResult(
                passed=False,
                check_name="drawdown_soft",
                reason="Soft daily drawdown limit breached -- no new positions",
            )
        return RiskCheckResult(passed=True, check_name="drawdown_soft")

    def _check_exchange_exposure(self, exchange: str, position_size_usd: float) -> RiskCheckResult:
        capital = self._portfolio.total_capital
        if capital <= 0:
            return RiskCheckResult(
                passed=False,
                check_name="exchange_exposure",
                reason="No capital available",
            )

        current = self._portfolio.exposure_by_exchange.get(exchange, 0.0)
        new_exposure = (current + position_size_usd) / capital

        if new_exposure > self._limits.max_exposure_per_exchange:
            return RiskCheckResult(
                passed=False,
                check_name="exchange_exposure",
                reason=(
                    f"{exchange} exposure {new_exposure:.1%}"
                    f" > limit {self._limits.max_exposure_per_exchange:.1%}"
                ),
            )
        return RiskCheckResult(passed=True, check_name="exchange_exposure")

    def _check_pair_exposure(self, symbol: str, position_size_usd: float) -> RiskCheckResult:
        capital = self._portfolio.total_capital
        if capital <= 0:
            return RiskCheckResult(
                passed=False,
                check_name="pair_exposure",
                reason="No capital available",
            )

        current = self._portfolio.exposure_by_pair.get(symbol, 0.0)
        new_exposure = (current + position_size_usd) / capital

        if new_exposure > self._limits.max_exposure_per_pair:
            return RiskCheckResult(
                passed=False,
                check_name="pair_exposure",
                reason=(
                    f"{symbol} exposure {new_exposure:.1%}"
                    f" > limit {self._limits.max_exposure_per_pair:.1%}"
                ),
            )
        return RiskCheckResult(passed=True, check_name="pair_exposure")

    def _check_spread(self, spread_bps: float) -> RiskCheckResult:
        max_spread = 50.0
        if spread_bps > max_spread:
            return RiskCheckResult(
                passed=False,
                check_name="spread",
                reason=f"Spread {spread_bps:.1f} bps exceeds maximum {max_spread:.0f} bps",
            )
        return RiskCheckResult(passed=True, check_name="spread")
