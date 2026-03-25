"""Signal dataclasses emitted by the strategy engine."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


class SignalType(enum.StrEnum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    HOLD = "HOLD"


@dataclass(frozen=True, slots=True)
class Opportunity:
    """A scored funding rate arbitrage opportunity."""

    exchange: str
    symbol: str
    funding_rate: float
    predicted_rate: float | None
    time_to_funding_seconds: float | None
    spread_bps: float
    score: float


@dataclass(frozen=True, slots=True)
class Signal:
    """Trading signal emitted by the strategy engine."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: SignalType = SignalType.HOLD
    opportunity: Opportunity | None = None
    position_id: str | None = None
    reason: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def entry(cls, opportunity: Opportunity, reason: str = "") -> Signal:
        return cls(
            type=SignalType.ENTRY,
            opportunity=opportunity,
            reason=reason
            or (f"Score {opportunity.score:.3f} on {opportunity.exchange}:{opportunity.symbol}"),
        )

    @classmethod
    def exit(cls, position_id: str, reason: str = "") -> Signal:
        return cls(
            type=SignalType.EXIT,
            position_id=position_id,
            reason=reason or "Below exit threshold",
        )

    @classmethod
    def hold(cls, reason: str = "") -> Signal:
        return cls(type=SignalType.HOLD, reason=reason or "No actionable opportunity")
