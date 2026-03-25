"""Circuit breaker: emergency stop mechanism.

Triggers automatic trading halt when critical thresholds are breached.
Once tripped, the circuit breaker stays open until manually reset.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

from app.core.risk.limits import RiskLimits

logger = structlog.get_logger(__name__)


class BreakerState(enum.StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"


@dataclass
class TripEvent:
    reason: str
    trigger: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class CircuitBreaker:
    """Monitors critical conditions and halts trading when breached."""

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self._limits = limits or RiskLimits()
        self._state = BreakerState.CLOSED
        self._trip_events: list[TripEvent] = []
        self._daily_pnl: float = 0.0
        self._start_equity: float = 0.0

    @property
    def state(self) -> BreakerState:
        return self._state

    @property
    def is_tripped(self) -> bool:
        return self._state == BreakerState.OPEN

    @property
    def trip_events(self) -> list[TripEvent]:
        return list(self._trip_events)

    def set_start_equity(self, equity: float) -> None:
        self._start_equity = equity

    def update_pnl(self, current_equity: float) -> None:
        """Update daily P&L and check drawdown limits."""
        if self._start_equity <= 0:
            return

        self._daily_pnl = (current_equity - self._start_equity) / self._start_equity

        if self._daily_pnl <= -self._limits.max_daily_drawdown_hard:
            self._trip(
                reason=f"Hard drawdown limit breached: {self._daily_pnl:.4%}",
                trigger="drawdown_hard",
            )

    def check_drawdown_warning(self) -> bool:
        """Returns True if soft drawdown limit is breached (warning, not trip)."""
        return self._daily_pnl <= -self._limits.max_daily_drawdown

    def check_exchange_errors(self, exchange: str, consecutive_errors: int) -> None:
        if consecutive_errors >= self._limits.max_consecutive_exchange_errors:
            self._trip(
                reason=f"{exchange}: {consecutive_errors} consecutive API errors",
                trigger="exchange_errors",
            )

    def check_delta_imbalance(
        self, spot_value: float, perp_value: float, position_value: float
    ) -> None:
        if position_value <= 0:
            return
        imbalance = abs(spot_value - perp_value) / position_value
        if imbalance > self._limits.max_delta_imbalance_pct:
            limit = self._limits.max_delta_imbalance_pct
            self._trip(
                reason=f"Delta imbalance {imbalance:.4%} exceeds {limit:.4%}",
                trigger="delta_imbalance",
            )

    def check_ws_downtime(self, exchange: str, downtime_seconds: float) -> None:
        if downtime_seconds > self._limits.max_ws_downtime_seconds:
            self._trip(
                reason=f"{exchange}: WS down for {downtime_seconds:.0f}s",
                trigger="ws_downtime",
            )

    def manual_trip(self, reason: str = "Manual trigger") -> None:
        self._trip(reason=reason, trigger="manual")

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        if self._state == BreakerState.OPEN:
            logger.warning(
                "circuit_breaker_reset",
                previous_events=len(self._trip_events),
            )
        self._state = BreakerState.CLOSED
        self._trip_events.clear()
        self._daily_pnl = 0.0

    def _trip(self, reason: str, trigger: str) -> None:
        if self._state == BreakerState.OPEN:
            return

        self._state = BreakerState.OPEN
        event = TripEvent(reason=reason, trigger=trigger)
        self._trip_events.append(event)
        logger.critical(
            "circuit_breaker_tripped",
            reason=reason,
            trigger=trigger,
        )
