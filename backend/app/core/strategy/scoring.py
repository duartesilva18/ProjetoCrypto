"""Multi-factor weighted scoring for funding rate opportunities.

Factors:
  1. Funding rate magnitude   (40%) -- higher |rate| = better
  2. Predicted next rate      (30%) -- consistency signal / early entry
  3. Time to next funding     (15%) -- prefer entering before settlement
  4. Spread / slippage        (10%) -- tighter spread = cheaper entry
  5. Historical rate stability( 5%) -- steadier rates are more reliable
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ScoringWeights:
    rate_magnitude: float = 0.40
    predicted_rate: float = 0.30
    time_to_funding: float = 0.15
    spread: float = 0.10
    stability: float = 0.05


_RATE_NORMALIZER = 0.001
_SPREAD_MAX_BPS = 20.0
_FUNDING_WINDOW_SECONDS = 8 * 3600.0


def score_opportunity(
    funding_rate: float,
    predicted_rate: float | None,
    time_to_funding_seconds: float | None,
    spread_bps: float,
    historical_avg_rate: float | None = None,
    weights: ScoringWeights | None = None,
) -> float:
    """Compute a 0-1 score for a funding rate arbitrage opportunity.

    Higher score = more attractive opportunity.
    Returns 0.0 if the opportunity is clearly unattractive.
    """
    w = weights or ScoringWeights()

    rate_score = _score_rate_magnitude(funding_rate)
    pred_score = _score_predicted_rate(funding_rate, predicted_rate)
    time_score = _score_time_to_funding(time_to_funding_seconds)
    spread_score = _score_spread(spread_bps)
    stability_score = _score_stability(funding_rate, historical_avg_rate)

    total = (
        w.rate_magnitude * rate_score
        + w.predicted_rate * pred_score
        + w.time_to_funding * time_score
        + w.spread * spread_score
        + w.stability * stability_score
    )

    return round(min(1.0, max(0.0, total)), 4)


def _score_rate_magnitude(rate: float) -> float:
    """Higher absolute rate = higher score. Normalized against 0.1% (10 bps)."""
    return min(1.0, abs(rate) / _RATE_NORMALIZER)


def _score_predicted_rate(current: float, predicted: float | None) -> float:
    """Score based on whether the predicted rate confirms the current direction.

    Full score if predicted rate has the same sign and >= magnitude.
    Partial if same sign but lower. Zero if opposite sign.
    """
    if predicted is None:
        return 0.5

    if current == 0:
        return 0.5

    same_sign = (current > 0 and predicted > 0) or (current < 0 and predicted < 0)
    if not same_sign:
        return 0.0

    ratio = abs(predicted) / abs(current) if current != 0 else 0
    return min(1.0, ratio)


def _score_time_to_funding(seconds: float | None) -> float:
    """Prefer entering 1-4 hours before funding settlement.

    Peak score at ~2 hours. Low score if funding is imminent (<30 min)
    or very far away (>6 hours).
    """
    if seconds is None:
        return 0.5

    hours = seconds / 3600.0

    if hours < 0.5:
        return 0.3
    if hours <= 4.0:
        return 1.0 - abs(hours - 2.0) / 4.0
    return max(0.1, 1.0 - (hours - 4.0) / 4.0)


def _score_spread(spread_bps: float) -> float:
    """Lower spread = higher score. Zero spread is perfect, >20 bps is bad."""
    if spread_bps <= 0:
        return 1.0
    return max(0.0, 1.0 - spread_bps / _SPREAD_MAX_BPS)


def _score_stability(current: float, historical_avg: float | None) -> float:
    """Rate consistency: if current rate is close to 24h average, it's stable."""
    if historical_avg is None:
        return 0.5

    if historical_avg == 0:
        return 0.5 if current == 0 else 0.3

    same_sign = (current > 0 and historical_avg > 0) or (current < 0 and historical_avg < 0)
    if not same_sign:
        return 0.1

    ratio = min(abs(current), abs(historical_avg)) / max(abs(current), abs(historical_avg))
    return ratio
