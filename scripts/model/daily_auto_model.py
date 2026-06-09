"""Self-retraining daily model: trains through yesterday, predicts today.

Persists to disk so page loads only retrain when new final games exist.
Uses walk-forward logistic + Elo + real MLB stats, rolling form, park, and weather features.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from sklearn.pipeline import Pipeline

from fast_edge_model import FastPrediction
from mlb_api import GameRecord, load_or_fetch_games
from team_tracker import LeagueState
from trained_edge_model import (
    REFIT_EVERY,
    WARMUP_GAMES,
    TrainingExample,
    feature_row,
    fit_model,
    predict_with_model,
)

MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "model" / "daily_edge.pkl"
MODEL_VERSION = "daily-auto-v1.0"


@dataclass
class DailyModelBundle:
    trained_through: date
    league: LeagueState
    model: Pipeline
    model_version: str = MODEL_VERSION

    def predict(self, game: GameRecord) -> FastPrediction:
        prediction = predict_with_model(game, self.league, self.model)
        return FastPrediction(
            home_probability=prediction.home_probability,
            away_probability=prediction.away_probability,
            predicted_home=prediction.predicted_home,
            pick_probability=prediction.pick_probability,
            confidence=prediction.confidence,
            notes=[
                f"Retrained through {self.trained_through.isoformat()}",
                "Blended logistic + form model fit on prior games with stats, rolling form, weather, park, starter, and matchup features",
                "Retrains automatically when yesterday's final scores are new",
            ],
        )


def train_on_games(games: list[GameRecord]) -> DailyModelBundle:
    league = LeagueState()
    examples: list[TrainingExample] = []

    for game in games:
        examples.append(
            TrainingExample(features=feature_row(game, league), label=1 if game.home_won else 0)
        )
        league.apply_result(
            game.game_date,
            game.home_team_id,
            game.away_team_id,
            game.home_score,
            game.away_score,
        )

    model = fit_model(examples)
    if model is None:
        raise RuntimeError("Not enough games to train the daily model.")

    trained_through = games[-1].game_date if games else date.today() - timedelta(days=1)
    return DailyModelBundle(trained_through=trained_through, league=league, model=model)


def load_bundle() -> DailyModelBundle | None:
    if not MODEL_PATH.exists():
        return None
    try:
        with MODEL_PATH.open("rb") as handle:
            bundle = pickle.load(handle)
        if bundle.__dict__.get("model_version") != MODEL_VERSION:
            return None
        return bundle
    except Exception:
        return None


def save_bundle(bundle: DailyModelBundle) -> None:
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MODEL_PATH.open("wb") as handle:
        pickle.dump(bundle, handle)


def season_games_through(yesterday: date) -> list[GameRecord]:
    season_start = date(yesterday.year, 3, 20)
    if yesterday < season_start:
        season_start = date(yesterday.year - 1, 3, 20)
    return load_or_fetch_games(season_start, yesterday)


def ensure_trained_through(yesterday: date) -> DailyModelBundle:
    existing = load_bundle()
    if existing is not None and existing.trained_through >= yesterday:
        return existing

    games = season_games_through(yesterday)
    if not games:
        raise RuntimeError("No historical games available to train on.")

    bundle = train_on_games(games)
    bundle.trained_through = yesterday
    save_bundle(bundle)
    return bundle


def walk_forward_history(games: list[GameRecord], team_abbr: dict[int, str]) -> list[dict]:
    league = LeagueState()
    examples: list[TrainingExample] = []
    model: Pipeline | None = None
    last_fit_index = 0
    rows: list[dict] = []

    for index, game in enumerate(games):
        features = feature_row(game, league)

        if len(examples) >= WARMUP_GAMES and (model is None or index - last_fit_index >= REFIT_EVERY):
            model = fit_model(examples)
            last_fit_index = index

        if len(examples) >= WARMUP_GAMES and model is not None:
            prediction = predict_with_model(game, league, model)
            home_abbr = team_abbr.get(game.home_team_id, str(game.home_team_id))
            away_abbr = team_abbr.get(game.away_team_id, str(game.away_team_id))
            actual_winner = home_abbr if game.home_won else away_abbr
            predicted_winner = home_abbr if prediction.predicted_home else away_abbr

            rows.append(
                {
                    "gamePk": game.game_pk,
                    "date": game.game_date.isoformat(),
                    "startsAt": game.game_datetime_iso,
                    "home": home_abbr,
                    "away": away_abbr,
                    "probability": round(prediction.home_probability, 4),
                    "pickProbability": round(prediction.pick_probability, 4),
                    "confidence": prediction.confidence,
                    "predicted": predicted_winner,
                    "actual": actual_winner,
                    "correct": int(predicted_winner == actual_winner),
                    "modelVersion": MODEL_VERSION,
                }
            )

        examples.append(TrainingExample(features=features, label=1 if game.home_won else 0))
        league.apply_result(
            game.game_date,
            game.home_team_id,
            game.away_team_id,
            game.home_score,
            game.away_score,
        )

    return rows
