"""One-time prefetch of per-game reliever boxscore lines for the matrix seasons.

Populates data/cache/boxscore_bullpen/{game_pk}.json so the feature matrix build
and live board don't stall on thousands of boxscore fetches.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

from mlb_api import load_or_fetch_games
from bullpen_provider import _game_bullpen_lines


def main() -> None:
    today = date.today()
    yesterday = today - timedelta(days=1)
    ranges = [
        (date(2025, 3, 20), date(2025, 10, 5)),
        (date(2026, 3, 20), yesterday),
    ]
    total = 0
    done = 0
    all_games = []
    for start, end in ranges:
        games = load_or_fetch_games(start, end)
        all_games.extend(g for g in games if g.is_final)
    total = len(all_games)
    print(f"prefetching {total} game boxscores", flush=True)
    for g in all_games:
        _game_bullpen_lines(g.game_pk)
        done += 1
        if done % 200 == 0:
            print(f"  {done}/{total}", flush=True)
    print(f"DONE {done}/{total}", flush=True)


if __name__ == "__main__":
    main()
