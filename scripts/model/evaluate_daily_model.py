"""Evaluate the self-retraining daily GBM walk-forward model."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

import numpy as np

from daily_auto_model import season_games_through, walk_forward_history
from mlb_api import load_team_abbreviations


def main() -> None:
    yesterday = date.today() - timedelta(days=1)
    games = season_games_through(yesterday)
    team_abbr = load_team_abbreviations()
    rows = walk_forward_history(games, team_abbr)

    correct = sum(row["correct"] for row in rows)
    evaluated = len(rows)
    brier = float(np.mean([(row["probability"] - (1 if row["actual"] == row["home"] else 0)) ** 2 for row in rows]))

    by_day: dict[str, list[int]] = defaultdict(list)
    high_conf: list[int] = []
    for row in rows:
        by_day[row["date"]].append(row["correct"])
        if row["confidence"] == "High":
            high_conf.append(row["correct"])

    worst = sorted((sum(v) / len(v), day, sum(v), len(v)) for day, v in by_day.items())[:8]

    print(f"evaluated_games={evaluated}")
    print(f"overall_accuracy={correct / evaluated:.4f}")
    print(f"brier={brier:.4f}")
    if high_conf:
        print(f"high_confidence_games={len(high_conf)}")
        print(f"high_confidence_accuracy={sum(high_conf) / len(high_conf):.4f}")
    print("worst_days:")
    for acc, day, wins, total in worst:
        print(f"  {day} {wins}-{total - wins} games={total} acc={acc:.3f}")


if __name__ == "__main__":
    main()
