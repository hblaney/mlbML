"""Walk-forward backtest on real MLB game history."""

from __future__ import annotations

from datetime import date

from predictor import MlbPredictor, write_outputs
from mlb_api import load_or_fetch_games


def main() -> None:
    season_start = date(2025, 3, 20)
    season_end = date.today()
    games = load_or_fetch_games(season_start, season_end)

    predictor = MlbPredictor()
    results = predictor.walk_forward_backtest(games)
    write_outputs(results, [])

    for key, value in results.items():
        if key in {"daily_accuracy", "weekly_accuracy", "recent_predictions"}:
            continue
        if isinstance(value, float):
            print(f"{key}={value:.4f}")
        else:
            print(f"{key}={value}")


if __name__ == "__main__":
    main()
