"""Cash-and-Carry Arbitrage strategy.

Detects premium between spot and perpetual futures prices.
When the futures premium is high enough, opens a hedged position
(buy spot + short perp) to capture the premium as it converges.

The profit comes from the futures premium decaying over time,
not from funding rate payments (though those are a bonus).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

from app.core.data.state import StateStore

logger = structlog.get_logger(__name__)

_MIN_PREMIUM_BPS = 15.0
_EXIT_PREMIUM_BPS = 3.0


@dataclass
class CarryPosition:
    id: str = ""
    exchange: str = ""
    symbol: str = ""
    strategy: str = "carry"
    side: str = "LONG_SPOT_SHORT_PERP"
    spot_qty: float = 0.0
    perp_qty: float = 0.0
    entry_price_spot: float = 0.0
    entry_price_perp: float = 0.0
    entry_premium_bps: float = 0.0
    current_premium_bps: float = 0.0
    premium_profit: float = 0.0
    funding_collected: float = 0.0
    opened_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    @property
    def notional_value(self) -> float:
        return self.spot_qty * self.entry_price_spot

    @property
    def total_profit(self) -> float:
        return self.premium_profit + self.funding_collected

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "side": self.side,
            "spot_qty": self.spot_qty,
            "perp_qty": self.perp_qty,
            "entry_price_spot": self.entry_price_spot,
            "entry_price_perp": self.entry_price_perp,
            "funding_collected": self.total_profit,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "entry_premium_bps": round(self.entry_premium_bps, 2),
            "current_premium_bps": round(self.current_premium_bps, 2),
        }


@dataclass
class CarrySignal:
    action: str  # "entry", "exit", "hold"
    exchange: str = ""
    symbol: str = ""
    premium_bps: float = 0.0
    score: float = 0.0
    reason: str = ""
    position_id: str = ""


class CarryStrategy:
    """Detects cash-and-carry opportunities from spot/futures premium."""

    def __init__(
        self,
        symbols: list[str],
        min_premium_bps: float = _MIN_PREMIUM_BPS,
        exit_premium_bps: float = _EXIT_PREMIUM_BPS,
    ) -> None:
        self._symbols = symbols
        self._min_premium = min_premium_bps
        self._exit_premium = exit_premium_bps

    async def evaluate(
        self,
        state: StateStore,
        open_positions: dict[str, CarryPosition],
    ) -> CarrySignal:
        """Scan for premium opportunities and check exits."""
        entry = await self._scan_entries(state, open_positions)
        if entry is not None:
            return entry

        exit_sig = await self._scan_exits(state, open_positions)
        if exit_sig is not None:
            return exit_sig

        return CarrySignal(action="hold", reason="No carry opportunity")

    async def _scan_entries(
        self,
        state: StateStore,
        open_positions: dict[str, CarryPosition],
    ) -> CarrySignal | None:
        open_keys = {f"{p.exchange}:{p.symbol}" for p in open_positions.values()}
        best: CarrySignal | None = None

        for symbol in self._symbols:
            for exchange in ["binance", "bybit", "okx", "gate"]:
                key = f"{exchange}:{symbol}"
                if key in open_keys:
                    continue

                premium = await self._calculate_premium(state, exchange, symbol)
                if premium is None or premium < self._min_premium:
                    continue

                score = min(1.0, premium / (self._min_premium * 3))

                if best is None or premium > best.premium_bps:
                    best = CarrySignal(
                        action="entry",
                        exchange=exchange,
                        symbol=symbol,
                        premium_bps=premium,
                        score=score,
                        reason=f"Premium {premium:.1f}bps on {exchange}:{symbol}",
                    )

        if best:
            logger.info(
                "carry_opportunity",
                exchange=best.exchange,
                symbol=best.symbol,
                premium_bps=round(best.premium_bps, 2),
                score=round(best.score, 3),
            )
        return best

    async def _scan_exits(
        self,
        state: StateStore,
        open_positions: dict[str, CarryPosition],
    ) -> CarrySignal | None:
        for pos_id, pos in open_positions.items():
            premium = await self._calculate_premium(state, pos.exchange, pos.symbol)
            if premium is None:
                continue

            pos.current_premium_bps = premium

            if premium <= self._exit_premium:
                profit_bps = pos.entry_premium_bps - premium
                pos.premium_profit = pos.notional_value * profit_bps / 10_000
                logger.info(
                    "carry_exit_signal",
                    exchange=pos.exchange,
                    symbol=pos.symbol,
                    entry_premium=pos.entry_premium_bps,
                    current_premium=premium,
                    profit_bps=round(profit_bps, 2),
                )
                return CarrySignal(
                    action="exit",
                    exchange=pos.exchange,
                    symbol=pos.symbol,
                    premium_bps=premium,
                    position_id=pos_id,
                    reason=f"Premium converged to {premium:.1f}bps"
                    f" (entry: {pos.entry_premium_bps:.1f}bps)",
                )
        return None

    async def _calculate_premium(
        self, state: StateStore, exchange: str, symbol: str
    ) -> float | None:
        """Calculate futures premium in basis points.

        Premium = (perp_price - spot_price) / spot_price * 10000
        """
        ticker = await state.get_ticker(exchange, symbol)
        funding_data = await state.get_funding_rate(exchange, symbol)

        if not ticker:
            return None

        try:
            spot_mid = (float(ticker.get("bid", 0)) + float(ticker.get("ask", 0))) / 2
        except (TypeError, ValueError):
            return None

        if spot_mid <= 0:
            return None

        mark = None
        if funding_data:
            with contextlib.suppress(TypeError, ValueError):
                mark = float(funding_data.get("mark_price", 0))

        if not mark or mark <= 0:
            return None

        premium_bps = (mark - spot_mid) / spot_mid * 10_000
        return abs(premium_bps)
