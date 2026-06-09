"""Daily training and prediction job."""

from __future__ import annotations

from datetime import date, timedelta

from predictor import MlbPredictor, write_outputs
from mlb_api import fetch_upcoming_games, load_or_fetch_games


MIN_TARGET_ACCURACY = 0.60


def main() -> None:
    season_start = date(2024, 3, 20)
    today = date.today()
    historical_games = load_or_fetch_games(season_start, today - timedelta(days=1))

    predictor = MlbPredictor()
    train_metrics = predictor.fit(historical_games)
    backtest = predictor.walk_forward_backtest(historical_games)

    upcoming = fetch_upcoming_games(today, today)
    predictions = predictor.predict_upcoming(upcoming) if upcoming else []

    write_outputs(backtest, predictions)
    predictor.save()

    promote = backtest["accuracy"] >= MIN_TARGET_ACCURACY
    print(f"trained_at={today.isoformat()}")
    print(f"train_games={int(train_metrics['train_games'])}")
    print(f"train_accuracy={train_metrics['train_accuracy']:.4f}")
    print(f"backtest_accuracy={backtest['accuracy']:.4f}")
    print(f"backtest_brier={backtest['brier_score']:.4f}")
    print(f"weeks_at_or_above_60pct={int(backtest['weeks_at_or_above_60pct'])}")
    print(f"upcoming_predictions={len(predictions)}")
    print(f"promote_model={str(promote).lower()}")


if __name__ == "__main__":
    main()
