"""Trained lightweight MLB predictor for page-load daily boards.

The full research model can be slow because it pulls many external features.
This model is designed to be fast, chronological, and auditable: features are
built only from information available before first pitch, then a calibrated
logistic model is trained on prior games.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple
from datetime import date, datetime

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.pipeline import Pipeline

from fast_edge_model import FastPrediction, predict_fast
from mlb_api import GameRecord, fetch_pitcher_recent_era, load_team_abbreviations
from pitcher_stats_provider import pitcher_stats_as_of
from park_factors import park_for_team
from statcast_provider import StatcastTeamCache, statcast_feature_vector
from team_stats_provider import team_stats_as_of
from team_tracker import LeagueState
from probability_calibration import apply_display_calibration, confidence_from_display
from weather import cached_historical_weather_or_default, fetch_weather


WARMUP_GAMES = 180
# ~one MLB slate — adapt to recent baseball, not a month-old fit.
REFIT_EVERY = 10
TRAINED_MODEL_WEIGHT = 1.00
PRIOR_SEASON_SAMPLE_WEIGHT = 0.45
CURRENT_SEASON_SAMPLE_WEIGHT = 1.60
RECENCY_DAYS_HOT = 14
RECENCY_DAYS_WARM = 35
# Upweight the last two weeks hard — last-100 collapse was the live failure.
RECENCY_MULTIPLIER_HOT = 1.85
RECENCY_MULTIPLIER_WARM = 1.30


def recency_sample_weight(game_date: date, as_of: date, base: float) -> float:
    """Upweight recent current-season games relative to the prediction as_of date."""
    days = max(0, (as_of - game_date).days)
    if days <= RECENCY_DAYS_HOT:
        return base * RECENCY_MULTIPLIER_HOT
    if days <= RECENCY_DAYS_WARM:
        return base * RECENCY_MULTIPLIER_WARM
    return base


def fit_weights_for_as_of(
    game_dates: list[date],
    base_weights: list[float],
    as_of: date,
) -> list[float]:
    """Recompute sample weights for a fit anchored at as_of (walk-forward / daily)."""
    return [
        recency_sample_weight(gd, as_of, base) if base >= CURRENT_SEASON_SAMPLE_WEIGHT - 1e-9 else base
        for gd, base in zip(game_dates, base_weights)
    ]
# Model-only publish (Jun 2026 v3.9): zero blend beats 6/10% on season accuracy (+0.8pp
# to 60.0%) and last-100 AUC (0.559). Market no-vig is still used for model_edge and
# the market_agrees confidence gate — not for pulling the displayed probability.
MARKET_BLEND_WEIGHT = 0.0
MARKET_BLEND_WEIGHT_COIN_FLIP = 0.0
MARKET_BLEND_EDGE_FULL_MODEL = 0.12
MARKET_BLEND_EDGE_COIN_FLIP = 0.04
PUBLIC_CONFIDENCE_SHARPENING = 0.8
PUBLIC_CONFIDENCE_SHARPENING_STRONG = 1.0
PUBLIC_PROBABILITY_CAP = 0.72
PUBLIC_PROBABILITY_CAP_STRONG = 0.78
# Retired Jun 2026: the ±12pt market clamp fixed weak-home overrating but crushed
# discrimination (last-100 published AUC 0.56). High/Elite now require era/form gates.
MAX_MARKET_DISAGREEMENT = 0.12  # kept for tests; no longer applied in final_public_probabilities
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
    return _safe_pitcher_stats(game, pitcher_id)["era"]


def _safe_pitcher_stats(game: GameRecord, pitcher_id: int | None) -> dict[str, float]:
    # Point-in-time line (current-season-to-date shrunk toward the prior season).
    # NEVER the full final-season totals — that was lookahead leakage in the
    # model's most important feature (starter ERA differential).
    try:
        return pitcher_stats_as_of(pitcher_id, game.game_date)
    except Exception:
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
        # Pythagorean win expectancy — more stable than raw W-L
        _clip(home.pythagorean_win_pct(), 0.25, 0.75),
        _clip(away.pythagorean_win_pct(), 0.25, 0.75),
        _clip(home.pythagorean_win_pct() - away.pythagorean_win_pct(), -0.30, 0.30),
        _clip(home.pythagorean_win_pct(30) - away.pythagorean_win_pct(30), -0.30, 0.30),
        # Home/away splits — team performance at this venue type
        _clip(home.home_win_pct(), 0.20, 0.80),
        _clip(away.away_win_pct(), 0.20, 0.80),
        _clip(home.home_win_pct() - away.away_win_pct(), -0.40, 0.40),
        # Exponentially weighted recent scoring
        _clip(home.avg_runs_scored_recent(7) - away.avg_runs_scored_recent(7), -4.0, 4.0),
        _clip(home.avg_runs_scored_recent(5) - away.avg_runs_allowed(5), -4.0, 4.0),
        _clip(away.avg_runs_scored_recent(5) - home.avg_runs_allowed(5), -4.0, 4.0),
        # 5-game win pct delta (tighter window for hot/cold streaks)
        _clip(home.win_pct(5) - away.win_pct(5), -1.0, 1.0),
        # season run differential vs opponent (context-free)
        _clip(home.run_differential() - away.run_differential(), -3.0, 3.0),
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
    home_pvo = league.pitcher_vs_opponent_features(game.home_pitcher_id, game.away_team_id, game.game_date)
    away_pvo = league.pitcher_vs_opponent_features(game.away_pitcher_id, game.home_team_id, game.game_date)
    features.extend(
        [
            _clip(home_pvo[0], 1.5, 9.0),
            _clip(home_pvo[1], 0.0, 1.0),
            _clip(away_pvo[0], 1.5, 9.0),
            _clip(away_pvo[1], 0.0, 1.0),
            _clip(away_pvo[0] - home_pvo[0], -5.0, 5.0),
        ]
    )
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


def public_confidence_for(
    pick_probability: float,
    *,
    market_agrees: bool | None = None,
    model_edge: float = 0.0,
    starter_certain: bool = True,
    market_available: bool = True,
    raw_pick: float = 0.0,
    era_diff: float = 0.0,
    form_edge: float = 0.0,
) -> str:
    """Accountable confidence on 60–90% display scale (walk-forward calibrated).

    Era diff and form edge are the two strongest predictors of whether a High/Elite
    pick actually wins (season walk-forward: wins avg era_diff=3.5 vs losses=2.4).
    """
    return confidence_from_display(
        pick_probability,
        model_edge=model_edge,
        starter_certain=starter_certain,
        market_available=market_available,
        market_agrees=market_agrees,
        raw_pick=raw_pick,
        era_diff=era_diff,
        form_edge=form_edge,
    )


class PublicPickResult(NamedTuple):
    home_probability: float
    away_probability: float
    pick_probability: float
    raw_pick_probability: float
    confidence: str
    market_agrees: bool | None
    model_edge: float


def final_public_probabilities(
    prediction: "FastPrediction",
    *,
    market_home: float | None = None,
    market_away: float | None = None,
    starter_certain: bool = True,
    era_diff: float = 0.0,
    form_edge: float = 0.0,
) -> PublicPickResult:
    """Publish GBM win% via market residual when odds exist; raw model otherwise.

    V5: P(home) = market + α × (model − market). Markets are the strongest MLB prior;
    the residual keeps the feature model when it disagrees with real edge. Missing odds
    fall back to the raw GBM + era/form confidence gates (no invented prices).
    """
    from v3_market_residual import publish_v3

    raw_home = float(prediction.home_probability)
    raw_pick = max(raw_home, 1.0 - raw_home)

    if market_home is not None and market_away is not None:
        v3 = publish_v3(
            raw_home,
            market_home=market_home,
            market_away=market_away,
            starter_certain=starter_certain,
        )
        return PublicPickResult(
            home_probability=v3.home_probability,
            away_probability=v3.away_probability,
            pick_probability=v3.pick_probability,
            raw_pick_probability=v3.raw_pick_probability,
            confidence=v3.confidence,
            market_agrees=v3.market_agrees,
            model_edge=v3.model_edge,
        )

    home_probability = calibrate_public_probability(raw_home)
    away_probability = 1.0 - home_probability
    pick_probability = max(home_probability, away_probability)
    confidence = public_confidence_for(
        pick_probability,
        market_agrees=None,
        model_edge=0.0,
        starter_certain=starter_certain,
        market_available=False,
        raw_pick=raw_pick,
        era_diff=era_diff,
        form_edge=form_edge,
    )
    return PublicPickResult(
        home_probability=round(home_probability, 4),
        away_probability=round(away_probability, 4),
        pick_probability=round(pick_probability, 4),
        raw_pick_probability=round(pick_probability, 4),
        confidence=confidence,
        market_agrees=None,
        model_edge=0.0,
    )


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
    return float(np.clip(home_probability, 0.30, PUBLIC_PROBABILITY_CAP_STRONG))


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


def sharpen_public_probability(home_probability: float, *, strong: bool = False) -> float:
    """Strong picks (model+market agree) keep full separation; coin flips stay soft."""
    if abs(home_probability - 0.5) < 0.05:
        return home_probability
    factor = PUBLIC_CONFIDENCE_SHARPENING_STRONG if strong else PUBLIC_CONFIDENCE_SHARPENING
    cap = PUBLIC_PROBABILITY_CAP_STRONG if strong else PUBLIC_PROBABILITY_CAP
    if home_probability >= 0.5:
        sharpened = 0.5 + ((home_probability - 0.5) * factor)
    else:
        sharpened = 0.5 - ((0.5 - home_probability) * factor)
    return float(np.clip(sharpened, 1 - cap, cap))


def build_model() -> Pipeline:
    # Shallow depth-2 boosting (reverted from the v2.14 HistGBM, which overfit and
    # lost out-of-sample discrimination: same-game internal AUC fell 0.577 -> 0.551).
    # Depth-2 stumps generalize far better on this noisy, ~3k-game signal.
    # Jun 2026 v4.2: 104 trees @ lr=0.043 — accuracy-forward (season 60.3%, last-250
    # 62.0%, last-100 51%). Beats v4.1 on forward pick accuracy; H/E 78.4% vs 80.8%.
    # REFIT_EVERY=30 validated best (more frequent refit regresses recent windows).
    return Pipeline(
        [
            (
                "model",
                GradientBoostingClassifier(
                    n_estimators=104,
                    learning_rate=0.043,
                    max_depth=2,
                    subsample=0.90,
                    random_state=42,
                ),
            ),
        ]
    )


FULL_FEATURE_WIDTH = 218


# Frozen feature selection. feature_row() emits 218 columns but a walk-forward
# importance prune (scripts/model/feature_importance.py) showed ~106 of them carry
# <0.1% importance and only add noise. Keeping the top-35 by importance is best on
# out-of-sample calibration (top-35 ECE 0.029 vs full 0.045) at equal AUC.
# These indices are frozen so fit and predict mask identically.
#
# RE-RANKED Jun 2026 after the starting-pitcher leakage fix (pitcher_stats_provider).
# With full-season pitcher stats removed, the model correctly leans on the
# leakage-safe recent-form features: sp_recent_era_diff is now the #1 feature
# (33.5% importance) and the recent-ERA *trend* columns rank #2/#3 — so the prior
# (leaked) selection that dropped them is no longer optimal. This set adds
# home_sp_recent_era / home_sp_era_trend / away_sp_era_trend and drops the leaked
# era_away_minus_home and home_era.
# Names: elo_prob, away_winpct, home_era, away_ops, away_obp, away_rpg, away_hrpg,
# away_krate, home_bbrate, away_bbrate, away_krate, home_sp_whip(*), home_off_vs_away_pit,
# home_sp_k9, away_sp_k9, home_sp_bb9, away_sp_bb9, home_sp_opsa, pyth_diff, pyth30_diff,
# home_roll21_allowed, home_roll30_rundiff, away_roll5_rundiff, away_roll7_rundiff,
# away_roll30_winpct, away_roll30_allowed, away_roll30_net, mu10_rundiff_diff,
# mu10_net, mu30_home_off_edge, mu30_away_off_edge, home_sp_recent_era,
# home_sp_era_trend, away_sp_era_trend, sp_recent_era_diff
# Jun 2026 v4.4: boxscore IP/ER for pitcher-vs-opponent ERA (features 213/215).
# v4.3 set below; walk-forward validated after boxscore prefetch.
SELECTED_FEATURE_INDICES: list[int] = sorted([
    0, 2, 16, 19, 21, 26, 28, 29, 30, 34, 39, 43, 46, 49, 50, 51, 52, 56, 57, 66, 67,
    122, 125, 135, 140, 159, 162, 163, 180, 183, 196, 197, 202, 204, 205, 206,
    213, 215,
])


def _clean_matrix(matrix: np.ndarray) -> np.ndarray:
    matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)
    return np.clip(matrix, -100.0, 100.0)


def _select_features(matrix: np.ndarray) -> np.ndarray:
    """Mask a full feature matrix down to the frozen top-35 signal columns.

    No-op if the matrix already has the pruned width (so callers can pass either)."""
    if matrix.ndim != 2 or matrix.shape[1] != FULL_FEATURE_WIDTH:
        return matrix
    return matrix[:, SELECTED_FEATURE_INDICES]


def fit_model(
    examples: list[TrainingExample],
    sample_weights: list[float] | None = None,
) -> Pipeline | None:
    if len(examples) < WARMUP_GAMES:
        return None

    y = np.array([example.label for example in examples], dtype=int)
    if len(set(y.tolist())) < 2:
        return None

    x = _select_features(_clean_matrix(np.array([example.features for example in examples], dtype=float)))
    model = build_model()
    if sample_weights is not None:
        model.fit(x, y, model__sample_weight=np.array(sample_weights, dtype=float))
    else:
        model.fit(x, y)
    return model


def predict_with_model(game: GameRecord, league: LeagueState, model: Pipeline | None) -> FastPrediction:
    if model is None:
        return predict_fast(game, league)

    x = _select_features(_clean_matrix(np.array([feature_row(game, league)], dtype=float)))
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
