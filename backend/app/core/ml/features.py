"""Feature extraction pipeline for funding rate prediction.

Extracts time-series features from historical funding rate data
for use with the gradient boosting predictor.
"""

from __future__ import annotations

import numpy as np


def extract_features(rates: list[float], timestamps_h: list[float] | None = None) -> dict:
    """Extract features from a sequence of funding rates.

    Args:
        rates: Historical funding rate values (most recent last).
        timestamps_h: Hours since epoch for each rate (optional).

    Returns:
        Feature dictionary suitable for model input.
    """
    if len(rates) < 3:
        return _empty_features()

    arr = np.array(rates, dtype=np.float64)

    features = {
        "rate_current": arr[-1],
        "rate_mean_3": float(np.mean(arr[-3:])),
        "rate_mean_6": float(np.mean(arr[-6:])) if len(arr) >= 6 else float(np.mean(arr)),
        "rate_mean_12": float(np.mean(arr[-12:])) if len(arr) >= 12 else float(np.mean(arr)),
        "rate_std_6": float(np.std(arr[-6:])) if len(arr) >= 6 else float(np.std(arr)),
        "rate_std_12": float(np.std(arr[-12:])) if len(arr) >= 12 else float(np.std(arr)),
        "rate_min_6": float(np.min(arr[-6:])) if len(arr) >= 6 else float(np.min(arr)),
        "rate_max_6": float(np.max(arr[-6:])) if len(arr) >= 6 else float(np.max(arr)),
        "rate_trend": float(arr[-1] - arr[-3]) if len(arr) >= 3 else 0.0,
        "rate_momentum": float(arr[-1] - arr[0]),
        "rate_sign_changes": _count_sign_changes(arr[-12:] if len(arr) >= 12 else arr),
        "rate_abs_mean": float(np.mean(np.abs(arr))),
        "positive_ratio": float(np.sum(arr > 0) / len(arr)),
    }

    if timestamps_h is not None and len(timestamps_h) == len(rates):
        h = timestamps_h[-1] % 24
        features["hour_sin"] = float(np.sin(2 * np.pi * h / 24))
        features["hour_cos"] = float(np.cos(2 * np.pi * h / 24))
    else:
        features["hour_sin"] = 0.0
        features["hour_cos"] = 0.0

    return features


def features_to_array(features: dict) -> np.ndarray:
    """Convert feature dict to ordered numpy array for model input."""
    return np.array([features[k] for k in sorted(features.keys())], dtype=np.float64)


def feature_names() -> list[str]:
    """Return sorted list of feature names (matches features_to_array order)."""
    return sorted(_empty_features().keys())


def _empty_features() -> dict:
    return {
        "rate_current": 0.0,
        "rate_mean_3": 0.0,
        "rate_mean_6": 0.0,
        "rate_mean_12": 0.0,
        "rate_std_6": 0.0,
        "rate_std_12": 0.0,
        "rate_min_6": 0.0,
        "rate_max_6": 0.0,
        "rate_trend": 0.0,
        "rate_momentum": 0.0,
        "rate_sign_changes": 0.0,
        "rate_abs_mean": 0.0,
        "positive_ratio": 0.0,
        "hour_sin": 0.0,
        "hour_cos": 0.0,
    }


def _count_sign_changes(arr: np.ndarray) -> float:
    if len(arr) < 2:
        return 0.0
    signs = np.sign(arr)
    return float(np.sum(signs[1:] != signs[:-1]))
