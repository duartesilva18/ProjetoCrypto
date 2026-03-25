"""Configurable risk limit parameters."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings


@dataclass(slots=True)
class RiskLimits:
    """All configurable risk thresholds in one place."""

    max_exposure_per_exchange: float = 0.30
    max_exposure_per_pair: float = 0.10
    max_daily_drawdown: float = 0.02
    max_daily_drawdown_hard: float = 0.03
    margin_buffer: float = 0.30
    min_order_book_depth_usd: float = 10_000.0
    max_consecutive_exchange_errors: int = 3
    max_delta_imbalance_pct: float = 0.02
    max_ws_downtime_seconds: float = 60.0

    @classmethod
    def from_settings(cls) -> RiskLimits:
        s = get_settings()
        return cls(
            max_exposure_per_exchange=s.max_exposure_per_exchange,
            max_exposure_per_pair=s.max_exposure_per_pair,
            max_daily_drawdown=s.max_daily_drawdown,
            max_daily_drawdown_hard=s.max_daily_drawdown_hard,
            margin_buffer=s.margin_buffer,
        )
