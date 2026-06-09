"""Generate walk-forward prediction history with daily retraining."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from daily_auto_model import walk_forward_history
from mlb_api import load_or_fetch_games
from mlb_api import load_team_abbreviations

PUBLIC_PATH = Path(__file__).resolve().parents[2] / "public" / "prediction-history.json"


def main() -> None:
    today = date.today()
    yesterday = today - timedelta(days=1)
    history_start = date(yesterday.year - 1, 3, 20)
    games = load_or_fetch_games(history_start, yesterday)
    team_abbr = load_team_abbreviations()
    rows = walk_forward_history(games, team_abbr)

    PUBLIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_PATH.write_text(
        json.dumps(
            {
                "generated_at": today.isoformat(),
                "history_start": history_start.isoformat(),
                "trained_through": yesterday.isoformat(),
                "predictions": rows,
            },
            indent=2,
        )
    )
    print(f"generated_history_rows={len(rows)}")


if __name__ == "__main__":
    main()
