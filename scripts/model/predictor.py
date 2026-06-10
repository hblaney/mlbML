"""Train and run the MLB home-win prediction model."""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler

from context import FeatureContext
from elo import win_probability
from feature_registry import FEATURES, validate_feature_count
from features import build_feature_vector
from historical_odds import HistoricalOddsStore
from mlb_api import GameRecord, fetch_pitcher_season_era, load_or_fetch_games, load_team_abbreviations
from odds_provider import fetch_moneyline_market, market_for_game
from park_factors import park_for_team
from team_tracker import LeagueState
from team_stats_provider import team_stats_as_of
from weather import fetch_historical_weather, fetch_weather

MODEL_DIR = Path(__file__).resolve().parents[2] / "data" / "model"
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data"
WARMUP_GAMES = 250
ELO_WEIGHT = 0.35
ML_WEIGHT = 0.65


@dataclass
class PredictionRow:
    game: GameRecord
    home_abbr: str
    away_abbr: str
    home_win_probability: float
    away_win_probability: float
    confidence: str
    home_moneyline: int = 100
    away_moneyline: int = 100


class MlbPredictor:
    def __init__(self) -> None:
        validate_feature_count()
        self.league = LeagueState()
        self.scaler = StandardScaler()
        self.model = HistGradientBoostingClassifier(
            max_depth=6,
            learning_rate=0.05,
            max_iter=250,
            random_state=42,
        )
        self.is_fitted = False
        self.team_abbr = load_team_abbreviations()
        self.historical_odds = HistoricalOddsStore()

    def _starter_eras(self, game: GameRecord) -> tuple[float, float]:
        season = game.game_date.year
        home_era = 4.35
        away_era = 4.35

        if game.home_pitcher_id:
            try:
                home_era = fetch_pitcher_season_era(game.home_pitcher_id, season)
            except Exception:
                pass
        if game.away_pitcher_id:
            try:
                away_era = fetch_pitcher_season_era(game.away_pitcher_id, season)
            except Exception:
                pass

        return home_era, away_era

    def _feature_row(self, game: GameRecord) -> list[float]:
        home = self.league.team(game.home_team_id)
        away = self.league.team(game.away_team_id)
        home_era, away_era = self._starter_eras(game)
        return build_feature_vector(home, away, game.game_date, home_era, away_era, self._context_for_game(game))

    def _context_for_game(
        self,
        game: GameRecord,
        *,
        live_sources: bool = False,
        market: dict[tuple[str, str], MarketSnapshot] | None = None,
    ) -> FeatureContext:
        park = park_for_team(game.home_team_id)
        game_dt = datetime.fromisoformat(game.game_datetime_iso.replace("Z", "+00:00"))
        home_stats = team_stats_as_of(game.home_team_id, game.game_date)
        away_stats = team_stats_as_of(game.away_team_id, game.game_date)

        if not live_sources:
            away_abbr = self.team_abbr.get(game.away_team_id, "")
            home_abbr = self.team_abbr.get(game.home_team_id, "")
            market = self.historical_odds.for_game(game.game_date.isoformat(), away_abbr, home_abbr)
            weather = fetch_historical_weather(game.home_team_id, game.game_datetime_iso)
            return FeatureContext(
                market=market,
                weather=weather,
                park=park,
                home_stats=home_stats,
                away_stats=away_stats,
                game_hour_utc=float(game_dt.hour),
                is_day_game=game_dt.hour < 22,
            )

        market = market_for_game(game, market if market is not None else fetch_moneyline_market())
        weather = fetch_weather(game.home_team_id, game.game_datetime_iso)
        return FeatureContext(
            market=market,
            weather=weather,
            park=park,
            home_stats=home_stats,
            away_stats=away_stats,
            game_hour_utc=float(game_dt.hour),
            is_day_game=game_dt.hour < 22,
        )

    def _blend_probability(self, game: GameRecord, ml_probability: float) -> float:
        elo_probability = self.league.predict_home_win_probability(
            game.home_team_id,
            game.away_team_id,
        )
        return ELO_WEIGHT * elo_probability + ML_WEIGHT * ml_probability

    def fit(self, games: list[GameRecord]) -> dict[str, float]:
        features: list[list[float]] = []
        labels: list[int] = []
        state = LeagueState()
        self.team_abbr = load_team_abbreviations()

        for game in games:
            home = state.team(game.home_team_id)
            away = state.team(game.away_team_id)
            home_era, away_era = self._starter_eras(game)
            context = self._context_for_game(game)
            features.append(build_feature_vector(home, away, game.game_date, home_era, away_era, context))
            labels.append(1 if game.home_won else 0)
            state.apply_result(
                game.game_date,
                game.home_team_id,
                game.away_team_id,
                game.home_score,
                game.away_score,
            )

        x = np.array(features, dtype=float)
        y = np.array(labels, dtype=int)
        x_scaled = self.scaler.fit_transform(x)
        self.model.fit(x_scaled, y)
        self.league = state
        self.is_fitted = True

        train_probs = self.model.predict_proba(x_scaled)[:, 1]
        train_preds = train_probs >= 0.5
        accuracy = float(np.mean(train_preds == y))
        brier = float(np.mean((train_probs - y) ** 2))

        return {"train_games": float(len(games)), "train_accuracy": accuracy, "train_brier": brier}

    def walk_forward_backtest(self, games: list[GameRecord]) -> dict[str, float | list[dict[str, float | str]]]:
        predictions: list[dict[str, float | str]] = []
        correct = 0
        brier_scores: list[float] = []
        daily_buckets: dict[str, list[int]] = {}
        weekly_buckets: dict[str, list[int]] = {}

        state = LeagueState()
        scaler = StandardScaler()
        model = HistGradientBoostingClassifier(
            max_depth=6,
            learning_rate=0.05,
            max_iter=250,
            random_state=42,
        )

        train_x: list[list[float]] = []
        train_y: list[int] = []
        last_fit_index = 0

        for index, game in enumerate(games):
            home = state.team(game.home_team_id)
            away = state.team(game.away_team_id)
            home_era, away_era = self._starter_eras(game)
            context = self._context_for_game(game)
            feature_row = build_feature_vector(home, away, game.game_date, home_era, away_era, context)

            if index >= WARMUP_GAMES and len(train_x) >= WARMUP_GAMES:
                if index - last_fit_index >= 14 or index == WARMUP_GAMES:
                    x = np.array(train_x, dtype=float)
                    y = np.array(train_y, dtype=int)
                    x_scaled = scaler.fit_transform(x)
                    model.fit(x_scaled, y)
                    last_fit_index = index

                x_scaled = scaler.transform(np.array([feature_row], dtype=float))
                ml_probability = float(model.predict_proba(x_scaled)[0, 1])
                elo_probability = win_probability(home.elo, away.elo)
                probability = ELO_WEIGHT * elo_probability + ML_WEIGHT * ml_probability
                predicted_home = probability >= 0.5
                actual = 1 if game.home_won else 0

                if predicted_home == game.home_won:
                    correct += 1

                brier_scores.append((probability - actual) ** 2)
                day_key = game.game_date.isoformat()
                week_key = f"{game.game_date.isocalendar().year}-W{game.game_date.isocalendar().week:02d}"
                daily_buckets.setdefault(day_key, []).append(int(predicted_home == game.home_won))
                weekly_buckets.setdefault(week_key, []).append(int(predicted_home == game.home_won))

                predictions.append(
                    {
                        "date": day_key,
                        "home": self.team_abbr.get(game.home_team_id, str(game.home_team_id)),
                        "away": self.team_abbr.get(game.away_team_id, str(game.away_team_id)),
                        "probability": round(probability, 4),
                        "correct": int(predicted_home == game.home_won),
                    }
                )

            train_x.append(feature_row)
            train_y.append(1 if game.home_won else 0)
            state.apply_result(
                game.game_date,
                game.home_team_id,
                game.away_team_id,
                game.home_score,
                game.away_score,
            )

        evaluated = len(predictions)
        daily_accuracy = {
            day: sum(values) / len(values) for day, values in daily_buckets.items() if values
        }
        weekly_accuracy = {
            week: sum(values) / len(values) for week, values in weekly_buckets.items() if values
        }

        return {
            "evaluated_games": float(evaluated),
            "accuracy": correct / evaluated if evaluated else 0.0,
            "brier_score": float(np.mean(brier_scores)) if brier_scores else 0.0,
            "days_at_or_above_60pct": float(sum(1 for value in daily_accuracy.values() if value >= 0.6)),
            "weeks_at_or_above_60pct": float(sum(1 for value in weekly_accuracy.values() if value >= 0.6)),
            "daily_accuracy": daily_accuracy,
            "weekly_accuracy": weekly_accuracy,
            "prediction_history": predictions,
            "recent_predictions": predictions[-20:],
        }

    def predict_upcoming(self, games: list[GameRecord]) -> list[PredictionRow]:
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before predicting upcoming games.")

        rows: list[PredictionRow] = []
        market = fetch_moneyline_market()
        for game in games:
            home = self.league.team(game.home_team_id)
            away = self.league.team(game.away_team_id)
            home_era, away_era = self._starter_eras(game)
            context = self._context_for_game(game, live_sources=True, market=market)
            feature_row = np.array(
                [build_feature_vector(home, away, game.game_date, home_era, away_era, context)],
                dtype=float,
            )
            ml_probability = float(self.model.predict_proba(self.scaler.transform(feature_row))[0, 1])
            home_probability = self._blend_probability(game, ml_probability)
            away_probability = 1.0 - home_probability
            edge = abs(home_probability - 0.5)
            confidence = "High" if edge >= 0.08 else "Medium" if edge >= 0.04 else "Low"

            rows.append(
                PredictionRow(
                    game=game,
                    home_abbr=self.team_abbr.get(game.home_team_id, str(game.home_team_id)),
                    away_abbr=self.team_abbr.get(game.away_team_id, str(game.away_team_id)),
                    home_win_probability=home_probability,
                    away_win_probability=away_probability,
                    confidence=confidence,
                    home_moneyline=context.market.home_moneyline or 100,
                    away_moneyline=context.market.away_moneyline or 100,
                )
            )

        return rows

    def save(self) -> None:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        with (MODEL_DIR / "model.pkl").open("wb") as handle:
            pickle.dump(
                {
                    "model": self.model,
                    "scaler": self.scaler,
                    "league": self.league,
                    "team_abbr": self.team_abbr,
                },
                handle,
            )

    def load(self) -> None:
        with (MODEL_DIR / "model.pkl").open("rb") as handle:
            payload = pickle.load(handle)
        self.model = payload["model"]
        self.scaler = payload["scaler"]
        self.league = payload["league"]
        self.team_abbr = payload["team_abbr"]
        self.is_fitted = True


