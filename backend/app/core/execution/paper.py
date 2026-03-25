"""Paper trading executor -- simulates order execution with realistic fills.

Uses real market prices from the StateStore and applies a configurable
slippage model. No real orders are placed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

from app.core.data.state import StateStore
from app.core.strategy.signals import Opportunity, Signal, SignalType

logger = structlog.get_logger(__name__)

_DEFAULT_SLIPPAGE_BPS = 2.0
_DEFAULT_FEE_BPS = 10.0


@dataclass
class PaperPosition:
    """A simulated position held by the paper executor."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    exchange: str = ""
    symbol: str = ""
    side: str = "LONG_SPOT_SHORT_PERP"
    strategy: str = "funding_arb"
    spot_qty: float = 0.0
    perp_qty: float = 0.0
    entry_price_spot: float = 0.0
    entry_price_perp: float = 0.0
    funding_collected: float = 0.0
    opened_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    @property
    def notional_value(self) -> float:
        return self.spot_qty * self.entry_price_spot

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "side": self.side,
            "strategy": self.strategy,
            "spot_qty": self.spot_qty,
            "perp_qty": self.perp_qty,
            "entry_price_spot": self.entry_price_spot,
            "entry_price_perp": self.entry_price_perp,
            "funding_collected": self.funding_collected,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
        }


class PaperExecutor:
    """Simulates trade execution using real prices + slippage model."""

    def __init__(
        self,
        state: StateStore,
        slippage_bps: float = _DEFAULT_SLIPPAGE_BPS,
        fee_bps: float = _DEFAULT_FEE_BPS,
    ) -> None:
        self._state = state
        self._slippage_bps = slippage_bps
        self._fee_bps = fee_bps
        self._positions: dict[str, PaperPosition] = {}

    @property
    def open_positions(self) -> list[PaperPosition]:
        return [p for p in self._positions.values() if p.is_open]

    @property
    def all_positions(self) -> list[PaperPosition]:
        return list(self._positions.values())

    def get_open_positions_as_dicts(self) -> list[dict]:
        return [p.to_dict() for p in self.open_positions]

    async def execute_signal(
        self,
        signal: Signal,
        position_size_usd: float | None = None,
    ) -> PaperPosition | None:
        """Execute a signal in paper mode."""
        if signal.type == SignalType.ENTRY and signal.opportunity is not None:
            return await self._execute_entry(
                signal.opportunity,
                size_usd=position_size_usd or 100.0,
            )
        if signal.type == SignalType.EXIT and signal.position_id is not None:
            return await self._execute_exit(signal.position_id)
        return None

    async def _execute_entry(
        self,
        opp: Opportunity,
        size_usd: float = 100.0,
    ) -> PaperPosition | None:
        """Simulate opening a hedged position with dynamic sizing."""
        ticker = await self._state.get_ticker(opp.exchange, opp.symbol)
        if ticker is None:
            logger.warning("paper_entry_no_ticker", exchange=opp.exchange, symbol=opp.symbol)
            return None

        try:
            ask = float(ticker.get("ask", 0))
            bid = float(ticker.get("bid", 0))
        except (TypeError, ValueError):
            return None

        if ask <= 0 or bid <= 0:
            return None

        spot_entry = ask * (1 + self._slippage_bps / 10_000)
        perp_entry = bid * (1 - self._slippage_bps / 10_000)

        qty = round(size_usd / spot_entry, 8) if spot_entry > 0 else 1.0

        side = "LONG_SPOT_SHORT_PERP" if opp.funding_rate > 0 else "SHORT_SPOT_LONG_PERP"

        position = PaperPosition(
            exchange=opp.exchange,
            symbol=opp.symbol,
            side=side,
            spot_qty=qty,
            perp_qty=qty,
            entry_price_spot=spot_entry,
            entry_price_perp=perp_entry,
        )
        self._positions[position.id] = position

        logger.info(
            "paper_position_opened",
            position_id=position.id,
            exchange=opp.exchange,
            symbol=opp.symbol,
            side=side,
            qty=qty,
            size_usd=round(size_usd, 2),
            spot_price=spot_entry,
            perp_price=perp_entry,
        )
        return position

    async def _execute_exit(self, position_id: str) -> PaperPosition | None:
        """Simulate closing a position."""
        pos = self._positions.get(position_id)
        if pos is None or not pos.is_open:
            logger.warning("paper_exit_not_found", position_id=position_id)
            return None

        pos.closed_at = datetime.now(UTC)

        logger.info(
            "paper_position_closed",
            position_id=position_id,
            exchange=pos.exchange,
            symbol=pos.symbol,
            funding_collected=pos.funding_collected,
        )
        return pos

    def apply_funding_payment(self, position_id: str, payment: float) -> None:
        """Record a funding payment to a paper position."""
        pos = self._positions.get(position_id)
        if pos is not None and pos.is_open:
            pos.funding_collected += payment
