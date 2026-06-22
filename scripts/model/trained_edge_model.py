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
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.pipeline import Pipeline

from fast_edge_model import FastPrediction, predict_fast
from mlb_api import GameRecord, fetch_pitcher_recent_era, fetch_pitcher_season_era, fetch_pitcher_season_stats, load_team_abbreviations
from park_factors import park_for_team
from statcast_provider import StatcastTeamCache, statcast_feature_vector
from team_stats_provider import team_stats_as_of
from team_tracker import LeagueState
from weather import cached_historical_weather_or_default, fetch_weather


WARMUP_GAMES = 180
REFIT_EVERY = 60
TRAINED_MODEL_WEIGHT = 1.00
PRIOR_SEASON_SAMPLE_WEIGHT = 0.60
CURRENT_SEASON_SAMPLE_WEIGHT = 1.25
# Season walk-forward best: 0.09 (61.21%). 0.10 OK alone; 0.10 + series-in-wf regressed.
MARKET_BLEND_WEIGHT = 0.09
# When internal edge is tiny, lean harder on no-vig market (Jun 2026 audit: 50-55% picks hit 44%).
MARKET_BLEND_WEIGHT_COIN_FLIP = 0.30
MARKET_BLEND_EDGE_FULL_MODEL = 0.12
MARKET_BLEND_EDGE_COIN_FLIP = 0.04
PUBLIC_CONFIDENCE_SHARPENING = 0.8
PUBLIC_PROBABILITY_CAP = 0.70
# Starter experience thresholds — learned via features, not post-hoc nudges.
VETERAN_STARTER_IP_MIN = 80.0
ROOKIE_STARTER_IP_MAX = 35.0

_STATCAST_CACHE: StatcastTeamCache | None = None
_TEAM_ABBR: dict[int, str] | None = None


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


def _team_abbreviations() -> dict[int, str]:
    global _TEAM_ABBR
    if _TEAM_ABBR is None:
        _TEAM_ABBR = load_team_abbreviations()
    return _TEAM_ABBR


def statcast_cache() -> StatcastTeamCache:
    global _STATCAST_CACHE
    if _STATCAST_CACHE is None:
        _STATCAST_CACHE = StatcastTeamCache()
    return _STATCAST_CACHE


def preload_statcast_years(years: set[int]) -> None:
    for year in sorted(years):
        if year >= 2015:
            statcast_cache().preload_season(year)


def statcast_features_for_game(game: GameRecord) -> list[float]:
    from feature_registry import zero_statcast_feature_map

    zeros = list(zero_statcast_feature_map().values())
    if game.game_date.year < 2015:
        return zeros
    abbr = _team_abbreviations()
    home = abbr.get(game.home_team_id, "")
    away = abbr.get(game.away_team_id, "")
    if not home or not away:
        return zeros
    try:
        return statcast_feature_vector(statcast_cache(), home, away, game.game_date)
    except Exception:
        return zeros


def feature_row(game: GameRecord, league: LeagueState, *, include_statcast: bool = False) -> list[float]:
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
    features.extend(_starter_experience_features(game))
    features.extend(league.head_to_head_features(game.home_team_id, game.away_team_id, game.game_date))
    if include_statcast:
        features.extend(statcast_features_for_game(game))
    return features


