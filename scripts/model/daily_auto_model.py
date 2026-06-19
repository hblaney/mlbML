"""Self-retraining daily model: trains through yesterday, predicts today.

Persists to disk so page loads only retrain when new final games exist.
Uses a walk-forward gradient boosting model + Elo + real MLB stats, rolling form, park, and weather features.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from sklearn.pipeline import Pipeline

from fast_edge_model import FastPrediction
from historical_odds import HistoricalOddsStore
from mlb_api import GameRecord, load_or_fetch_games
from odds_provider import implied_probability
from team_tracker import LeagueState
from trained_edge_model import (
    CURRENT_SEASON_SAMPLE_WEIGHT,
    PRIOR_SEASON_SAMPLE_WEIGHT,
    REFIT_EVERY,
    WARMUP_GAMES,
    TrainingExample,
    feature_row,
    final_public_probabilities,
    fit_model,
    predict_with_model,
)

MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "model" / "daily_edge.pkl"
MODEL_VERSION = "daily-auto-v2.7-unified"
# Bump when the public probability pipeline changes (must match predictions.json).
PIPELINE_VERSION = "unified-public-v1"


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
                "Shallow gradient boosting trained on prior season (decayed) plus current season (boosted)",
                "Blends trained output with Elo/form at 85/15; light market anchor when odds are available",
                "Retrains automatically when yesterday's final scores are new",
            ],
        )


def _ingest_game(
    game: GameRecord,
    league: LeagueState,
    examples: list[TrainingExample],
    weights: list[float],
    weight: float,
) -> None:
    examples.append(TrainingExample(features=feature_row(game, league), label=1 if game.home_won else 0))
    weights.append(weight)
    league.apply_result(
        game.game_date,
        game.home_team_id,
        game.away_team_id,
        game.home_score,
        game.away_score,
    )


def train_on_games(
    games: list[GameRecord],
    prior_games: list[GameRecord] | None = None,
) -> DailyModelBundle:
    league = LeagueState()
    examples: list[TrainingExample] = []
    weights: list[float] = []

    for game in prior_games or []:
        _ingest_game(game, league, examples, weights, PRIOR_SEASON_SAMPLE_WEIGHT)

    for game in games:
        _ingest_game(game, league, examples, weights, CURRENT_SEASON_SAMPLE_WEIGHT)

    model = fit_model(examples, weights)
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


def prior_season_games(yesterday: date) -> list[GameRecord]:
    season_start = date(yesterday.year, 3, 20)
    if yesterday < season_start:
        return []
    return load_or_fetch_games(date(yesterday.year - 1, 3, 20), date(yesterday.year - 1, 10, 5))


def ensure_trained_through(yesterday: date) -> tuple[DailyModelBundle, bool]:
    existing = load_bundle()
    if existing is not None and existing.trained_through >= yesterday:
        return existing, False

    games = season_games_through(yesterday)
    if not games:
        raise RuntimeError("No historical games available to train on.")

    bundle = train_on_games(games, prior_games=prior_season_games(yesterday))
    bundle.trained_through = yesterday
    save_bundle(bundle)
    return bundle, True


def no_vig_market_probabilities(home_moneyline: int, away_moneyline: int) -> tuple[float, float] | None:
    home = implied_probability(home_moneyline)
    away = implied_probability(away_moneyline)
    total = home + away
    if total <= 0:
        return None
    return home / total, away / total


def walk_forward_history(
    games: list[GameRecord],
    team_abbr: dict[int, str],
    prior_games: list[GameRecord] | None = None,
) -> list[dict]:
    league = LeagueState()
    examples: list[TrainingExample] = []
    weights: list[float] = []
    model: Pipeline | None = None
    last_fit_index = -REFIT_EVERY
    rows: list[dict] = []
    odds = HistoricalOddsStore()

    for game in prior_games or []:
        _ingest_game(game, league, examples, weights, PRIOR_SEASON_SAMPLE_WEIGHT)

    for index, game in enumerate(games):
        features = feature_row(game, league)

        if len(examples) >= WARMUP_GAMES and (model is None or index - last_fit_index >= REFIT_EVERY):
            model = fit_model(examples, weights)
            last_fit_index = index

        if len(examples) >= WARMUP_GAMES and model is not None:
            prediction = predict_with_model(game, league, model)
            home_abbr = team_abbr.get(game.home_team_id, str(game.home_team_id))
            away_abbr = team_abbr.get(game.away_team_id, str(game.away_team_id))
            market = odds.for_game(game.game_date.isoformat(), away_abbr, home_abbr)
            odds_available = market.source_count > 0 and market.home_moneyline != 0 and market.away_moneyline != 0
            market_probs = (
                no_vig_market_probabilities(market.home_moneyline, market.away_moneyline)
                if odds_available
                else None
            )
            home_probability, away_probability, pick_probability, confidence = final_public_probabilities(
                prediction,
                market_home=market_probs[0] if market_probs else None,
                market_away=market_probs[1] if market_probs else None,
            )
            predicted_home = home_probability >= away_probability
            actual_winner = home_abbr if game.home_won else away_abbr
            predicted_winner = home_abbr if predicted_home else away_abbr

            rows.append(
                {
                    "gamePk": game.game_pk,
                    "date": game.game_date.isoformat(),
                    "startsAt": game.game_datetime_iso,
                    "home": home_abbr,
                    "away": away_abbr,
                    "internalHomeProbability": round(prediction.home_probability, 4),
                    "internalPickProbability": round(prediction.pick_probability, 4),
                    "probability": round(home_probability, 4),
                    "pickProbability": round(pick_probability, 4),
                    "confidence": confidence,
                    "marketBacked": odds_available,
                    "predicted": predicted_winner,
                    "actual": actual_winner,
                    "correct": int(predicted_winner == actual_winner),
                    "modelVersion": MODEL_VERSION,
                }
            )

        examples.append(TrainingExample(features=features, label=1 if game.home_won else 0))
        weights.append(CURRENT_SEASON_SAMPLE_WEIGHT)
        league.apply_result(
            game.game_date,
            game.home_team_id,
            game.away_team_id,
            game.home_score,
            game.away_score,
        )

    return rows