def write_outputs(backtest: dict, predictions: list[PredictionRow]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    public_dir = Path(__file__).resolve().parents[2] / "public"
    public_dir.mkdir(parents=True, exist_ok=True)

    accuracy_payload = {
        "generated_at": date.today().isoformat(),
        "evaluated_games": backtest.get("evaluated_games", 0),
        "overall_accuracy": backtest.get("accuracy", 0),
        "brier_score": backtest.get("brier_score", 0),
        "days_at_or_above_60pct": backtest.get("days_at_or_above_60pct", 0),
        "weeks_at_or_above_60pct": backtest.get("weeks_at_or_above_60pct", 0),
        "daily_accuracy": backtest.get("daily_accuracy", {}),
        "weekly_accuracy": backtest.get("weekly_accuracy", {}),
        "prediction_history": backtest.get("prediction_history", []),
        "recent_predictions": backtest.get("recent_predictions", []),
    }

    prediction_payload = [
        {
            "id": f"{row.away_abbr.lower()}-{row.home_abbr.lower()}-{row.game.game_date.isoformat()}",
            "date": row.game.game_date.isoformat(),
            "startsAt": row.game.game_datetime_iso,
            "awayTeam": row.away_abbr.lower(),
            "homeTeam": row.home_abbr.lower(),
            "awayPitcher": "TBD",
            "homePitcher": "TBD",
            "modelHomeWinProbability": round(row.home_win_probability, 4),
            "modelAwayWinProbability": round(row.away_win_probability, 4),
            "homeMoneyline": row.home_moneyline,
            "awayMoneyline": row.away_moneyline,
            "confidence": row.confidence,
            "modelVersion": "elo-gbm-v0.1",
            "explanation": [
                "Generated from the daily trained MLB model",
                "Market odds are included when an odds feed is available",
                "Probable starters are included in the model when MLB lists them",
            ],
        }
        for row in predictions
    ]

    for path in (OUTPUT_DIR / "accuracy.json", public_dir / "accuracy.json"):
        path.write_text(json.dumps(accuracy_payload, indent=2))

    for path in (OUTPUT_DIR / "predictions.json", public_dir / "predictions.json"):
        path.write_text(json.dumps(prediction_payload, indent=2))
