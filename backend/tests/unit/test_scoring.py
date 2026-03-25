"""Tests for opportunity scoring."""

from __future__ import annotations

from app.core.strategy.scoring import (
    ScoringWeights,
    score_opportunity,
)


def test_high_rate_high_score():
    s = score_opportunity(
        funding_rate=0.0005,
        predicted_rate=0.0004,
        time_to_funding_seconds=7200,
        spread_bps=2.0,
    )
    assert s > 0.6


def test_low_rate_low_score():
    s = score_opportunity(
        funding_rate=0.00001,
        predicted_rate=None,
        time_to_funding_seconds=None,
        spread_bps=15.0,
    )
    assert s < 0.3


def test_zero_rate_zero_score():
    s = score_opportunity(
        funding_rate=0.0,
        predicted_rate=None,
        time_to_funding_seconds=None,
        spread_bps=0.0,
    )
    assert s < 0.4


def test_opposite_predicted_rate_penalized():
    same_dir = score_opportunity(
        funding_rate=0.0003,
        predicted_rate=0.0002,
        time_to_funding_seconds=7200,
        spread_bps=3.0,
    )
    opp_dir = score_opportunity(
        funding_rate=0.0003,
        predicted_rate=-0.0002,
        time_to_funding_seconds=7200,
        spread_bps=3.0,
    )
    assert same_dir > opp_dir


def test_tight_spread_preferred():
    tight = score_opportunity(
        funding_rate=0.0003,
        predicted_rate=None,
        time_to_funding_seconds=7200,
        spread_bps=1.0,
    )
    wide = score_opportunity(
        funding_rate=0.0003,
        predicted_rate=None,
        time_to_funding_seconds=7200,
        spread_bps=15.0,
    )
    assert tight > wide


def test_optimal_timing_preferred():
    optimal = score_opportunity(
        funding_rate=0.0003,
        predicted_rate=None,
        time_to_funding_seconds=7200,
        spread_bps=3.0,
    )
    imminent = score_opportunity(
        funding_rate=0.0003,
        predicted_rate=None,
        time_to_funding_seconds=600,
        spread_bps=3.0,
    )
    assert optimal > imminent


def test_score_clamped_0_to_1():
    s = score_opportunity(
        funding_rate=0.01,
        predicted_rate=0.01,
        time_to_funding_seconds=7200,
        spread_bps=0.0,
        historical_avg_rate=0.01,
    )
    assert 0.0 <= s <= 1.0


def test_stability_same_sign_preferred():
    stable = score_opportunity(
        funding_rate=0.0003,
        predicted_rate=None,
        time_to_funding_seconds=None,
        spread_bps=3.0,
        historical_avg_rate=0.0003,
    )
    unstable = score_opportunity(
        funding_rate=0.0003,
        predicted_rate=None,
        time_to_funding_seconds=None,
        spread_bps=3.0,
        historical_avg_rate=-0.0001,
    )
    assert stable > unstable


def test_custom_weights():
    w = ScoringWeights(
        rate_magnitude=1.0,
        predicted_rate=0.0,
        time_to_funding=0.0,
        spread=0.0,
        stability=0.0,
    )
    s = score_opportunity(
        funding_rate=0.0005,
        predicted_rate=None,
        time_to_funding_seconds=None,
        spread_bps=100.0,
        weights=w,
    )
    assert s == round(min(1.0, 0.0005 / 0.001), 4)
