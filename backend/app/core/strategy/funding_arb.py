"""Core funding rate arbitrage strategy.

Scans all exchanges/symbols for attractive funding rates,
scores opportunities, validates risk, and emits entry/exit signals.
"""

from __future__ import annotations

import structlog

from app.core.data.state import StateStore
from app.core.risk.manager import RiskManager
from app.core.strategy.scoring import score_opportunity
from app.core.strategy.signals import Opportunity, Signal

logger = structlog.get_logger(__name__)


class FundingArbStrategy:
    """Evaluates funding rate opportunities across exchanges."""

    def __init__(
        self,
        symbols: list[str],
        entry_threshold: float = 0.0001,
        exit_threshold: float = 0.00005,
        min_score: float = 0.5,
        position_size_pct: float = 0.05,
    ) -> None:
        self._symbols = symbols
        self._entry_threshold = entry_threshold
        self._exit_threshold = exit_threshold
        self._min_score = min_score
        self._position_size_pct = position_size_pct

    async def evaluate(
        self,
        state: StateStore,
        risk_manager: RiskManager,
        open_positions: list[dict],
    ) -> Signal:
        """Run one evaluation cycle.

        1. Scan funding rates for entry opportunities
        2. Score and rank them
        3. Validate top candidate against risk
        4. Check existing positions for exit
        5. Return the best signal (or HOLD)
        """
        if risk_manager.circuit_breaker.is_tripped:
            return Signal.hold(reason="Circuit breaker is OPEN")

        entry_signal = await self._scan_entries(state, risk_manager)
        if entry_signal is not None:
            return entry_signal

        exit_signal = await self._scan_exits(state, open_positions)
        if exit_signal is not None:
            return exit_signal

        return Signal.hold()

    async def _scan_entries(self, state: StateStore, risk_manager: RiskManager) -> Signal | None:
        """Scan all symbols on all exchanges for entry opportunities."""
        opportunities: list[Opportunity] = []

        for symbol in self._symbols:
            rates = await state.get_funding_rates_for_symbol(symbol)

            for key, data in rates.items():
                try:
                    rate = float(data.get("funding_rate", 0))
                except (TypeError, ValueError):
                    continue

                if abs(rate) < self._entry_threshold:
                    continue

                predicted = _safe_float(data.get("predicted_rate"))
                ttf = _safe_float(data.get("time_to_funding_s"))
                spread = _safe_float(data.get("spread_bps")) or 0.0
                exchange = data.get("exchange", key.split(":")[0])

                opp_score = score_opportunity(
                    funding_rate=rate,
                    predicted_rate=predicted,
                    time_to_funding_seconds=ttf,
                    spread_bps=spread,
                )

                if opp_score >= self._min_score:
                    opportunities.append(
                        Opportunity(
                            exchange=exchange,
                            symbol=symbol,
                            funding_rate=rate,
                            predicted_rate=predicted,
                            time_to_funding_seconds=ttf,
                            spread_bps=spread,
                            score=opp_score,
                        )
                    )

        if not opportunities:
            return None

        ranked = sorted(opportunities, key=lambda o: o.score, reverse=True)

        portfolio = risk_manager._portfolio
        position_size = portfolio.total_capital * self._position_size_pct

        for opp in ranked:
            if risk_manager.is_valid(opp, position_size):
                logger.info(
                    "entry_signal",
                    exchange=opp.exchange,
                    symbol=opp.symbol,
                    score=opp.score,
                    rate=opp.funding_rate,
                )
                return Signal.entry(opp)

        return None

    async def _scan_exits(self, state: StateStore, open_positions: list[dict]) -> Signal | None:
        """Check if any open position should be closed."""
        for pos in open_positions:
            exchange = pos.get("exchange", "")
            symbol = pos.get("symbol", "")
            position_id = pos.get("id", "")

            rate_data = await state.get_funding_rate(exchange, symbol)
            if rate_data is None:
                continue

            try:
                current_rate = float(rate_data.get("funding_rate", 0))
            except (TypeError, ValueError):
                continue

            if abs(current_rate) < self._exit_threshold:
                logger.info(
                    "exit_signal",
                    exchange=exchange,
                    symbol=symbol,
                    rate=current_rate,
                    threshold=self._exit_threshold,
                    position_id=position_id,
                )
                return Signal.exit(
                    position_id=position_id,
                    reason=f"Rate {current_rate:.6f} below threshold {self._exit_threshold:.6f}",
                )

        return None


def _safe_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
