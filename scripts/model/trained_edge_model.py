"""Trained lightweight MLB predictor for page-load daily boards.

The full research model can be slow because it pulls many external features.
This model is designed to be fast, chronological, and auditable: features are
built only from information available before first pitch, then a calibrated
logistic model is trained on prior games.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from fast_edge_model import FastPrediction, predict_fast
from mlb_api import GameRecord, fetch_pitcher_season_era
from team_tracker import LeagueState


WARMUP_GAMES = 180
REFIT_EVERY = 25


@dataclass
class TrainingExample:
    features: list[float]
    label: int


def _safe_era(game: GameRecord, pitcher_id: int | None) -> float:
    if not pitcher_id:
        return 4.35
    try:
        return fetch_pitcher_season_era(pitcher_id, game.game_date.year)
    except Exception:
        return 4.35


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def feature_row(game: GameRecord, league: LeagueState) -> list[float]:
    home = league.team(game.home_team_id)
    away = league.team(game.away_team_id)
    elo_probability = league.predict_home_win_probability(game.home_team_id, game.away_team_id)
    home_era = _safe_era(game, game.home_pitcher_id)
    away_era = _safe_era(game, game.away_pitcher_id)

    return [
        elo_probability,
        home.win_pct(),
        away.win_pct(),
        home.win_pct(10),
        away.win_pct(10),
        _clip(home.run_differential(), -5.0, 5.0),
        _clip(away.run_differential(), -5.0, 5.0),
        _clip(home.run_differential(10), -6.0, 6.0),
        _clip(away.run_differential(10), -6.0, 6.0),
        _clip(home.rest_days(game.game_date), 0.0, 7.0),
        _clip(away.rest_days(game.game_date), 0.0, 7.0),
        _clip(home.avg_runs_scored(10), 1.0, 9.0),
        _clip(away.avg_runs_scored(10), 1.0, 9.0),
        _clip(home.avg_runs_allowed(10), 1.0, 9.0),
        _clip(away.avg_runs_allowed(10), 1.0, 9.0),
        _clip(home_era, 1.5, 8.5),
        _clip(away_era, 1.5, 8.5),
        _clip(away_era - home_era, -5.0, 5.0),
    ]


def confidence_for(pick_probability: float) -> str:
    if pick_probability >= 0.65:
        return "Elite"
    if pick_probability >= 0.60:
        return "High"
    if pick_probability >= 0.56:
        return "Medium"
    return "Low"


def calibrate_public_probability(home_probability: float) -> float:
    """Keep public probabilities in a realistic pregame range."""
    return float(np.clip(home_probability, 0.30, 0.70))


def build_model() -> Pipeline:
    return Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    C=0.35,
                    class_weight="balanced",
                    max_iter=1000,
                    solver="liblinear",
                ),
            ),
        ]
    )


def _clean_matrix(matrix: np.ndarray) -> np.ndarray:
    matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)
    return np.clip(matrix, -100.0, 100.0)


def fit_model(examples: list[TrainingExample]) -> Pipeline | None:
    if len(examples) < WARMUP_GAMES:
        return None

    y = np.array([example.label for example in examples], dtype=int)
    if len(set(y.tolist())) < 2:
        return None

    x = _clean_matrix(np.array([example.features for example in examples], dtype=float))
    model = build_model()
    model.fit(x, y)
    return model


def predict_with_model(game: GameRecord, league: LeagueState, model: Pipeline | None) -> FastPrediction:
    if model is None:
        return predict_fast(game, league)

    x = _clean_matrix(np.array([feature_row(game, league)], dtype=float))
    trained_probability = float(model.predict_proba(x)[0, 1])
    form_probability = predict_fast(game, league).home_probability
    home_probability = calibrate_public_probability((trained_probability * 0.60) + (form_probability * 0.40))
    away_probability = 1.0 - home_probability
    predicted_home = home_probability >= away_probability
    pick_probability = max(home_probability, away_probability)

    return FastPrediction(
        home_probability=home_probability,
        away_probability=away_probability,
        predicted_home=predicted_home,
        pick_probability=pick_probability,
        confidence=confidence_for(pick_probability),
        notes=[
            "Trained on prior games only using walk-forward features",
            "Blends trained logistic output with current form, Elo, run differential, rest, scoring profile, and starter ERA",
            "Probability is capped to a realistic pregame range",
        ],
    )
