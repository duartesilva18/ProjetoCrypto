"""Gradient boosting predictor for funding rate forecasting.

Wraps scikit-learn's GradientBoostingRegressor with save/load
and a predict interface compatible with the strategy engine.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import structlog

from app.core.ml.features import extract_features, features_to_array

logger = structlog.get_logger(__name__)

_DEFAULT_MODEL_PATH = Path("models/funding_rate_model.pkl")


class FundingRatePredictor:
    """Predicts the next funding rate from historical data."""

    def __init__(self, model_path: Path | str | None = None) -> None:
        self._model_path = Path(model_path) if model_path else _DEFAULT_MODEL_PATH
        self._model = None
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> bool:
        """Load a trained model from disk. Returns True if successful."""
        if not self._model_path.exists():
            logger.info("ml_model_not_found", path=str(self._model_path))
            return False

        try:
            with open(self._model_path, "rb") as f:
                self._model = pickle.load(f)  # noqa: S301
            self._loaded = True
            logger.info("ml_model_loaded", path=str(self._model_path))
            return True
        except Exception as exc:
            logger.error("ml_model_load_error", error=str(exc))
            return False

    def save(self, model) -> None:
        """Save a trained model to disk."""
        self._model_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._model_path, "wb") as f:
            pickle.dump(model, f)
        self._model = model
        self._loaded = True
        logger.info("ml_model_saved", path=str(self._model_path))

    def predict(self, rates: list[float], timestamps_h: list[float] | None = None) -> float | None:
        """Predict the next funding rate from historical rates.

        Returns None if the model is not loaded or input is insufficient.
        """
        if not self._loaded or self._model is None:
            return None

        features = extract_features(rates, timestamps_h)
        if features["rate_current"] == 0.0 and features["rate_mean_3"] == 0.0:
            return None

        x = features_to_array(features).reshape(1, -1)
        try:
            prediction = float(self._model.predict(x)[0])
            return prediction
        except Exception as exc:
            logger.warning("ml_predict_error", error=str(exc))
            return None

    def predict_from_features(self, features: dict) -> float | None:
        """Predict from pre-computed features."""
        if not self._loaded or self._model is None:
            return None
        x = features_to_array(features).reshape(1, -1)
        try:
            return float(self._model.predict(x)[0])
        except Exception as exc:
            logger.warning("ml_predict_error", error=str(exc))
            return None


def train_model(
    x: np.ndarray,
    y: np.ndarray,
    n_estimators: int = 200,
    max_depth: int = 4,
    learning_rate: float = 0.05,
):
    """Train a GradientBoostingRegressor and return it."""
    from sklearn.ensemble import GradientBoostingRegressor

    model = GradientBoostingRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        loss="huber",
        random_state=42,
    )
    model.fit(x, y)
    return model
