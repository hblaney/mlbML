"""Full 1000+ feature walk-forward model: registry + injuries + Statcast + robust blend."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from context import FeatureContext
from fast_edge_model import FastPrediction
from feature_registry import zero_statcast_feature_map
from features import build_feature_map, build_feature_vector
from historical_odds import HistoricalOddsStore
from injuries_provider import injury_counts_for_game
from mlb_api import GameRecord, fetch_pitcher_season_era
from park_factors import park_for_team
from robust_blend import robust_home_probability
from statcast_provider import StatcastTeamCache
from team_stats_provider import team_stats_as_of
from team_tracker import LeagueState
from trained_edge_model import (
    CURRENT_SEASON_SAMPLE_WEIGHT,
    PRIOR_SEASON_SAMPLE_WEIGHT,
    REFIT_EVERY,
    WARMUP_GAMES,
    confidence_for,
)
from weather import cached_historical_weather_or_default, fetch_historical_weather, fetch_weather

MODEL_VERSION = "daily-auto-v3.0-full-registry"


@dataclass
class TrainingExample:
    features: list[float]
    label: int


def _starter_eras(game: GameRecord) -> tuple[float, float]:
    home_era = 4.35
    away_era = 4.35
    if game.home_pitcher_id:
        try:
            home_era = fetch_pitcher_season_era(game.home_pitcher_id, game.game_date.year)
        except Exception:
            pass
    if game.away_pitcher_id:
        try:
            away_era = fetch_pitcher_season_era(game.away_pitcher_id, game.game_date.year)
        except Exception:
            pass
    return home_era, away_era


def _game_weather(game: GameRecord):
    try:
        if game.game_date < date.today() or game.is_final:
            return cached_historical_weather_or_default(game.home_team_id, game.game_datetime_iso)
        return fetch_weather(game.home_team_id, game.game_datetime_iso)
    except Exception:
        return cached_historical_weather_or_default(game.home_team_id, game.game_datetime_iso)


class FullRegistryFeatureBuilder:
    def __init__(self, team_abbr: dict[int, str]) -> None:
        self.team_abbr = team_abbr
        self.odds = HistoricalOddsStore()
        self.statcast = StatcastTeamCache()
        self._statcast_years: set[int] = set()

    def ensure_statcast_year(self, year: int) -> None:
        if year in self._statcast_years:
            return
        self.statcast.preload_season(year)
        self._statcast_years.add(year)

    def context_for_game(
        self,
        game: GameRecord,
        league: LeagueState,
        *,
        include_statcast: bool = True,
    ) -> FeatureContext:
        park = park_for_team(game.home_team_id)
        game_dt = datetime.fromisoformat(game.game_datetime_iso.replace("Z", "+00:00"))
        home_stats = team_stats_as_of(game.home_team_id, game.game_date)
        away_stats = team_stats_as_of(game.away_team_id, game.game_date)
        away_abbr = self.team_abbr.get(game.away_team_id, "")
        home_abbr = self.team_abbr.get(game.home_team_id, "")
        market = self.odds.for_game(game.game_date.isoformat(), away_abbr, home_abbr)
        weather = cached_historical_weather_or_default(game.home_team_id, game.game_datetime_iso)
        if game.game_date >= date.today() and not game.is_final:
            weather = _game_weather(game)
        home_injuries, away_injuries = injury_counts_for_game(
            game.home_team_id,
            game.away_team_id,
            snapshot_date=game.game_date,
        )
        if include_statcast and game.game_date.year >= 2015:
            self.ensure_statcast_year(game.game_date.year)
            statcast_features = self.statcast.feature_map(home_abbr, away_abbr, game.game_date)
        else:
            statcast_features = zero_statcast_feature_map()
        return FeatureContext(
            market=market,
            weather=weather,
            park=park,
            home_stats=home_stats,
            away_stats=away_stats,
            game_hour_utc=float(game_dt.hour),
            is_day_game=game_dt.hour < 22,
            home_injury_count=float(home_injuries),
            away_injury_count=float(away_injuries),
            statcast_features=statcast_features,
        )

    def feature_row(
        self,
        game: GameRecord,
        league: LeagueState,
        *,
        include_statcast: bool = True,
    ) -> list[float]:
        home = league.team(game.home_team_id)
        away = league.team(game.away_team_id)
        home_era, away_era = _starter_eras(game)
        context = self.context_for_game(game, league, include_statcast=include_statcast)
        return build_feature_vector(home, away, game.game_date, home_era, away_era, context)

    def feature_map(
        self,
        game: GameRecord,
        league: LeagueState,
        *,
        include_statcast: bool = True,
    ) -> dict[str, float]:
        home = league.team(game.home_team_id)
        away = league.team(game.away_team_id)
        home_era, away_era = _starter_eras(game)
        context = self.context_for_game(game, league, include_statcast=include_statcast)
        return build_feature_map(home, away, game.game_date, home_era, away_era, context)


def build_model() -> Pipeline:
    return Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "model",
                HistGradientBoostingClassifier(
                    max_depth=5,
                    learning_rate=0.04,
                    max_iter=180,
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


def predict_with_model(
    game: GameRecord,
    league: LeagueState,
    model: Pipeline | None,
    builder: FullRegistryFeatureBuilder,
    *,
    include_statcast: bool = True,
) -> FastPrediction:
    if model is None:
        from fast_edge_model import predict_fast

        return predict_fast(game, league)

    feature_map = builder.feature_map(game, league, include_statcast=include_statcast)
    x = _clean_matrix(np.array([builder.feature_row(game, league, include_statcast=include_statcast)], dtype=float))
    trained_probability = float(model.predict_proba(x)[0, 1])
    home_probability = robust_home_probability(trained_probability, feature_map)
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
            "Full registry model with injuries, Statcast rolling, market, weather, and robust signal blend",
            f"Feature count: {len(feature_map)}",
        ],
    )


def feature_row(game: GameRecord, league: LeagueState, builder: FullRegistryFeatureBuilder) -> list[float]:
    return builder.feature_row(game, league)
