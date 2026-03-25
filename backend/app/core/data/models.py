from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ── Enums ────────────────────────────────────────


class PositionSide(enum.StrEnum):
    LONG_SPOT_SHORT_PERP = "LONG_SPOT_SHORT_PERP"
    SHORT_SPOT_LONG_PERP = "SHORT_SPOT_LONG_PERP"


class PositionStatus(enum.StrEnum):
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class TradeSide(enum.StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class TradeMarket(enum.StrEnum):
    SPOT = "SPOT"
    PERP = "PERP"


class EventLevel(enum.StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# ── TimescaleDB Hypertables ─────────────────────


class FundingRate(Base):
    """Funding rate snapshots -- TimescaleDB hypertable on `timestamp`."""

    __tablename__ = "funding_rates"

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(20), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30), primary_key=True)
    funding_rate: Mapped[float] = mapped_column(Numeric(18, 10), nullable=False)
    predicted_rate: Mapped[float | None] = mapped_column(Numeric(18, 10))
    mark_price: Mapped[float | None] = mapped_column(Numeric(18, 8))
    index_price: Mapped[float | None] = mapped_column(Numeric(18, 8))

    __table_args__ = (Index("ix_funding_rates_exchange_symbol", "exchange", "symbol"),)


class Trade(Base):
    """Executed trades -- TimescaleDB hypertable on `timestamp`."""

    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    position_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    side: Mapped[TradeSide] = mapped_column(Enum(TradeSide), nullable=False)
    market: Mapped[TradeMarket] = mapped_column(Enum(TradeMarket), nullable=False)
    qty: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    fee: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    order_id: Mapped[str | None] = mapped_column(String(100))
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("ix_trades_position_id", "position_id"),
        Index("ix_trades_timestamp", "timestamp"),
    )


class FundingPayment(Base):
    """Collected funding payments -- TimescaleDB hypertable on `timestamp`."""

    __tablename__ = "funding_payments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    position_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    payment: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    rate: Mapped[float] = mapped_column(Numeric(18, 10), nullable=False)

    __table_args__ = (Index("ix_funding_payments_position_id", "position_id"),)


class EquitySnapshot(Base):
    """Periodic equity snapshots -- TimescaleDB hypertable on `timestamp`."""

    __tablename__ = "equity_snapshots"

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    total_equity: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    realized_pnl: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    funding_pnl: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    positions_count: Mapped[int] = mapped_column(Integer, default=0)


class BotEvent(Base):
    """Structured bot events/logs -- TimescaleDB hypertable on `timestamp`."""

    __tablename__ = "bot_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    level: Mapped[EventLevel] = mapped_column(Enum(EventLevel), nullable=False)
    component: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    __table_args__ = (
        Index("ix_bot_events_level", "level"),
        Index("ix_bot_events_component", "component"),
        Index("ix_bot_events_timestamp", "timestamp"),
    )


# ── Regular Tables ───────────────────────────────


class Position(Base):
    """Arbitrage positions -- regular table with lifecycle tracking."""

    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    side: Mapped[PositionSide] = mapped_column(Enum(PositionSide), nullable=False)
    spot_qty: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    perp_qty: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    entry_price_spot: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    entry_price_perp: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    status: Mapped[PositionStatus] = mapped_column(
        Enum(PositionStatus), default=PositionStatus.OPEN
    )
    funding_collected: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("ix_positions_status", "status"),
        Index("ix_positions_exchange_symbol", "exchange", "symbol"),
    )


HYPERTABLE_CONFIGS: list[dict[str, str]] = [
    {"table": "funding_rates", "time_column": "timestamp"},
    {"table": "trades", "time_column": "timestamp"},
    {"table": "funding_payments", "time_column": "timestamp"},
    {"table": "equity_snapshots", "time_column": "timestamp"},
    {"table": "bot_events", "time_column": "timestamp"},
]
