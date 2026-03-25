"""Initial schema with all tables.

Revision ID: 001
Revises: None
Create Date: 2026-03-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── funding_rates (hypertable) ────────────
    op.create_table(
        "funding_rates",
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exchange", sa.String(20), nullable=False),
        sa.Column("symbol", sa.String(30), nullable=False),
        sa.Column("funding_rate", sa.Numeric(18, 10), nullable=False),
        sa.Column("predicted_rate", sa.Numeric(18, 10)),
        sa.Column("mark_price", sa.Numeric(18, 8)),
        sa.Column("index_price", sa.Numeric(18, 8)),
        sa.PrimaryKeyConstraint("timestamp", "exchange", "symbol"),
    )
    op.create_index(
        "ix_funding_rates_exchange_symbol",
        "funding_rates",
        ["exchange", "symbol"],
    )

    # ── positions ─────────────────────────────
    op.create_table(
        "positions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exchange", sa.String(20), nullable=False),
        sa.Column("symbol", sa.String(30), nullable=False),
        sa.Column(
            "side",
            sa.Enum("LONG_SPOT_SHORT_PERP", "SHORT_SPOT_LONG_PERP", name="positionside"),
            nullable=False,
        ),
        sa.Column("spot_qty", sa.Numeric(18, 8), nullable=False),
        sa.Column("perp_qty", sa.Numeric(18, 8), nullable=False),
        sa.Column("entry_price_spot", sa.Numeric(18, 8), nullable=False),
        sa.Column("entry_price_perp", sa.Numeric(18, 8), nullable=False),
        sa.Column(
            "status",
            sa.Enum("OPEN", "CLOSING", "CLOSED", name="positionstatus"),
            server_default="OPEN",
        ),
        sa.Column("funding_collected", sa.Numeric(18, 8), server_default="0"),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("is_paper", sa.Boolean(), server_default="true"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_positions_status", "positions", ["status"])
    op.create_index(
        "ix_positions_exchange_symbol", "positions", ["exchange", "symbol"]
    )

    # ── trades (hypertable) ───────────────────
    op.create_table(
        "trades",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("position_id", sa.Uuid()),
        sa.Column("exchange", sa.String(20), nullable=False),
        sa.Column("symbol", sa.String(30), nullable=False),
        sa.Column(
            "side", sa.Enum("BUY", "SELL", name="tradeside"), nullable=False
        ),
        sa.Column(
            "market", sa.Enum("SPOT", "PERP", name="trademarket"), nullable=False
        ),
        sa.Column("qty", sa.Numeric(18, 8), nullable=False),
        sa.Column("price", sa.Numeric(18, 8), nullable=False),
        sa.Column("fee", sa.Numeric(18, 8), server_default="0"),
        sa.Column("order_id", sa.String(100)),
        sa.Column("is_paper", sa.Boolean(), server_default="true"),
        sa.PrimaryKeyConstraint("id", "timestamp"),
    )
    op.create_index("ix_trades_position_id", "trades", ["position_id"])

    # ── funding_payments (hypertable) ─────────
    op.create_table(
        "funding_payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("position_id", sa.Uuid()),
        sa.Column("exchange", sa.String(20), nullable=False),
        sa.Column("symbol", sa.String(30), nullable=False),
        sa.Column("payment", sa.Numeric(18, 8), nullable=False),
        sa.Column("rate", sa.Numeric(18, 10), nullable=False),
        sa.PrimaryKeyConstraint("id", "timestamp"),
    )
    op.create_index(
        "ix_funding_payments_position_id", "funding_payments", ["position_id"]
    )

    # ── equity_snapshots (hypertable) ─────────
    op.create_table(
        "equity_snapshots",
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_equity", sa.Numeric(18, 8), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(18, 8), server_default="0"),
        sa.Column("realized_pnl", sa.Numeric(18, 8), server_default="0"),
        sa.Column("funding_pnl", sa.Numeric(18, 8), server_default="0"),
        sa.Column("positions_count", sa.Integer(), server_default="0"),
        sa.PrimaryKeyConstraint("timestamp"),
    )

    # ── bot_events (hypertable) ───────────────
    op.create_table(
        "bot_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "level",
            sa.Enum("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", name="eventlevel"),
            nullable=False,
        ),
        sa.Column("component", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata", JSONB()),
        sa.PrimaryKeyConstraint("id", "timestamp"),
    )
    op.create_index("ix_bot_events_level", "bot_events", ["level"])
    op.create_index("ix_bot_events_component", "bot_events", ["component"])
    op.create_index("ix_bot_events_timestamp", "bot_events", ["timestamp"])


def downgrade() -> None:
    op.drop_table("bot_events")
    op.drop_table("equity_snapshots")
    op.drop_table("funding_payments")
    op.drop_table("trades")
    op.drop_table("positions")
    op.drop_table("funding_rates")

    for enum_name in (
        "eventlevel", "trademarket", "tradeside",
        "positionstatus", "positionside",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
