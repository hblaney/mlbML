"""Backfill missing rows in historical_odds.jsonl through yesterday.

The walk-forward pipeline grades every game against closing lines. When
historical_odds.jsonl stops updating, recent games lose marketBacked/edge and
model health falsely reports degradation.

Sources (in order):
  1. FantasyData visible consensus table (import_fantasydata_odds)
  2. The Odds API historical snapshots (requires ODDS_API_KEY)
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from historical_odds import HistoricalOddsStore, ODDS_PATH, _valid_american_odds
from import_fantasydata_odds import existing_keys, fetch_rows
from mlb_api import GameRecord, load_or_fetch_games, load_team_abbreviations
from odds_provider import fetch_historical_moneyline_market, implied_probability

ROOT = Path(__file__).resolve().parents[2]


def _store_max_date(store: HistoricalOddsStore) -> date | None:
    start, end = store.date_range()
    if not end:
        return None
    return date.fromisoformat(end[:10])


def _append_rows(rows: list[dict]) -> int:
    keys = existing_keys()
    new_rows = [
        row
        for row in rows
        if (row["start_date"][:10], row["away_abbr"].upper(), row["home_abbr"].upper()) not in keys
    ]
    if not new_rows:
        return 0
    ODDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ODDS_PATH.open("a") as handle:
        for row in new_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return len(new_rows)


def _fantasydata_backfill() -> int:
    rows = fetch_rows()
    return _append_rows(rows)


def _team_name_map() -> dict[int, str]:
    from mlb_api import load_team_names

    return load_team_names()


def _historical_api_row(game: GameRecord, home_ml: int, away_ml: int, source_count: int) -> dict:
    abbr = load_team_abbreviations()
    away = abbr.get(game.away_team_id, str(game.away_team_id)).upper()
    home = abbr.get(game.home_team_id, str(game.home_team_id)).upper()
    return {
        "start_date": game.game_datetime_iso,
        "game_type": "R",
        "away_team": away,
        "away_abbr": away,
        "home_team": home,
        "home_abbr": home,
        "away_score": int(game.away_score or 0),
        "home_score": int(game.home_score or 0),
        "venue": None,
        "opening_home_moneyline": home_ml,
        "opening_away_moneyline": away_ml,
        "closing_home_moneyline": home_ml,
        "closing_away_moneyline": away_ml,
        "closing_total": 8.5,
        "closing_over_price": -110,
        "closing_under_price": -110,
        "sportsbook_count": source_count,
        "sportsbooks": ["The Odds API historical"],
        "source": "odds_api_historical",
    }


def _odds_api_backfill(from_day: date, through: date) -> int:
    names = _team_name_map()
    abbr = load_team_abbreviations()
    keys = existing_keys()
    added = 0
    day = from_day
    while day <= through:
        games = [g for g in load_or_fetch_games(day, day) if g.is_final]
        if not games:
            day += timedelta(days=1)
            continue
        # Snapshot ~4h before first pitch on that slate (US evening).
        snapshot = datetime(day.year, day.month, day.day, 20, 0, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        market = fetch_historical_moneyline_market(snapshot)
        if not market:
            day += timedelta(days=1)
            continue
        rows: list[dict] = []
        for game in games:
            away_name = names.get(game.away_team_id, "").lower()
            home_name = names.get(game.home_team_id, "").lower()
            snap = market.get((away_name, home_name))
            if not snap or not snap.home_moneyline or not snap.away_moneyline:
                continue
            if not _valid_american_odds(int(snap.home_moneyline)) or not _valid_american_odds(int(snap.away_moneyline)):
                continue
            away = abbr.get(game.away_team_id, "").upper()
            home = abbr.get(game.home_team_id, "").upper()
            key = (day.isoformat(), away, home)
            if key in keys:
                continue
            rows.append(_historical_api_row(game, int(snap.home_moneyline), int(snap.away_moneyline), snap.source_count or 1))
            keys.add(key)
        added += _append_rows(rows)
        day += timedelta(days=1)
    return added


def main() -> None:
    yesterday = date.today() - timedelta(days=1)
    store = HistoricalOddsStore()
    max_date = _store_max_date(store)
    print(f"historical_odds_max={max_date} yesterday={yesterday}")

    fd_added = _fantasydata_backfill()
    print(f"fantasydata_added={fd_added}")

    store = HistoricalOddsStore()
    max_date = _store_max_date(store)
    if max_date and max_date < yesterday:
        gap_start = max_date + timedelta(days=1)
        api_added = _odds_api_backfill(gap_start, yesterday)
        print(f"odds_api_added={api_added}")

    store = HistoricalOddsStore()
    start, end = store.date_range()
    print(f"historical_odds_range={start}..{end}")


if __name__ == "__main__":
    main()
