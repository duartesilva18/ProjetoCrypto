"""Train the funding rate prediction model.

Usage:
    python -m scripts.train_model --input data/historical/binance_BTC_USDT_funding_90d.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

from app.core.ml.features import extract_features, feature_names, features_to_array
from app.core.ml.predictor import FundingRatePredictor, train_model


def load_rates_from_csv(path: Path) -> tuple[list[float], list[float]]:
    """Load funding rates and timestamps from historical CSV."""
    rates: list[float] = []
    timestamps_h: list[float] = []

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rate = float(row.get("funding_rate", 0))
                ts = int(row.get("timestamp", 0))
            except (TypeError, ValueError):
                continue
            rates.append(rate)
            timestamps_h.append(ts / 1000 / 3600)

    return rates, timestamps_h


def build_training_data(
    rates: list[float],
    timestamps_h: list[float],
    lookback: int = 12,
) -> tuple[np.ndarray, np.ndarray]:
    """Build feature matrix X and target vector y.

    For each point i (where i >= lookback), uses rates[i-lookback:i]
    as features and rates[i] as the target (next rate prediction).
    """
    x_list = []
    y_list = []

    for i in range(lookback, len(rates)):
        window_rates = rates[i - lookback : i]
        window_ts = timestamps_h[i - lookback : i] if timestamps_h else None

        features = extract_features(window_rates, window_ts)
        x_list.append(features_to_array(features))
        y_list.append(rates[i])

    return np.array(x_list), np.array(y_list)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train funding rate prediction model")
    parser.add_argument("--input", required=True, help="Path to historical CSV")
    parser.add_argument("--lookback", type=int, default=12, help="Lookback window size")
    parser.add_argument(
        "--output", default="models/funding_rate_model.pkl", help="Model output path"
    )
    parser.add_argument("--n-estimators", type=int, default=200)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input file not found: {input_path}")
        sys.exit(1)

    print(f"Loading data from {input_path}...")
    rates, timestamps_h = load_rates_from_csv(input_path)
    print(f"  Loaded {len(rates)} funding rate records")

    if len(rates) < args.lookback + 10:
        print(f"Not enough data (need at least {args.lookback + 10} records)")
        sys.exit(1)

    print(f"Building features with lookback={args.lookback}...")
    x, y = build_training_data(rates, timestamps_h, lookback=args.lookback)
    print(f"  Training samples: {len(x)}, Features: {x.shape[1]}")

    split = int(len(x) * 0.8)
    x_train, x_test = x[:split], x[split:]
    y_train, y_test = y[:split], y[split:]

    print("Training model...")
    model = train_model(
        x_train,
        y_train,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        learning_rate=args.learning_rate,
    )

    y_pred = model.predict(x_test)
    mae = np.mean(np.abs(y_test - y_pred))
    rmse = np.sqrt(np.mean((y_test - y_pred) ** 2))
    direction_accuracy = np.mean(np.sign(y_test) == np.sign(y_pred)) * 100

    print(f"\n  Test MAE:           {mae:.8f}")
    print(f"  Test RMSE:          {rmse:.8f}")
    print(f"  Direction Accuracy: {direction_accuracy:.1f}%")

    predictor = FundingRatePredictor(model_path=args.output)
    predictor.save(model)
    print(f"\nModel saved to {args.output}")

    names = feature_names()
    importances = model.feature_importances_
    ranked = sorted(zip(names, importances, strict=False), key=lambda x: x[1], reverse=True)
    print("\nTop 5 feature importances:")
    for name, imp in ranked[:5]:
        print(f"  {name:25s} {imp:.4f}")


if __name__ == "__main__":
    main()
