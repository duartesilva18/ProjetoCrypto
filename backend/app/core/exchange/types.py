"""Shared data transfer objects for exchange data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Ticker:
    exchange: str
    symbol: str
    bid: float
    ask: float
    last: float
    timestamp: datetime = field(default_factory=_utcnow)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread_bps(self) -> float:
        if self.mid == 0:
            return 0.0
        return ((self.ask - self.bid) / self.mid) * 10_000


@dataclass(frozen=True, slots=True)
class FundingRateData:
    exchange: str
    symbol: str
    funding_rate: float
    predicted_rate: float | None = None
    mark_price: float | None = None
    index_price: float | None = None
    next_funding_time: datetime | None = None
    timestamp: datetime = field(default_factory=_utcnow)

    @property
    def time_to_funding_seconds(self) -> float | None:
        if self.next_funding_time is None:
            return None
        delta = (self.next_funding_time - datetime.now(UTC)).total_seconds()
        return max(0.0, delta)


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    price: float
    qty: float


@dataclass(frozen=True, slots=True)
class OrderBook:
    exchange: str
    symbol: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    timestamp: datetime = field(default_factory=_utcnow)

    def bid_depth_at(self, slippage_bps: float = 10.0) -> float:
        """Total bid quantity within `slippage_bps` of best bid."""
        if not self.bids:
            return 0.0
        best = self.bids[0].price
        threshold = best * (1 - slippage_bps / 10_000)
        return sum(lvl.qty for lvl in self.bids if lvl.price >= threshold)

    def ask_depth_at(self, slippage_bps: float = 10.0) -> float:
        """Total ask quantity within `slippage_bps` of best ask."""
        if not self.asks:
            return 0.0
        best = self.asks[0].price
        threshold = best * (1 + slippage_bps / 10_000)
        return sum(lvl.qty for lvl in self.asks if lvl.price <= threshold)


@dataclass(frozen=True, slots=True)
class Balance:
    currency: str
    free: float
    used: float

    @property
    def total(self) -> float:
        return self.free + self.used


@dataclass(frozen=True, slots=True)
class OrderResult:
    order_id: str
    exchange: str
    symbol: str
    side: str
    qty: float
    price: float
    filled_qty: float
    status: str
    fee: float = 0.0
    timestamp: datetime = field(default_factory=_utcnow)

    @property
    def is_filled(self) -> bool:
        return self.status in ("closed", "filled")
