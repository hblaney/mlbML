"""Generate walk-forward prediction history with daily retraining."""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from daily_auto_model import walk_forward_history
from mlb_api import load_or_fetch_games, load_team_abbreviations

PUBLIC_PATH = Path(__file__).resolve().parents[2] / "public" / "prediction-history.json"


def season_start_for(year: int) -> date:
    return date(year, 3, 20)


def season_history_rows(
    year: int,
    end_date: date,
    team_abbr: dict[int, str],
    prior_games: list[GameRecord] | None = None,
) -> list[dict]:
    games = load_or_fetch_games(season_start_for(year), end_date)
    return walk_forward_history(games, team_abbr, prior_games=prior_games)


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
    # Always warm up on prior-season games so early-season picks match the full
    # walk-forward (WARMUP_GAMES). --current-season-only only skips rewriting
    # prior-season output rows (those are preserved from the existing file).
    prior_games = None
    if yesterday.year > 2021:
        prior_games = load_or_fetch_games(
            season_start_for(yesterday.year - 1),
            date(yesterday.year - 1, 10, 5),
        )
    current_rows = season_history_rows(yesterday.year, yesterday, team_abbr, prior_games=prior_games)
    rows = current_rows
    history_start = season_start_for(yesterday.year)
    method = "current-season walk-forward retrain through yesterday"

    if not args.current_season_only:
        previous_year_end = date(yesterday.year - 1, 10, 5)
        rows = [
            *season_history_rows(yesterday.year - 1, previous_year_end, team_abbr),
            *current_rows,
        ]
        history_start = season_start_for(yesterday.year - 1)
        method = "season walk-forward with current-season retrain and market-backed confidence when odds are available"

    # Keep prior-season archive rows when regenerating current season only.
    if args.current_season_only and PUBLIC_PATH.exists():
        try:
            existing = json.loads(PUBLIC_PATH.read_text())
            prior_rows = [
                row
                for row in existing.get("predictions", [])
                if str(row.get("date", ""))[:4] < str(yesterday.year)
            ]
            if prior_rows:
                rows = [*prior_rows, *rows]
                history_start = date.fromisoformat(
                    str(existing.get("history_start") or prior_rows[0]["date"])
                )
                method = (
                    "current-season walk-forward retrain through yesterday "
                    "+ preserved prior-season archive rows"
                )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass

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
    print(f"trained_through={yesterday.isoformat()}")


if __name__ == "__main__":
    main()
