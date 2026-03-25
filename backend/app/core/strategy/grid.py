"""Grid Trading strategy for range-bound markets.

Places simulated buy/sell orders across a price grid and profits
from price oscillations within the range. Market-neutral when
the grid is symmetric around the current price.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

from app.core.data.state import StateStore

logger = structlog.get_logger(__name__)

_DEFAULT_GRID_LEVELS = 10
_DEFAULT_GRID_SPREAD_PCT = 2.0


@dataclass
class GridOrder:
    price: float
    side: str
    filled: bool = False
    filled_at: datetime | None = None


@dataclass
class GridPosition:
    id: str = ""
    exchange: str = ""
    symbol: str = ""
    strategy: str = "grid"
    grid_low: float = 0.0
    grid_high: float = 0.0
    levels: int = _DEFAULT_GRID_LEVELS
    buy_orders: list[GridOrder] = field(default_factory=list)
    sell_orders: list[GridOrder] = field(default_factory=list)
    qty_per_level: float = 0.0
    total_profit: float = 0.0
    trades_completed: int = 0
    opened_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    @property
    def notional_value(self) -> float:
        return self.qty_per_level * ((self.grid_low + self.grid_high) / 2) * self.levels

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "side": "GRID",
            "spot_qty": self.qty_per_level * self.levels,
            "perp_qty": 0.0,
            "entry_price_spot": (self.grid_low + self.grid_high) / 2,
            "entry_price_perp": 0.0,
            "funding_collected": self.total_profit,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "grid_low": self.grid_low,
            "grid_high": self.grid_high,
            "levels": self.levels,
            "trades_completed": self.trades_completed,
        }


@dataclass
class GridSignal:
    action: str  # "open", "close", "hold"
    exchange: str = ""
    symbol: str = ""
    grid_low: float = 0.0
    grid_high: float = 0.0
    reason: str = ""
    score: float = 0.0


class GridStrategy:
    """Evaluates grid trading opportunities based on price range analysis."""

    def __init__(
        self,
        symbols: list[str],
        grid_spread_pct: float = _DEFAULT_GRID_SPREAD_PCT,
        grid_levels: int = _DEFAULT_GRID_LEVELS,
        min_volatility_pct: float = 0.5,
        max_volatility_pct: float = 5.0,
    ) -> None:
        self._symbols = symbols
        self._grid_spread_pct = grid_spread_pct
        self._grid_levels = grid_levels
        self._min_vol = min_volatility_pct
        self._max_vol = max_volatility_pct
        self._price_history: dict[str, list[float]] = {}

    async def evaluate(
        self,
        state: StateStore,
        open_grids: dict[str, GridPosition],
    ) -> GridSignal:
        """Evaluate whether to open/close grid positions."""
        for symbol in self._symbols:
            if symbol in open_grids:
                continue

            prices = await self._collect_price(state, symbol)
            if len(prices) < 5:
                continue

            volatility = self._calculate_volatility(prices)

            if self._min_vol <= volatility <= self._max_vol:
                mid = prices[-1]
                half_spread = mid * self._grid_spread_pct / 100
                score = min(1.0, volatility / self._max_vol)

                best_exchange = await self._find_best_exchange(state, symbol)

                logger.info(
                    "grid_opportunity",
                    symbol=symbol,
                    exchange=best_exchange,
                    volatility=round(volatility, 3),
                    score=round(score, 3),
                )

                return GridSignal(
                    action="open",
                    exchange=best_exchange,
                    symbol=symbol,
                    grid_low=round(mid - half_spread, 8),
                    grid_high=round(mid + half_spread, 8),
                    score=score,
                    reason=f"Volatility {volatility:.2f}% in range",
                )

        for _key, grid in open_grids.items():
            prices = await self._collect_price(state, grid.symbol)
            if not prices:
                continue
            current = prices[-1]
            if current < grid.grid_low * 0.95 or current > grid.grid_high * 1.05:
                return GridSignal(
                    action="close",
                    exchange=grid.exchange,
                    symbol=grid.symbol,
                    reason=f"Price ${current:.2f} broke out of grid range",
                )

        return GridSignal(action="hold", reason="No grid opportunity")

    async def _collect_price(self, state: StateStore, symbol: str) -> list[float]:
        for exchange in ["binance", "bybit", "okx", "gate"]:
            ticker = await state.get_ticker(exchange, symbol)
            if ticker:
                try:
                    price = float(ticker.get("last", 0))
                except (TypeError, ValueError):
                    continue
                if price > 0:
                    key = symbol
                    if key not in self._price_history:
                        self._price_history[key] = []
                    self._price_history[key].append(price)
                    if len(self._price_history[key]) > 100:
                        self._price_history[key] = self._price_history[key][-100:]
                    return self._price_history[key]
        return []

    async def _find_best_exchange(self, state: StateStore, symbol: str) -> str:
        best_exchange = "binance"
        best_spread = float("inf")
        for exchange in ["binance", "bybit", "okx", "gate"]:
            ticker = await state.get_ticker(exchange, symbol)
            if ticker:
                try:
                    spread = float(ticker.get("spread_bps", 999))
                    if spread < best_spread:
                        best_spread = spread
                        best_exchange = exchange
                except (TypeError, ValueError):
                    continue
        return best_exchange

    @staticmethod
    def _calculate_volatility(prices: list[float]) -> float:
        if len(prices) < 2:
            return 0.0
        returns = [
            abs(prices[i] - prices[i - 1]) / prices[i - 1] * 100 for i in range(1, len(prices))
        ]
        return sum(returns) / len(returns)
