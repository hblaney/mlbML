"""Build a current-season live model performance curve from walk-forward history."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

PUBLIC_DIR = Path(__file__).resolve().parents[2] / "public"
HISTORY_PATH = PUBLIC_DIR / "prediction-history.json"
OUTPUT_PATH = PUBLIC_DIR / "model-live-performance.json"

STARTING_BANKROLL = 10_000.0
STAKE = 100.0
BASELINE_ODDS = -110
HIGH_CONFIDENCE = {"High", "Elite"}


def baseline_profit(won: bool) -> float:
    return (STAKE * 100 / 110) if won else -STAKE


def summarize(rows: list[dict], *, profit: float | None = None, staked: float | None = None) -> dict:
    wins = sum(int(row.get("correct", 0)) for row in rows)
    total = len(rows)
    resolved_profit = profit if profit is not None else 0.0
    resolved_staked = staked if staked is not None else 0.0
    return {
        "bets": total,
        "wins": wins,
        "losses": total - wins,
        "staked": round(resolved_staked, 2),
        "profit": round(resolved_profit, 2),
        "roi": round(resolved_profit / resolved_staked, 4) if resolved_staked else 0.0,
        "hit_rate": round(wins / total, 4) if total else 0.0,
    }


def main() -> None:
    payload = json.loads(HISTORY_PATH.read_text())
    predictions = payload.get("predictions", [])
    today = date.today()
    yesterday = today - timedelta(days=1)
    season = str(yesterday.year)

    graded = [
        row
        for row in predictions
        if row.get("actual") and row.get("date", "") < today.isoformat() and row.get("date", "").startswith(season)
    ]
    graded.sort(key=lambda row: (row["date"], row.get("gamePk", 0)))

    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in graded:
        by_day[row["date"]].append(row)

    checkpoints: list[dict] = []
    daily_snapshots: list[dict] = []
    running_balance = STARTING_BANKROLL
    cumulative_profit = 0.0
    cumulative_staked = 0.0
    cumulative_wins = 0
    cumulative_bets = 0

    for day in sorted(by_day):
        day_rows = by_day[day]
        bet_rows = [row for row in day_rows if row.get("confidence") in HIGH_CONFIDENCE]
        day_profit = sum(baseline_profit(bool(row.get("correct"))) for row in bet_rows)
        day_staked = len(bet_rows) * STAKE
        day_wins = sum(int(row.get("correct", 0)) for row in bet_rows)

        cumulative_profit += day_profit
        cumulative_staked += day_staked
        cumulative_wins += day_wins
        cumulative_bets += len(bet_rows)
        running_balance += day_profit

        day_summary = {
            "date": day,
            "games": len(day_rows),
            "accuracy": round(sum(int(row.get("correct", 0)) for row in day_rows) / len(day_rows), 4),
            "high_confidence": summarize(bet_rows, profit=day_profit, staked=day_staked),
        }
        daily_snapshots.append(day_summary)
        checkpoints.append(
            {
                "date": day,
                "profit": round(day_profit, 2),
                "balance": round(running_balance, 2),
                "return_pct": round((running_balance - STARTING_BANKROLL) / STARTING_BANKROLL, 4),
                "season_accuracy": day_summary["accuracy"],
                "high_confidence_bets": len(bet_rows),
            }
        )

    output = {
        "generated_at": today.isoformat(),
        "trained_through": payload.get("trained_through"),
        "model_version": graded[-1].get("modelVersion") if graded else None,
        "season": season,
        "method": "current-season walk-forward retrain with daily checkpoints",
        "stake": STAKE,
        "starting_bankroll": STARTING_BANKROLL,
        "baseline_odds": BASELINE_ODDS,
        "date_range": {
            "start": daily_snapshots[0]["date"] if daily_snapshots else None,
            "end": daily_snapshots[-1]["date"] if daily_snapshots else None,
        },
        "overall": summarize(graded),
        "high_confidence": summarize(
            [row for row in graded if row.get("confidence") in HIGH_CONFIDENCE],
            profit=cumulative_profit,
            staked=cumulative_staked,
        ),
        "cumulative": {
            "bets": cumulative_bets,
            "wins": cumulative_wins,
            "losses": cumulative_bets - cumulative_wins,
            "profit": round(cumulative_profit, 2),
            "roi": round(cumulative_profit / cumulative_staked, 4) if cumulative_staked else 0.0,
            "balance": round(running_balance, 2),
            "return_pct": round(cumulative_profit / STARTING_BANKROLL, 4) if STARTING_BANKROLL else 0.0,
        },
        "checkpoints": checkpoints[-120:],
        "daily": daily_snapshots[-120:],
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"live_curve_days={len(daily_snapshots)}")
    print(f"live_curve_profit={cumulative_profit:.2f}")
    print(f"live_curve_accuracy={output['overall']['hit_rate']:.4f}")


if __name__ == "__main__":
    main()
