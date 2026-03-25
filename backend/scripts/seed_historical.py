"""Download historical funding rates from exchanges and store to CSV.

Usage:
    python -m scripts.seed_historical --exchange binance --symbol BTC/USDT --days 90
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import ccxt.async_support as ccxt


async def fetch_historical_funding(
    exchange_id: str,
    symbol: str,
    days: int,
    output_dir: Path,
) -> Path:
    """Fetch historical funding rates via ccxt and write to CSV."""
    exchange_class = getattr(ccxt, exchange_id, None)
    if exchange_class is None:
        print(f"Unsupported exchange: {exchange_id}")
        sys.exit(1)

    exchange = exchange_class({"enableRateLimit": True})

    try:
        await exchange.load_markets()

        perp_symbol = symbol
        if ":" not in symbol:
            base_quote = symbol.split("/")
            if len(base_quote) == 2:
                perp_symbol = f"{symbol}:{base_quote[1]}"

        since_ms = int((datetime.now(UTC) - timedelta(days=days)).timestamp() * 1000)
        all_rates: list[dict] = []

        print(f"Fetching {days}d of funding rates for {perp_symbol} on {exchange_id}...")

        while True:
            params = {"since": since_ms, "limit": 100}
            try:
                rates = await exchange.fetch_funding_rate_history(perp_symbol, **params)
            except Exception as exc:
                print(f"Warning: fetch_funding_rate_history failed: {exc}")
                break

            if not rates:
                break

            all_rates.extend(rates)
            last_ts = rates[-1].get("timestamp", 0)
            if last_ts <= since_ms:
                break
            since_ms = last_ts + 1

            if len(all_rates) % 500 == 0:
                print(f"  ... collected {len(all_rates)} records")

        output_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
        safe_symbol = symbol.replace("/", "_")
        output_path = output_dir / f"{exchange_id}_{safe_symbol}_funding_{days}d.csv"

        with open(output_path, "w", newline="") as f:  # noqa: ASYNC230
            writer = csv.writer(f)
            writer.writerow(
                [
                    "timestamp",
                    "datetime",
                    "exchange",
                    "symbol",
                    "funding_rate",
                    "mark_price",
                    "index_price",
                ]
            )
            for r in all_rates:
                ts = r.get("timestamp", 0)
                dt = datetime.fromtimestamp(ts / 1000, tz=UTC).isoformat() if ts else ""
                writer.writerow(
                    [
                        ts,
                        dt,
                        exchange_id,
                        symbol,
                        r.get("fundingRate", 0),
                        r.get("markPrice", ""),
                        r.get("indexPrice", ""),
                    ]
                )

        print(f"Saved {len(all_rates)} records to {output_path}")
        return output_path

    finally:
        await exchange.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed historical funding rate data")
    parser.add_argument("--exchange", default="binance", help="Exchange ID (ccxt)")
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading pair")
    parser.add_argument("--days", type=int, default=90, help="Number of days to fetch")
    parser.add_argument("--output-dir", default="data/historical", help="Output directory")
    args = parser.parse_args()

    asyncio.run(
        fetch_historical_funding(
            exchange_id=args.exchange,
            symbol=args.symbol,
            days=args.days,
            output_dir=Path(args.output_dir),
        )
    )


if __name__ == "__main__":
    main()