def _starter_experience_features(game: GameRecord) -> list[float]:
    """Veteran-vs-thin starter matchup — trained in the GBM, not applied after the fact."""
    home_pitcher = _safe_pitcher_stats(game, game.home_pitcher_id)
    away_pitcher = _safe_pitcher_stats(game, game.away_pitcher_id)
    home_vet = 1.0 if home_pitcher["innings_pitched"] >= VETERAN_STARTER_IP_MIN else 0.0
    away_vet = 1.0 if away_pitcher["innings_pitched"] >= VETERAN_STARTER_IP_MIN else 0.0
    home_thin = 1.0 if home_pitcher["innings_pitched"] <= ROOKIE_STARTER_IP_MAX else 0.0
    away_thin = 1.0 if away_pitcher["innings_pitched"] <= ROOKIE_STARTER_IP_MAX else 0.0
    era_edge_home = _clip(home_pitcher["era"] - away_pitcher["era"], -4.0, 4.0)
    era_edge_away = _clip(away_pitcher["era"] - home_pitcher["era"], -4.0, 4.0)
    vet_home_vs_thin_away = home_vet * away_thin * max(0.0, era_edge_away)
    vet_away_vs_thin_home = away_vet * home_thin * max(0.0, era_edge_home)

    try:
        home_recent_era = fetch_pitcher_recent_era(game.home_pitcher_id, game.game_date) if game.home_pitcher_id else home_pitcher["era"]
    except Exception:
        home_recent_era = home_pitcher["era"]
    try:
        away_recent_era = fetch_pitcher_recent_era(game.away_pitcher_id, game.game_date) if game.away_pitcher_id else away_pitcher["era"]
    except Exception:
        away_recent_era = away_pitcher["era"]

    return [
        vet_home_vs_thin_away,
        vet_away_vs_thin_home,
        _clip(home_pitcher["innings_pitched"] - away_pitcher["innings_pitched"], -150.0, 150.0) / 150.0,
        _clip(home_recent_era, 1.5, 9.0),
        _clip(away_recent_era, 1.5, 9.0),
        _clip(home_recent_era - home_pitcher["era"], -4.0, 4.0),
        _clip(away_recent_era - away_pitcher["era"], -4.0, 4.0),
        _clip(home_recent_era - away_recent_era, -5.0, 5.0),
    ]


def public_confidence_for(pick_probability: float) -> str:
    """Confidence label always matches the single displayed pick probability."""
    if pick_probability >= 0.70:
        return "High"
    if pick_probability >= 0.55:
        return "Medium"
    return "Low"


def final_public_probabilities(
    prediction: "FastPrediction",
    *,
    market_home: float | None = None,
    market_away: float | None = None,
) -> tuple[float, float, float, str]:
    """One pipeline for live board + walk-forward: GBM output → market blend → calibration → confidence."""
    home_probability = prediction.home_probability
    away_probability = prediction.away_probability
    if market_home is not None and market_away is not None:
        home_probability = blend_with_market(home_probability, market_home)
        away_probability = blend_with_market(away_probability, market_away)
        total = home_probability + away_probability
        if total > 0:
            home_probability /= total
            away_probability /= total
    home_probability = sharpen_public_probability(home_probability)
    away_probability = 1.0 - home_probability
    pick_probability = max(home_probability, away_probability)

    # Low-edge model vs market disagreements: defer to market (Jun 2026 live audit).
    if (
        market_home is not None
        and market_away is not None
        and pick_probability < 0.56
    ):
        market_pick_home = market_home >= market_away
        model_pick_home = home_probability >= away_probability
        if market_pick_home != model_pick_home:
            total = market_home + market_away
            if total > 0:
                home_probability = market_home / total
                away_probability = market_away / total
            home_probability = sharpen_public_probability(home_probability)
            away_probability = 1.0 - home_probability
            pick_probability = max(home_probability, away_probability)

    return home_probability, away_probability, pick_probability, public_confidence_for(pick_probability)


_CONFIDENCE_ORDER = ("Low", "Medium", "High", "Elite")


def cap_confidence(level: str, max_level: str) -> str:
    return _CONFIDENCE_ORDER[min(_CONFIDENCE_ORDER.index(level), _CONFIDENCE_ORDER.index(max_level))]


def confidence_for(
    pick_probability: float,
    market_backed: bool = False,
    internal_pick_probability: float | None = None,
    internal_agrees: bool = True,
) -> str:
    """Legacy alias — confidence always matches the unified final pick probability."""
    return public_confidence_for(pick_probability)


def calibrate_public_probability(home_probability: float) -> float:
    """Keep public probabilities in a realistic pregame range."""
    return float(np.clip(home_probability, 0.30, 0.70))


