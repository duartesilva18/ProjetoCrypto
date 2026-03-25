from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.core.data.models import Base, HYPERTABLE_CONFIGS

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = get_settings().database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _create_hypertables(connection) -> None:
    """Convert configured tables into TimescaleDB hypertables."""
    for cfg in HYPERTABLE_CONFIGS:
        await connection.execute(
            text(
                f"SELECT create_hypertable('{cfg['table']}', '{cfg['time_column']}', "
                f"if_not_exists => TRUE, migrate_data => TRUE)"
            )
        )


async def run_async_migrations() -> None:
    settings = get_settings()
    connectable = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        await connection.commit()

        await connection.run_sync(do_run_migrations)

        await _create_hypertables(connection)
        await connection.commit()

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
