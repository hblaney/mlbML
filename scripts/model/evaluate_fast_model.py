"""Compare the upgraded fast predictor against raw Elo on historical games."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from fast_edge_model import predict_fast
from mlb_api import load_or_fetch_games
from team_tracker import LeagueState
from trained_edge_model import REFIT_EVERY, WARMUP_GAMES, TrainingExample, feature_row, fit_model, predict_with_model


def brier(probabilities: list[float], labels: list[int]) -> float:
    return float(np.mean([(probability - label) ** 2 for probability, label in zip(probabilities, labels)]))


def main() -> None:
    today = date.today()
    games = load_or_fetch_games(date(today.year, 3, 20), today - timedelta(days=1))
    league = LeagueState()
    warmup = 120
    elo_correct = 0
    fast_correct = 0
    trained_correct = 0
    evaluated = 0
    elo_probs: list[float] = []
    fast_probs: list[float] = []
    trained_probs: list[float] = []
    labels: list[int] = []
    high_confidence = []
    examples: list[TrainingExample] = []
    model = None
    last_fit_index = 0

    for index, game in enumerate(games):
        features = feature_row(game, league)
        elo_home_probability = league.predict_home_win_probability(game.home_team_id, game.away_team_id)
        fast = predict_fast(game, league)
        if len(examples) >= WARMUP_GAMES and (model is None or index - last_fit_index >= REFIT_EVERY):
            model = fit_model(examples)
            last_fit_index = index
        trained = predict_with_model(game, league, model)

        if len(examples) >= WARMUP_GAMES:
            actual = 1 if game.home_won else 0
            elo_correct += int((elo_home_probability >= 0.5) == game.home_won)
            fast_correct += int(fast.predicted_home == game.home_won)
            trained_correct += int(trained.predicted_home == game.home_won)
            evaluated += 1
            elo_probs.append(elo_home_probability)
            fast_probs.append(fast.home_probability)
            trained_probs.append(trained.home_probability)
            labels.append(actual)
            if trained.confidence in {"High", "Elite"}:
                high_confidence.append(int(trained.predicted_home == game.home_won))

        examples.append(TrainingExample(features=features, label=1 if game.home_won else 0))
        league.apply_result(
            game.game_date,
            game.home_team_id,
            game.away_team_id,
            game.home_score,
            game.away_score,
        )

    print(f"evaluated_games={evaluated}")
    print(f"raw_elo_accuracy={elo_correct / evaluated:.4f}")
    print(f"fast_edge_accuracy={fast_correct / evaluated:.4f}")
    print(f"trained_edge_accuracy={trained_correct / evaluated:.4f}")
    print(f"raw_elo_brier={brier(elo_probs, labels):.4f}")
    print(f"fast_edge_brier={brier(fast_probs, labels):.4f}")
    print(f"trained_edge_brier={brier(trained_probs, labels):.4f}")
    if high_confidence:
        print(f"high_confidence_games={len(high_confidence)}")
        print(f"high_confidence_accuracy={sum(high_confidence) / len(high_confidence):.4f}")


if __name__ == "__main__":
    main()