def market_blend_weight(internal_home: float) -> float:
    """Use heavier market weight when the model has almost no edge."""
    edge = abs(internal_home - 0.5)
    if edge >= MARKET_BLEND_EDGE_FULL_MODEL:
        return MARKET_BLEND_WEIGHT
    if edge <= MARKET_BLEND_EDGE_COIN_FLIP:
        return MARKET_BLEND_WEIGHT_COIN_FLIP
    span = MARKET_BLEND_EDGE_FULL_MODEL - MARKET_BLEND_EDGE_COIN_FLIP
    t = (edge - MARKET_BLEND_EDGE_COIN_FLIP) / span
    return MARKET_BLEND_WEIGHT_COIN_FLIP + t * (MARKET_BLEND_WEIGHT - MARKET_BLEND_WEIGHT_COIN_FLIP)


def blend_with_market(internal_home: float, market_home: float) -> float:
    """Blend internal model probability with no-vig market consensus."""
    weight = market_blend_weight(internal_home)
    return internal_home * (1.0 - weight) + market_home * weight


def sharpen_public_probability(home_probability: float) -> float:
    """Make validated public picks more assertive without changing the side."""
    if abs(home_probability - 0.5) < 0.05:
        return home_probability
    if home_probability >= 0.5:
        sharpened = 0.5 + ((home_probability - 0.5) * PUBLIC_CONFIDENCE_SHARPENING)
    else:
        sharpened = 0.5 - ((0.5 - home_probability) * PUBLIC_CONFIDENCE_SHARPENING)
    return float(np.clip(sharpened, 1 - PUBLIC_PROBABILITY_CAP, PUBLIC_PROBABILITY_CAP))


def build_model() -> Pipeline:
    return Pipeline(
        [
            (
                "model",
                GradientBoostingClassifier(
                    n_estimators=140,
                    learning_rate=0.035,
                    max_depth=1,
                    subsample=0.90,
                    random_state=42,
                ),
            ),
        ]
    )


def _clean_matrix(matrix: np.ndarray) -> np.ndarray:
    matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)
    return np.clip(matrix, -100.0, 100.0)


def fit_model(
    examples: list[TrainingExample],
    sample_weights: list[float] | None = None,
) -> Pipeline | None:
    if len(examples) < WARMUP_GAMES:
        return None

    y = np.array([example.label for example in examples], dtype=int)
    if len(set(y.tolist())) < 2:
        return None

    x = _clean_matrix(np.array([example.features for example in examples], dtype=float))
    model = build_model()
    if sample_weights is not None:
        model.fit(x, y, model__sample_weight=np.array(sample_weights, dtype=float))
    else:
        model.fit(x, y)
    return model


def predict_with_model(game: GameRecord, league: LeagueState, model: Pipeline | None) -> FastPrediction:
    if model is None:
        return predict_fast(game, league)

    x = _clean_matrix(np.array([feature_row(game, league)], dtype=float))
    trained_probability = float(model.predict_proba(x)[0, 1])
    form_probability = predict_fast(game, league).home_probability
    home_probability = calibrate_public_probability(
        (trained_probability * TRAINED_MODEL_WEIGHT) + (form_probability * (1.0 - TRAINED_MODEL_WEIGHT))
    )
    away_probability = 1.0 - home_probability
    predicted_home = home_probability >= away_probability
    pick_probability = max(home_probability, away_probability)

    return FastPrediction(
        home_probability=home_probability,
        away_probability=away_probability,
        predicted_home=predicted_home,
        pick_probability=pick_probability,
        confidence=public_confidence_for(pick_probability),
        notes=[
            "Trained on prior games only using walk-forward features",
            "Blends a frequently refit shallow gradient-boosting output with Elo, real team hitting/pitching stats, rolling Statcast contact quality, starter profile, rolling form, park, weather, timing, and matchup context",
            "Probability is capped to a realistic pregame range",
        ],
    )
