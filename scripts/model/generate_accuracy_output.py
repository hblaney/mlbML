"""Build public/accuracy.json from walk-forward prediction history."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path

PUBLIC_DIR = Path(__file__).resolve().parents[2] / "public"
HISTORY_PATH = PUBLIC_DIR / "prediction-history.json"
OUTPUT_PATH = PUBLIC_DIR / "accuracy.json"


def main() -> None:
    payload = json.loads(HISTORY_PATH.read_text())
    predictions = payload.get("predictions", [])

    daily_buckets: dict[str, list[int]] = defaultdict(list)
    weekly_buckets: dict[str, list[int]] = defaultdict(list)
    correct = 0

    for row in predictions:
        day_key = row["date"]
        week_key = f"{date.fromisoformat(day_key).isocalendar().year}-W{date.fromisoformat(day_key).isocalendar().week:02d}"
        is_correct = int(row.get("correct", 0))
        correct += is_correct
        daily_buckets[day_key].append(is_correct)
        weekly_buckets[week_key].append(is_correct)

    evaluated = len(predictions)
    daily_accuracy = {
        day: sum(values) / len(values) for day, values in sorted(daily_buckets.items()) if values
    }
    weekly_accuracy = {
        week: sum(values) / len(values) for week, values in sorted(weekly_buckets.items()) if values
    }

    output = {
        "generated_at": payload.get("generated_at", date.today().isoformat()),
        "trained_through": payload.get("trained_through"),
        "evaluated_games": float(evaluated),
        "overall_accuracy": round(correct / evaluated, 4) if evaluated else 0.0,
        "brier_score": 0.0,
        "days_at_or_above_60pct": float(sum(1 for value in daily_accuracy.values() if value >= 0.6)),
        "weeks_at_or_above_60pct": float(sum(1 for value in weekly_accuracy.values() if value >= 0.6)),
        "daily_accuracy": daily_accuracy,
        "weekly_accuracy": weekly_accuracy,
        "recent_predictions": predictions[-40:],
        "prediction_history": predictions,
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"accuracy_games={evaluated}")
    print(f"accuracy_overall={output['overall_accuracy']:.4f}")


if __name__ == "__main__":
    main()
