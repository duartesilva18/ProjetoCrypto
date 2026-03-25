"""Backtesting engine for funding rate arbitrage strategy.

Simulates the strategy over historical funding rate data and outputs
P&L metrics, trade log, and equity curve.

Usage:
    python -m scripts.backtest --input data/historical/binance_BTC_USDT_funding_90d.csv
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BacktestConfig:
    initial_capital: float = 10_000.0
    entry_threshold: float = 0.00005
    exit_threshold: float = 0.00001
    position_size_pct: float = 0.05
    fee_bps: float = 10.0
    slippage_bps: float = 2.0


@dataclass
class BacktestPosition:
    entry_time: str = ""
    symbol: str = ""
    exchange: str = ""
    side: str = ""
    entry_rate: float = 0.0
    notional: float = 0.0
    funding_collected: float = 0.0
    exit_time: str | None = None
    exit_rate: float = 0.0
    pnl: float = 0.0


@dataclass
class BacktestResult:
    config: BacktestConfig
    total_trades: int = 0
    winning_trades: int = 0
    total_funding_collected: float = 0.0
    total_fees_paid: float = 0.0
    final_equity: float = 0.0
    max_drawdown_pct: float = 0.0
    annualized_return_pct: float = 0.0
    equity_curve: list[tuple[str, float]] = field(default_factory=list)
    trades: list[BacktestPosition] = field(default_factory=list)

    def summary(self) -> str:
        net_pnl = self.final_equity - self.config.initial_capital
        win_rate = self.winning_trades / self.total_trades * 100 if self.total_trades > 0 else 0
        return (
            f"\n{'=' * 60}\n"
            f"  BACKTEST RESULTS\n"
            f"{'=' * 60}\n"
            f"  Initial Capital:     ${self.config.initial_capital:>12,.2f}\n"
            f"  Final Equity:        ${self.final_equity:>12,.2f}\n"
            f"  Net P&L:             ${net_pnl:>12,.2f}\n"
            f"  Total Trades:        {self.total_trades:>12}\n"
            f"  Win Rate:            {win_rate:>11.1f}%\n"
            f"  Funding Collected:   ${self.total_funding_collected:>12,.4f}\n"
            f"  Fees Paid:           ${self.total_fees_paid:>12,.4f}\n"
            f"  Max Drawdown:        {self.max_drawdown_pct:>11.2f}%\n"
            f"  Annualized Return:   {self.annualized_return_pct:>11.2f}%\n"
            f"{'=' * 60}\n"
        )


def run_backtest(data_path: Path, config: BacktestConfig | None = None) -> BacktestResult:
    """Run backtest over a CSV of historical funding rates."""
    cfg = config or BacktestConfig()
    result = BacktestResult(config=cfg)

    rows = _load_csv(data_path)
    if not rows:
        print(f"No data found in {data_path}")
        return result

    capital = cfg.initial_capital
    peak_equity = capital
    max_dd = 0.0
    position: BacktestPosition | None = None

    for row in rows:
        rate = float(row.get("funding_rate", 0))
        dt = row.get("datetime", "")
        symbol = row.get("symbol", "")
        exchange = row.get("exchange", "")

        if position is None:
            if abs(rate) >= cfg.entry_threshold:
                size = capital * cfg.position_size_pct
                fee = size * cfg.fee_bps / 10_000 * 2
                side = "LONG_SPOT_SHORT_PERP" if rate > 0 else "SHORT_SPOT_LONG_PERP"
                position = BacktestPosition(
                    entry_time=dt,
                    symbol=symbol,
                    exchange=exchange,
                    side=side,
                    entry_rate=rate,
                    notional=size,
                )
                capital -= fee
                result.total_fees_paid += fee
        else:
            if position.side == "LONG_SPOT_SHORT_PERP":
                sign = 1 if rate > 0 else -1
            else:
                sign = 1 if rate < 0 else -1
            payment = sign * position.notional * abs(rate)

            position.funding_collected += payment
            capital += payment
            result.total_funding_collected += payment

            if abs(rate) < cfg.exit_threshold:
                fee = position.notional * cfg.fee_bps / 10_000 * 2
                capital -= fee
                result.total_fees_paid += fee
                position.exit_time = dt
                position.exit_rate = rate
                position.pnl = position.funding_collected - fee
                result.trades.append(position)
                result.total_trades += 1
                if position.pnl > 0:
                    result.winning_trades += 1
                position = None

        peak_equity = max(peak_equity, capital)
        dd = (peak_equity - capital) / peak_equity * 100 if peak_equity > 0 else 0
        max_dd = max(max_dd, dd)
        result.equity_curve.append((dt, round(capital, 2)))

    if position is not None:
        position.exit_time = rows[-1].get("datetime", "")
        position.pnl = position.funding_collected
        result.trades.append(position)
        result.total_trades += 1
        if position.pnl > 0:
            result.winning_trades += 1

    result.final_equity = round(capital, 2)
    result.max_drawdown_pct = round(max_dd, 4)

    if len(rows) >= 2:
        first_ts = rows[0].get("timestamp", 0)
        last_ts = rows[-1].get("timestamp", 0)
        try:
            days = (int(last_ts) - int(first_ts)) / 1000 / 86400
        except (TypeError, ValueError):
            days = 1
        if days > 0:
            total_return = (capital - cfg.initial_capital) / cfg.initial_capital
            result.annualized_return_pct = round(total_return * (365 / days) * 100, 2)

    return result


def _load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest funding rate arbitrage strategy")
    parser.add_argument("--input", required=True, help="Path to historical CSV")
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument("--entry-threshold", type=float, default=0.00005)
    parser.add_argument("--exit-threshold", type=float, default=0.00001)
    parser.add_argument("--position-size-pct", type=float, default=0.05)
    parser.add_argument("--output-equity", default="", help="Save equity curve CSV")
    args = parser.parse_args()

    cfg = BacktestConfig(
        initial_capital=args.capital,
        entry_threshold=args.entry_threshold,
        exit_threshold=args.exit_threshold,
        position_size_pct=args.position_size_pct,
    )

    result = run_backtest(Path(args.input), cfg)
    print(result.summary())

    if args.output_equity:
        out = Path(args.output_equity)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["datetime", "equity"])
            for dt, eq in result.equity_curve:
                writer.writerow([dt, eq])
        print(f"Equity curve saved to {out}")


if __name__ == "__main__":
    main()
