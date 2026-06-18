"""Transparent signal blend from mlb-predictor-dashboard (ensemble-v3)."""

from __future__ import annotations

import math


def _clip(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def _logit(probability: float) -> float:
    probability = _clip(float(probability), 0.001, 0.999)
    return math.log(probability / (1.0 - probability))


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def robust_signal_score(feature_map: dict[str, float]) -> float:
    """Positive favors home team."""
    signal = 0.0
    signal += 0.0030 * _clip(float(feature_map.get("elo_difference", 0.0)), -180.0, 180.0)
    signal += 0.18 * _clip(float(feature_map.get("diff_run_diff_15", feature_map.get("home_run_differential", 0.0) - feature_map.get("away_run_differential", 0.0))), -5.0, 5.0)
    signal += 0.90 * _clip(
        float(
            feature_map.get(
                "season_win_pct_diff",
                feature_map.get("home_win_pct", 0.5) - feature_map.get("away_win_pct", 0.5),
            )
        ),
        -0.35,
        0.35,
    )
    signal += 0.65 * _clip(
        float(feature_map.get("diff_win_pct_15", feature_map.get("home_win_pct", 0.5) - feature_map.get("away_win_pct", 0.5))),
        -0.45,
        0.45,
    )
    signal += 0.08 * _clip(
        float(feature_map.get("rest_days_delta", feature_map.get("home_rest_days", 0.0) - feature_map.get("away_rest_days", 0.0))),
        -2.0,
        2.0,
    )
    signal += 0.10

    market_delta = float(feature_map.get("market_prob_delta", 0.0))
    if abs(market_delta) <= 0.02:
        market_delta = float(feature_map.get("market_home_implied_probability", 0.5)) - float(
            feature_map.get("market_away_implied_probability", 0.5)
        )
    if abs(market_delta) > 0.02:
        signal += 1.15 * _clip(market_delta, -0.30, 0.30)

    injury_delta = float(feature_map.get("injury_count_delta", 0.0))
    if injury_delta:
        signal -= 0.04 * _clip(injury_delta, -8.0, 8.0)

    return float(_clip(signal, -1.25, 1.25))


def robust_home_probability(model_probability: float, feature_map: dict[str, float]) -> float:
    base = _clip(float(model_probability), 0.03, 0.97)
    signal = robust_signal_score(feature_map)
    adjusted_logit = 0.75 * _logit(base) + signal
    return float(_clip(_sigmoid(adjusted_logit), 0.03, 0.97))
