"""Generate walk-forward prediction history with daily retraining."""

from __future__ import annotations

import json
import argparse
from datetime import date, timedelta
from pathlib import Path

from daily_auto_model import walk_forward_history
from mlb_api import load_or_fetch_games
from mlb_api import load_team_abbreviations

PUBLIC_PATH = Path(__file__).resolve().parents[2] / "public" / "prediction-history.json"


def season_start_for(year: int) -> date:
    return date(year, 3, 20)


def season_history_rows(year: int, end_date: date, team_abbr: dict[int, str]) -> list[dict]:
    games = load_or_fetch_games(season_start_for(year), end_date)
    return walk_forward_history(games, team_abbr)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--current-season-only",
        action="store_true",
        help="Only generate the current season. By default the prior season is included for odds-backed confidence validation.",
    )
    args = parser.parse_args()

    today = date.today()
    yesterday = today - timedelta(days=1)
    team_abbr = load_team_abbreviations()
    current_rows = season_history_rows(yesterday.year, yesterday, team_abbr)
    rows = current_rows
    history_start = season_start_for(yesterday.year)
    method = "current-season walk-forward"

    if not args.current_season_only:
        previous_year_end = date(yesterday.year - 1, 10, 5)
        rows = [
            *season_history_rows(yesterday.year - 1, previous_year_end, team_abbr),
            *current_rows,
        ]
        history_start = season_start_for(yesterday.year - 1)
        method = "season-local walk-forward by year with market-backed confidence when odds are available"

    rows.sort(key=lambda row: (row["date"], row["gamePk"]))

    PUBLIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_PATH.write_text(
        json.dumps(
            {
                "generated_at": today.isoformat(),
                "history_start": history_start.isoformat(),
                "method": method,
                "trained_through": yesterday.isoformat(),
                "predictions": rows,
            },
            indent=2,
        )
    )
    print(f"generated_history_rows={len(rows)}")


if __name__ == "__main__":
    main()
