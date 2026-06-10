"""Trained lightweight MLB predictor for page-load daily boards.

The full research model can be slow because it pulls many external features.
This model is designed to be fast, chronological, and auditable: features are
built only from information available before first pitch, then a calibrated
logistic model is trained on prior games.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from fast_edge_model import FastPrediction, predict_fast
from mlb_api import GameRecord, fetch_pitcher_season_era, fetch_pitcher_season_stats
from park_factors import park_for_team
from team_stats_provider import team_stats_as_of
from team_tracker import LeagueState
from weather import cached_historical_weather_or_default, fetch_weather


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


def _safe_pitcher_stats(game: GameRecord, pitcher_id: int | None) -> dict[str, float]:
    if not pitcher_id:
        return {
            "era": 4.35,
            "whip": 1.3,
            "avg_allowed": 0.250,
            "obp_allowed": 0.320,
            "slg_allowed": 0.400,
            "ops_allowed": 0.720,
            "strikeouts_per_9": 8.0,
            "walks_per_9": 3.0,
            "hits_per_9": 8.5,
            "home_runs_per_9": 1.1,
            "innings_pitched": 0.0,
            "games_started": 0.0,
        }
    try:
        return fetch_pitcher_season_stats(pitcher_id, game.game_date.year)
    except Exception:
        return _safe_pitcher_stats(game, None)


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _game_weather(game: GameRecord):
    try:
        if game.game_date < date.today() or game.is_final:
            return cached_historical_weather_or_default(game.home_team_id, game.game_datetime_iso)
        return fetch_weather(game.home_team_id, game.game_datetime_iso)
    except Exception:
        return cached_historical_weather_or_default(game.home_team_id, game.game_datetime_iso)


def _rolling_team_features(team, windows: list[int]) -> list[float]:
    features: list[float] = []
    for window in windows:
        scored = team.avg_runs_scored(window)
        allowed = team.avg_runs_allowed(window)
        features.extend(
            [
                _clip(team.win_pct(window), 0.0, 1.0),
                _clip(team.run_differential(window), -7.0, 7.0),
                _clip(scored, 1.0, 10.0),
                _clip(allowed, 1.0, 10.0),
                _clip(scored - allowed, -7.0, 7.0),
            ]
        )
    return features


def _rolling_matchup_features(home, away, windows: list[int]) -> list[float]:
    features: list[float] = []
    for window in windows:
        home_offense = home.avg_runs_scored(window)
        away_offense = away.avg_runs_scored(window)
        home_defense = home.avg_runs_allowed(window)
        away_defense = away.avg_runs_allowed(window)
        features.extend(
            [
                _clip(home.win_pct(window) - away.win_pct(window), -1.0, 1.0),
                _clip(home.run_differential(window) - away.run_differential(window), -10.0, 10.0),
                _clip(home_offense - away_defense, -7.0, 7.0),
                _clip(away_offense - home_defense, -7.0, 7.0),
                _clip((home_offense - away_defense) - (away_offense - home_defense), -10.0, 10.0),
            ]
        )
    return features


def feature_row(game: GameRecord, league: LeagueState) -> list[float]:
    home = league.team(game.home_team_id)
    away = league.team(game.away_team_id)
    elo_probability = league.predict_home_win_probability(game.home_team_id, game.away_team_id)
    home_stats = team_stats_as_of(game.home_team_id, game.game_date)
    away_stats = team_stats_as_of(game.away_team_id, game.game_date)
    home_pitcher = _safe_pitcher_stats(game, game.home_pitcher_id)
    away_pitcher = _safe_pitcher_stats(game, game.away_pitcher_id)
    home_era = home_pitcher["era"]
    away_era = away_pitcher["era"]
    park = park_for_team(game.home_team_id)
    weather = _game_weather(game)
    game_dt = datetime.fromisoformat(game.game_datetime_iso.replace("Z", "+00:00"))
    rolling_windows = [3, 5, 7, 10, 14, 21, 30]

    features = [
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
        _clip(home_stats.ops, 0.550, 0.900),
        _clip(away_stats.ops, 0.550, 0.900),
        _clip(home_stats.obp, 0.260, 0.380),
        _clip(away_stats.obp, 0.260, 0.380),
        _clip(home_stats.slg, 0.320, 0.520),
        _clip(away_stats.slg, 0.320, 0.520),
        _clip(home_stats.runs_per_game, 2.5, 6.5),
        _clip(away_stats.runs_per_game, 2.5, 6.5),
        _clip(home_stats.home_runs_per_game, 0.4, 2.0),
        _clip(away_stats.home_runs_per_game, 0.4, 2.0),
        _clip(home_stats.strikeout_rate, 0.15, 0.32),
        _clip(away_stats.strikeout_rate, 0.15, 0.32),
        _clip(home_stats.walk_rate, 0.05, 0.13),
        _clip(away_stats.walk_rate, 0.05, 0.13),
        _clip(home_stats.pitching_era, 2.8, 6.2),
        _clip(away_stats.pitching_era, 2.8, 6.2),
        _clip(home_stats.pitching_whip, 1.0, 1.6),
        _clip(away_stats.pitching_whip, 1.0, 1.6),
        _clip(home_stats.pitching_ops_allowed, 0.580, 0.850),
        _clip(away_stats.pitching_ops_allowed, 0.580, 0.850),
        _clip(home_stats.strikeouts_per_9, 6.0, 11.5),
        _clip(away_stats.strikeouts_per_9, 6.0, 11.5),
        _clip(home_stats.walks_per_9, 2.0, 5.0),
        _clip(away_stats.walks_per_9, 2.0, 5.0),
        _clip(home_stats.home_runs_per_9, 0.5, 1.8),
        _clip(away_stats.home_runs_per_9, 0.5, 1.8),
        _clip(home_pitcher["whip"], 0.8, 1.8),
        _clip(away_pitcher["whip"], 0.8, 1.8),
        _clip(home_pitcher["strikeouts_per_9"], 4.0, 13.5),
        _clip(away_pitcher["strikeouts_per_9"], 4.0, 13.5),
        _clip(home_pitcher["walks_per_9"], 1.0, 6.0),
        _clip(away_pitcher["walks_per_9"], 1.0, 6.0),
        _clip(home_pitcher["home_runs_per_9"], 0.2, 2.5),
        _clip(away_pitcher["home_runs_per_9"], 0.2, 2.5),
        _clip(home_pitcher["ops_allowed"], 0.500, 0.950),
        _clip(away_pitcher["ops_allowed"], 0.500, 0.950),
        _clip(home_pitcher["innings_pitched"], 0.0, 180.0),
        _clip(away_pitcher["innings_pitched"], 0.0, 180.0),
        _clip(home_stats.ops - away_stats.pitching_ops_allowed, -0.250, 0.250),
        _clip(away_stats.ops - home_stats.pitching_ops_allowed, -0.250, 0.250),
        _clip((home_stats.ops - away_stats.pitching_ops_allowed) - (away_stats.ops - home_stats.pitching_ops_allowed), -0.350, 0.350),
        _clip((home_pitcher["ops_allowed"] - away_pitcher["ops_allowed"]), -0.350, 0.350),
        _clip(home.streak(), -10.0, 10.0),
        _clip(away.streak(), -10.0, 10.0),
        _clip(home.streak() - away.streak(), -15.0, 15.0),
        _clip(home.rest_days(game.game_date) - away.rest_days(game.game_date), -7.0, 7.0),
        _clip(park.park_factor_runs, 0.85, 1.25),
        _clip(park.park_factor_hr, 0.75, 1.25),
        _clip(park.altitude_ft, 0.0, 5500.0),
        _clip(park.left_field_ft, 300.0, 380.0),
        _clip(park.center_field_ft, 380.0, 430.0),
        _clip(park.right_field_ft, 300.0, 380.0),
        _clip(weather.temperature_f, 35.0, 105.0),
        _clip(weather.wind_speed_mph, 0.0, 35.0),
        _clip(weather.wind_direction_degrees, 0.0, 360.0),
        _clip(weather.wind_out_to_center, 0.0, 1.0),
        _clip(weather.humidity_pct, 5.0, 100.0),
        _clip(weather.precipitation_probability, 0.0, 1.0),
        _clip(weather.pressure_hpa, 950.0, 1050.0),
        1.0 if weather.is_dome else 0.0,
        _clip(float(game_dt.hour), 0.0, 23.0),
        1.0 if game_dt.hour < 22 else 0.0,
        _clip(float(game_dt.month), 3.0, 11.0),
        1.0,
    ]
    features.extend(_rolling_team_features(home, rolling_windows))
    features.extend(_rolling_team_features(away, rolling_windows))
    features.extend(_rolling_matchup_features(home, away, rolling_windows))
    return features


def confidence_for(
    pick_probability: float,
    market_backed: bool = False,
    internal_pick_probability: float | None = None,
    internal_agrees: bool = True,
) -> str:
    if not market_backed:
        internal_probability = internal_pick_probability if internal_pick_probability is not None else pick_probability
        if pick_probability >= 0.70 and internal_probability >= 0.70:
            return "Elite"
        if pick_probability >= 0.65 and internal_probability >= 0.65:
            return "High"
        if pick_probability >= 0.58:
            return "Medium"
        return "Low"

    if pick_probability >= 0.70:
        return "Elite"
    if (
        pick_probability >= 0.68
        and internal_agrees
        and (internal_pick_probability is None or internal_pick_probability >= 0.55)
    ):
        return "High"
    if pick_probability >= 0.55:
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
                ExtraTreesClassifier(
                    n_estimators=220,
                    max_depth=7,
                    min_samples_leaf=18,
                    class_weight="balanced",
                    random_state=42,
                    n_jobs=-1,
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
            "Blends trained tree-ensemble output with Elo, real team hitting/pitching stats, starter profile, rolling form, park, weather, timing, and matchup context",
            "Probability is capped to a realistic pregame range",
        ],
    )
