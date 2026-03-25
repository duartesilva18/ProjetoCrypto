from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Bot ───────────────────────────────────
    bot_mode: str = Field(default="paper", pattern=r"^(paper|live)$")
    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR)$")

    # ── Database ──────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "projetocrypto"
    postgres_user: str = "trader"
    postgres_password: str = "devpassword"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ── Redis ─────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    # ── Exchange API Keys ─────────────────────
    binance_api_key: str = ""
    binance_api_secret: str = ""
    bybit_api_key: str = ""
    bybit_api_secret: str = ""
    okx_api_key: str = ""
    okx_api_secret: str = ""
    okx_passphrase: str = ""

    # ── Strategy ──────────────────────────────
    funding_rate_entry_threshold: float = 0.0001
    funding_rate_exit_threshold: float = 0.00005
    min_opportunity_score: float = 0.5
    watched_symbols: str = "BTC/USDT,ETH/USDT,SOL/USDT"

    @property
    def watched_symbols_list(self) -> list[str]:
        return [s.strip() for s in self.watched_symbols.split(",") if s.strip()]

    # ── Risk ──────────────────────────────────
    max_exposure_per_exchange: float = 0.30
    max_exposure_per_pair: float = 0.10
    max_daily_drawdown: float = 0.02
    max_daily_drawdown_hard: float = 0.03
    margin_buffer: float = 0.30

    # ── Execution ─────────────────────────────
    twap_steps: int = 3
    twap_step_delay_seconds: float = 3.0

    # ── Auth ──────────────────────────────────
    jwt_secret: str = "CHANGE_ME_IN_PRODUCTION"
    dashboard_password: str = "admin"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
