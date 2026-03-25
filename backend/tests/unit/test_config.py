from __future__ import annotations

from app.config import Settings


def test_default_settings():
    s = Settings()
    assert s.bot_mode == "paper"
    assert s.postgres_db == "projetocrypto"
    assert "asyncpg" in s.database_url
    assert s.watched_symbols_list == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


def test_database_url_format():
    s = Settings(postgres_user="u", postgres_password="p", postgres_host="h", postgres_port=1234)
    assert s.database_url == "postgresql+asyncpg://u:p@h:1234/projetocrypto"
    assert s.database_url_sync == "postgresql://u:p@h:1234/projetocrypto"


def test_watched_symbols_parsing():
    s = Settings(watched_symbols="BTC/USDT, ETH/USDT , SOL/USDT")
    assert s.watched_symbols_list == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


def test_redis_url():
    s = Settings(redis_host="myhost", redis_port=6380)
    assert s.redis_url == "redis://myhost:6380/0"
