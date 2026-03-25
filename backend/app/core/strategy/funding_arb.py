"""Core funding rate arbitrage strategy.

Scans all exchanges/symbols for attractive funding rates,
scores opportunities, validates risk, and emits entry/exit signals.

Multi-exchange comparison: for each symbol, picks the exchange with
the best funding rate rather than evaluating each independently.

Dynamic position sizing: scales position size based on opportunity
score and available capital instead of using a fixed $100 notional.
"""

from __future__ import annotations

from collections import defaultdict

import structlog

from app.core.data.state import StateStore
from app.core.risk.manager import RiskManager
from app.core.strategy.scoring import score_opportunity
from app.core.strategy.signals import Opportunity, Signal

logger = structlog.get_logger(__name__)

_BASE_POSITION_SIZE_USD = 200.0
_MAX_CAPITAL_FRACTION = 0.10


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
        2. Score and rank them (best exchange per symbol)
        3. Validate top candidate against risk
        4. Check existing positions for exit
        5. Return the best signal (or HOLD)
        """
        if risk_manager.circuit_breaker.is_tripped:
            return Signal.hold(reason="Circuit breaker is OPEN")

        open_keys = {f"{p.get('exchange')}:{p.get('symbol')}" for p in open_positions}

        entry_signal = await self._scan_entries(state, risk_manager, open_keys)
        if entry_signal is not None:
            return entry_signal

        exit_signal = await self._scan_exits(state, open_positions)
        if exit_signal is not None:
            return exit_signal

        return Signal.hold()

    async def _scan_entries(
        self,
        state: StateStore,
        risk_manager: RiskManager,
        open_keys: set[str] | None = None,
    ) -> Signal | None:
        """Scan all symbols across exchanges, pick best exchange per symbol."""
        open_keys = open_keys or set()
        candidates_by_symbol: defaultdict[str, list[Opportunity]] = defaultdict(list)

        for symbol in self._symbols:
            rates = await state.get_funding_rates_for_symbol(symbol)

            for key, data in rates.items():
                exchange = data.get("exchange", key.split(":")[0])
                if f"{exchange}:{symbol}" in open_keys:
                    continue

                try:
                    rate = float(data.get("funding_rate", 0))
                except (TypeError, ValueError):
                    continue

                if abs(rate) < self._entry_threshold:
                    continue

                predicted = _safe_float(data.get("predicted_rate"))
                ttf = _safe_float(data.get("time_to_funding_s"))
                spread = _safe_float(data.get("spread_bps")) or 0.0

                opp_score = score_opportunity(
                    funding_rate=rate,
                    predicted_rate=predicted,
                    time_to_funding_seconds=ttf,
                    spread_bps=spread,
                )

                if opp_score >= self._min_score:
                    candidates_by_symbol[symbol].append(
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

        best_per_symbol: list[Opportunity] = []
        for symbol, candidates in candidates_by_symbol.items():
            best = max(candidates, key=lambda o: (abs(o.funding_rate), o.score))
            best_per_symbol.append(best)
            if len(candidates) > 1:
                others = [f"{c.exchange}={c.funding_rate:.6f}" for c in candidates if c is not best]
                logger.debug(
                    "multi_exchange_comparison",
                    symbol=symbol,
                    chosen=best.exchange,
                    chosen_rate=best.funding_rate,
                    alternatives=others,
                )

        if not best_per_symbol:
            return None

        ranked = sorted(best_per_symbol, key=lambda o: o.score, reverse=True)

        portfolio = risk_manager._portfolio
        capital = portfolio.total_capital

        for opp in ranked:
            position_size = self._dynamic_size(opp.score, capital)
            if risk_manager.is_valid(opp, position_size):
                logger.info(
                    "entry_signal",
                    exchange=opp.exchange,
                    symbol=opp.symbol,
                    score=opp.score,
                    rate=opp.funding_rate,
                    position_size_usd=round(position_size, 2),
                )
                return Signal.entry(opp)

        return None

    @staticmethod
    def _dynamic_size(score: float, capital: float) -> float:
        """Scale position size by opportunity score and available capital."""
        score_multiplier = max(0.5, min(2.0, score / 0.5))
        capital_alloc = capital * _MAX_CAPITAL_FRACTION
        return min(capital_alloc, _BASE_POSITION_SIZE_USD * score_multiplier)

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
