"""Factory for creating exchange connectors by ID."""

from __future__ import annotations

from app.core.exchange.base import BaseExchangeConnector
from app.core.exchange.binance import BinanceConnector
from app.core.exchange.bybit import BybitConnector
from app.core.exchange.gate import GateConnector
from app.core.exchange.okx import OKXConnector

_REGISTRY: dict[str, type[BaseExchangeConnector]] = {
    "binance": BinanceConnector,
    "bybit": BybitConnector,
    "okx": OKXConnector,
    "gate": GateConnector,
}

SUPPORTED_EXCHANGES: list[str] = list(_REGISTRY.keys())


def create_connector(exchange_id: str) -> BaseExchangeConnector:
    """Create an exchange connector instance by ID.

    Raises ValueError if the exchange is not supported.
    """
    cls = _REGISTRY.get(exchange_id.lower())
    if cls is None:
        raise ValueError(
            f"Unsupported exchange '{exchange_id}'. Supported: {', '.join(SUPPORTED_EXCHANGES)}"
        )
    return cls()


async def create_all_connectors() -> dict[str, BaseExchangeConnector]:
    """Create and connect all supported exchange connectors."""
    connectors: dict[str, BaseExchangeConnector] = {}
    for exchange_id in SUPPORTED_EXCHANGES:
        connector = create_connector(exchange_id)
        await connector.connect()
        connectors[exchange_id] = connector
    return connectors
