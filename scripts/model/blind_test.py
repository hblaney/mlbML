"""Blind-test ledger.

Use this daily. `predict` locks predictions before first pitch. `grade` later
fetches final scores and reports how the locked predictions performed.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from mlb_api import fetch_games, fetch_upcoming_games, load_or_fetch_games
from predictor import MlbPredictor

LEDGER_PATH = Path(__file__).resolve().parents[2] / "data" / "blind_predictions.jsonl"
REPORT_PATH = Path(__file__).resolve().parents[2] / "public" / "blind-test.json"


def _read_ledger() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    return [json.loads(line) for line in LEDGER_PATH.read_text().splitlines() if line.strip()]


def _append_rows(rows: list[dict]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing_keys = {row["prediction_key"] for row in _read_ledger()}
    new_rows = [row for row in rows if row["prediction_key"] not in existing_keys]
    if not new_rows:
        print("locked_predictions=0")
        return

    with LEDGER_PATH.open("a") as handle:
        for row in new_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    print(f"locked_predictions={len(new_rows)}")


def lock_predictions(days_ahead: int) -> None:
    today = date.today()
    historical_games = load_or_fetch_games(date(2024, 3, 20), today - timedelta(days=1))
    upcoming_games = fetch_upcoming_games(today, today + timedelta(days=days_ahead))

    predictor = MlbPredictor()
    predictor.fit(historical_games)
    predictions = predictor.predict_upcoming(upcoming_games)

    rows = []
    for prediction in predictions:
        rows.append(
            {
                "prediction_key": f"{prediction.game.game_pk}:{prediction.game.game_date.isoformat()}",
                "locked_at": today.isoformat(),
                "game_pk": prediction.game.game_pk,
                "game_date": prediction.game.game_date.isoformat(),
                "away": prediction.away_abbr,
                "home": prediction.home_abbr,
                "home_win_probability": round(prediction.home_win_probability, 4),
                "away_win_probability": round(prediction.away_win_probability, 4),
                "predicted_home_win": prediction.home_win_probability >= 0.5,
                "confidence": prediction.confidence,
                "graded": False,
            }
        )

    _append_rows(rows)


def grade_predictions() -> None:
    rows = _read_ledger()
    if not rows:
        print("graded_predictions=0")
        return

    start = min(date.fromisoformat(row["game_date"]) for row in rows)
    end = max(date.fromisoformat(row["game_date"]) for row in rows)
    completed_games = {game.game_pk: game for game in fetch_games(start, end, final_only=True)}

    graded = []
    for row in rows:
        game = completed_games.get(row["game_pk"])
        if game is None:
            graded.append(row)
            continue

        updated = dict(row)
        updated["graded"] = True
        updated["home_score"] = game.home_score
        updated["away_score"] = game.away_score
        updated["home_won"] = game.home_won
        updated["correct"] = bool(row["predicted_home_win"]) == game.home_won
        graded.append(updated)

    LEDGER_PATH.write_text("\n".join(json.dumps(row, sort_keys=True) for row in graded) + "\n")

    completed = [row for row in graded if row.get("graded")]
    correct = [row for row in completed if row.get("correct")]
    accuracy = len(correct) / len(completed) if completed else 0.0
    daily: dict[str, list[int]] = {}
    for row in completed:
        daily.setdefault(row["game_date"], []).append(1 if row.get("correct") else 0)

    report = {
        "generated_at": date.today().isoformat(),
        "locked_predictions": len(rows),
        "graded_predictions": len(completed),
        "accuracy": accuracy,
        "daily_accuracy": {
            day: sum(values) / len(values)
            for day, values in sorted(daily.items())
        },
        "recent": completed[-30:],
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"graded_predictions={len(completed)}")
    print(f"accuracy={accuracy:.4f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["predict", "grade"])
    parser.add_argument("--days-ahead", type=int, default=2)
    args = parser.parse_args()

    if args.command == "predict":
        lock_predictions(args.days_ahead)
    else:
        grade_predictions()


if __name__ == "__main__":
    main()
