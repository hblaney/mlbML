"""Focused 2026 improvement sweep with v2.0 calibration applied at scoring time."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.pipeline import Pipeline

from daily_auto_model import no_vig_market_probabilities
from fast_edge_model import predict_fast
from historical_odds import HistoricalOddsStore
from mlb_api import GameRecord, load_or_fetch_games, load_team_abbreviations
from team_tracker import LeagueState
from trained_edge_model import (
    MARKET_BLEND_WEIGHT,
    PUBLIC_CONFIDENCE_SHARPENING,
    PUBLIC_PROBABILITY_CAP,
    WARMUP_GAMES,
    TrainingExample,
    _clean_matrix,
    blend_with_market,
    confidence_for,
    feature_row,
    sharpen_public_probability,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "data" / "model" / "sweep_v2_improvements.json"


@dataclass
class Config:
    model_name: str
    refit_every: int
    trained_weight: float
    prior_season_weight: float
    current_season_weight: float
    use_prior_season: bool


def season_start(year: int) -> date:
    return date(year, 3, 20)


def load_season(year: int) -> list[GameRecord]:
    end = date(year, 10, 5)
    if year == date.today().year:
        end = min(end, date.today() - __import__("datetime").timedelta(days=1))
    return load_or_fetch_games(season_start(year), end)


def build_model(name: str) -> Pipeline:
    if name == "gb_depth1":
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
                )
            ]
        )
    return Pipeline(
        [
            (
                "model",
                GradientBoostingClassifier(
                    n_estimators=90,
                    learning_rate=0.05,
                    max_depth=2,
                    subsample=0.85,
                    random_state=42,
                ),
            )
        ]
    )


def fit_model(
    examples: list[TrainingExample],
    weights: list[float] | None,
    model_name: str,
) -> Pipeline | None:
    if len(examples) < WARMUP_GAMES:
        return None
    y = np.array([row.label for row in examples], dtype=int)
    if len(set(y.tolist())) < 2:
        return None
    x = _clean_matrix(np.array([row.features for row in examples], dtype=float))
    model = build_model(model_name)
    if weights is not None:
        model.fit(x, y, model__sample_weight=np.array(weights, dtype=float))
    else:
        model.fit(x, y)
    return model


def score_row(
    *,
    home_probability: float,
    away_probability: float,
    predicted_home: bool,
    internal_pick_probability: float,
    market_backed: bool,
    actual_home_won: bool,
) -> dict:
    pick_probability = max(home_probability, away_probability)
    internal_agrees = predicted_home == (home_probability >= 0.5)
    predicted_winner_home = predicted_home
    correct = int(predicted_winner_home == actual_home_won)
    confidence = confidence_for(
        pick_probability,
        market_backed=market_backed,
        internal_pick_probability=internal_pick_probability,
        internal_agrees=internal_agrees,
    )
    return {
        "correct": correct,
        "pick_probability": pick_probability,
        "confidence": confidence,
        "market_backed": market_backed,
    }


def evaluate(config: Config, games_2026: list[GameRecord], prior_games: list[GameRecord]) -> dict:
    team_abbr = load_team_abbreviations()
    odds = HistoricalOddsStore()
    league = LeagueState()
    examples: list[TrainingExample] = []
    weights: list[float] = []
    model: Pipeline | None = None
    last_fit_index = -config.refit_every
    predictions: list[dict] = []

    warmup_games = list(prior_games) if config.use_prior_season else []
    for game in warmup_games:
        examples.append(TrainingExample(features=feature_row(game, league), label=1 if game.home_won else 0))
        weights.append(config.prior_season_weight)
        league.apply_result(
            game.game_date,
            game.home_team_id,
            game.away_team_id,
            game.home_score,
            game.away_score,
        )

    for index, game in enumerate(games_2026):
        features = feature_row(game, league)

        if len(examples) >= WARMUP_GAMES and (model is None or index - last_fit_index >= config.refit_every):
            model = fit_model(examples, weights, config.model_name)
            last_fit_index = index

        if len(examples) >= WARMUP_GAMES and model is not None:
            x = _clean_matrix(np.array([features], dtype=float))
            trained_probability = float(model.predict_proba(x)[0, 1])
            form_probability = predict_fast(game, league).home_probability
            internal_home = float(
                np.clip(
                    (trained_probability * config.trained_weight) + (form_probability * (1.0 - config.trained_weight)),
                    0.30,
                    0.70,
                )
            )
            internal_away = 1.0 - internal_home
            internal_pick = max(internal_home, internal_away)
            predicted_home = internal_home >= internal_away

            home_abbr = team_abbr.get(game.home_team_id, str(game.home_team_id))
            away_abbr = team_abbr.get(game.away_team_id, str(game.away_team_id))
            market = odds.for_game(game.game_date.isoformat(), away_abbr, home_abbr)
            market_backed = market.source_count > 0 and market.home_moneyline != 0 and market.away_moneyline != 0
            home_probability = internal_home
            away_probability = internal_away
            if market_backed:
                market_probs = no_vig_market_probabilities(market.home_moneyline, market.away_moneyline)
                if market_probs is not None:
                    market_home, market_away = market_probs
                    home_probability = blend_with_market(internal_home, market_home)
                    away_probability = blend_with_market(internal_away, market_away)
                    total = home_probability + away_probability
                    home_probability /= total
                    away_probability /= total

            home_probability = sharpen_public_probability(home_probability)
            away_probability = 1.0 - home_probability
            predicted_home = home_probability >= away_probability

            if market_backed:
                predictions.append(
                    score_row(
                        home_probability=home_probability,
                        away_probability=away_probability,
                        predicted_home=predicted_home,
                        internal_pick_probability=internal_pick,
                        market_backed=True,
                        actual_home_won=game.home_won,
                    )
                )

        examples.append(TrainingExample(features=features, label=1 if game.home_won else 0))
        weights.append(config.current_season_weight)
        league.apply_result(
            game.game_date,
            game.home_team_id,
            game.away_team_id,
            game.home_score,
            game.away_score,
        )

    total = len(predictions)
    correct = sum(row["correct"] for row in predictions)
    high = [row for row in predictions if row["confidence"] in ("High", "Elite")]
    strong = [row for row in predictions if row["pick_probability"] >= 0.65]
    return {
        **config.__dict__,
        "games": total,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "high_conf_games": len(high),
        "high_conf_accuracy": round(sum(row["correct"] for row in high) / len(high), 4) if high else 0.0,
        "strong_65_games": len(strong),
        "strong_65_accuracy": round(sum(row["correct"] for row in strong) / len(strong), 4) if strong else 0.0,
        "calibration": {
            "market_blend": MARKET_BLEND_WEIGHT,
            "sharpening": PUBLIC_CONFIDENCE_SHARPENING,
            "cap": PUBLIC_PROBABILITY_CAP,
        },
    }


def main() -> None:
    games_2026 = load_season(2026)
    prior_2025 = load_season(2025)
    print(f"games_2026={len(games_2026)} prior_2025={len(prior_2025)}", flush=True)

    configs: list[Config] = []
    for model_name in ("gb_depth1", "gb_depth2"):
        for refit_every in (30, 60):
            for trained_weight in (0.85, 1.0):
                for use_prior in (False, True):
                    for prior_w, current_w in ((0.35, 1.0), (0.60, 1.25), (1.0, 1.0)):
                        if not use_prior and (prior_w != 1.0 or current_w != 1.0):
                            continue
                        configs.append(
                            Config(
                                model_name=model_name,
                                refit_every=refit_every,
                                trained_weight=trained_weight,
                                prior_season_weight=prior_w,
                                current_season_weight=current_w,
                                use_prior_season=use_prior,
                            )
                        )

    results = []
    for config in configs:
        result = evaluate(config, games_2026, prior_2025)
        results.append(result)
        print(
            f"model={config.model_name} prior={config.use_prior_season} tw={config.trained_weight} "
            f"refit={config.refit_every} acc={result['accuracy']:.4f} "
            f"high={result['high_conf_accuracy']:.4f}@{result['high_conf_games']}",
            flush=True,
        )

    results.sort(
        key=lambda row: (row["high_conf_accuracy"], row["accuracy"], row["high_conf_games"]),
        reverse=True,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps({"results": results}, indent=2))

    print("=== top by high-confidence accuracy ===")
    for row in results[:15]:
        print(json.dumps(row, sort_keys=True))
    print("=== top by overall accuracy ===")
    overall = sorted(results, key=lambda row: (row["accuracy"], row["high_conf_accuracy"]), reverse=True)
    for row in overall[:10]:
        print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    main()
