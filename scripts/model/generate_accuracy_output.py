"""Build public/accuracy.json from walk-forward prediction history."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

PUBLIC_DIR = Path(__file__).resolve().parents[2] / "public"
HISTORY_PATH = PUBLIC_DIR / "prediction-history.json"
OUTPUT_PATH = PUBLIC_DIR / "accuracy.json"
LIVE_PERF_PATH = PUBLIC_DIR / "model-live-performance.json"
HIGH_CONFIDENCE = {"High", "Elite"}


def summarize_band(rows: list[dict]) -> dict:
    if not rows:
        return {"bets": 0, "wins": 0, "losses": 0, "hit_rate": None}
    wins = sum(int(r.get("correct", 0)) for r in rows)
    total = len(rows)
    return {
        "bets": total,
        "wins": wins,
        "losses": total - wins,
        "hit_rate": round(wins / total, 4),
    }


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {
            "games": 0,
            "wins": 0,
            "losses": 0,
            "accuracy": 0.0,
        }
    wins = sum(int(row.get("correct", 0)) for row in rows)
    total = len(rows)
    return {
        "games": total,
        "wins": wins,
        "losses": total - wins,
        "accuracy": round(wins / total, 4),
    }


def main() -> None:
    payload = json.loads(HISTORY_PATH.read_text())
    predictions = payload.get("predictions", [])
    trained_through = payload.get("trained_through")
    season = trained_through[:4] if trained_through else str(date.today().year)

    daily_buckets: dict[str, list[int]] = defaultdict(list)
    weekly_buckets: dict[str, list[int]] = defaultdict(list)

    season_rows = [
        row
        for row in predictions
        if row.get("actual") and str(row.get("date", "")).startswith(season)
    ]
    season_market_rows = [row for row in season_rows if row.get("marketBacked")]
    season_high_rows = [
        row for row in season_market_rows if row.get("confidence") in HIGH_CONFIDENCE
    ]

    archive_correct = 0
    for row in predictions:
        day_key = row["date"]
        week_key = f"{date.fromisoformat(day_key).isocalendar().year}-W{date.fromisoformat(day_key).isocalendar().week:02d}"
        is_correct = int(row.get("correct", 0))
        archive_correct += is_correct
        daily_buckets[day_key].append(is_correct)
        weekly_buckets[week_key].append(is_correct)

    season_summary = summarize(season_market_rows)
    season_high_summary = summarize(season_high_rows)
    archive_evaluated = len(predictions)
    archive_accuracy = round(archive_correct / archive_evaluated, 4) if archive_evaluated else 0.0

    daily_accuracy = {
        day: sum(values) / len(values) for day, values in sorted(daily_buckets.items()) if values
    }
    weekly_accuracy = {
        week: sum(values) / len(values) for week, values in sorted(weekly_buckets.items()) if values
    }
    season_daily_accuracy = {
        day: sum(int(row.get("correct", 0)) for row in rows) / len(rows)
        for day, rows in sorted(
            {
                row["date"]: [item for item in season_market_rows if item["date"] == row["date"]]
                for row in season_market_rows
            }.items()
        )
        if rows
    }

    # Confidence-level breakdown for current season
    graded_season = [r for r in season_rows if r.get("actual") and r.get("predicted")]
    by_confidence = {
        conf: summarize_band([r for r in graded_season if r.get("confidence") == conf])
        for conf in ("Elite", "High", "Medium", "Low")
    }

    # Recent windows (all graded rows, not just market-backed)
    today_str = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    seven_ago_str = (date.today() - timedelta(days=7)).isoformat()
    graded_all = [r for r in predictions if r.get("actual") and r.get("predicted")]
    last_7_days = summarize_band([r for r in graded_all if seven_ago_str <= r.get("date", "") < today_str])
    yesterday_band = summarize_band([r for r in graded_all if r.get("date", "") == yesterday_str])

    output = {
        "generated_at": payload.get("generated_at", date.today().isoformat()),
        "trained_through": trained_through,
        "season": season,
        "evaluated_games": float(season_summary["games"]),
        "overall_accuracy": season_summary["accuracy"],
        "current_season": {
            "season": season,
            "market_backed_games": season_summary["games"],
            "market_backed_accuracy": season_summary["accuracy"],
            "high_confidence_games": season_high_summary["games"],
            "high_confidence_accuracy": season_high_summary["accuracy"],
            "daily_accuracy": season_daily_accuracy,
        },
        "by_confidence": by_confidence,
        "last_7_days": last_7_days,
        "yesterday": yesterday_band,
        "archive": {
            "evaluated_games": float(archive_evaluated),
            "overall_accuracy": archive_accuracy,
        },
        "brier_score": 0.0,
        "days_at_or_above_60pct": float(sum(1 for value in season_daily_accuracy.values() if value >= 0.6)),
        "weeks_at_or_above_60pct": float(sum(1 for value in weekly_accuracy.values() if value >= 0.6)),
        "daily_accuracy": daily_accuracy,
        "weekly_accuracy": weekly_accuracy,
        "recent_predictions": predictions[-40:],
        "prediction_history": predictions,
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    # Write model-live-performance.json so history page can display full breakdown
    live_perf = {
        "generated_at": today_str,
        "trained_through": trained_through,
        "season": season,
        "method": "walk_forward_graded",
        "stake": 0.30,
        "starting_bankroll": 22.0,
        "baseline_odds": -110,
        "date_range": {"start": season + "-03-20", "end": yesterday_str},
        "overall": {
            "bets": by_confidence["High"]["bets"] + by_confidence["Elite"]["bets"] +
                    by_confidence["Medium"]["bets"] + by_confidence["Low"]["bets"],
            "wins": by_confidence["High"]["wins"] + by_confidence["Elite"]["wins"] +
                    by_confidence["Medium"]["wins"] + by_confidence["Low"]["wins"],
            "losses": by_confidence["High"]["losses"] + by_confidence["Elite"]["losses"] +
                      by_confidence["Medium"]["losses"] + by_confidence["Low"]["losses"],
            "hit_rate": season_summary["accuracy"],
        },
        "high_confidence": {
            "bets": by_confidence["High"]["bets"] + by_confidence["Elite"]["bets"],
            "wins": by_confidence["High"]["wins"] + by_confidence["Elite"]["wins"],
            "losses": by_confidence["High"]["losses"] + by_confidence["Elite"]["losses"],
            "hit_rate": season_high_summary["accuracy"],
        },
        "by_confidence": by_confidence,
        "last_7_days": last_7_days,
        "yesterday": yesterday_band,
        "cumulative": [],
        "checkpoints": [],
        "daily": [],
    }
    LIVE_PERF_PATH.write_text(json.dumps(live_perf, indent=2))

    print(f"accuracy_season={season}")
    print(f"accuracy_market_backed={output['overall_accuracy']:.4f}")
    print(f"accuracy_high_confidence={season_high_summary['accuracy']:.4f}")
    print(f"accuracy_archive={archive_accuracy:.4f}")
    print(f"by_confidence_high={by_confidence['High']['hit_rate']}")
    print(f"by_confidence_elite={by_confidence['Elite']['hit_rate']}")


if __name__ == "__main__":
    main()
