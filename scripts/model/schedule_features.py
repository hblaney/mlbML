"""Point-in-time schedule / travel / circadian-fatigue signals.

A genuinely different signal class from team-average stats: how tired and how
jet-lagged each team is when it takes the field. All computed from the schedule we
already cache (no boxscores), using only games strictly before the prediction date.

For a team playing a game hosted by `host_team_id`:
  - rest_days       days since the team's previous game
  - games_last7     games played in the trailing 7 days (density / grind)
  - travel_km       great-circle distance from the previous game's park to this one
  - tz_shift_east   signed time-zone change (east = harder per circadian literature)
  - trip_games      length of the current consecutive road/home stand so far

NEGATIVE RESULT (Jun 2026): adding 8 travel/fatigue columns to feature_row scored
0.000-0.002 GBM importance (best, travel_diff, ranked 77th of 221 — below the top-35
prune cut). Like the bullpen experiment, the shallow GBM (dominated by starter ERA
diff at ~44%) extracts no usable signal from these context features. NOT shipped.
Kept as reusable, leakage-safe tooling for future interaction-aware models.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from mlb_api import load_or_fetch_games
from park_factors import park_location

# season -> {team_id: [(date, host_team_id), ...] sorted by date}
_SCHED: dict[int, dict[int, list[tuple[date, int]]]] = {}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _tz_offset_hours(lon: float) -> float:
    """Rough continental US time-zone proxy from longitude (15 deg per hour)."""
    return lon / 15.0


def _season_bounds(game_date: date) -> tuple[int, date, date]:
    season = game_date.year
    start = date(season, 3, 1)
    if game_date < start:
        season -= 1
        start = date(season, 3, 1)
    end = min(game_date, date.today() - timedelta(days=1))
    return season, start, end


def _season_schedule(season: int, start: date, end: date) -> dict[int, list[tuple[date, int]]]:
    if season in _SCHED:
        return _SCHED[season]
    games = load_or_fetch_games(start, end)
    sched: dict[int, list[tuple[date, int]]] = {}
    for g in games:
        sched.setdefault(g.home_team_id, []).append((g.game_date, g.home_team_id))
        sched.setdefault(g.away_team_id, []).append((g.game_date, g.home_team_id))
    for tid in sched:
        sched[tid].sort(key=lambda row: row[0])
    _SCHED[season] = sched
    return sched


def travel_fatigue(team_id: int, game_date: date, host_team_id: int) -> dict[str, float]:
    season, start, end = _season_bounds(game_date)
    sched = _season_schedule(season, start, end)
    rows = [r for r in sched.get(team_id, []) if r[0] < game_date]

    cur_lat, cur_lon, _ = park_location(host_team_id)
    if not rows:
        return {"rest_days": 5.0, "games_last7": 0.0, "travel_km": 0.0,
                "tz_shift_east": 0.0, "trip_games": 1.0}

    last_date, last_host = rows[-1]
    rest_days = float((game_date - last_date).days)
    games_last7 = float(sum(1 for d, _ in rows if d >= game_date - timedelta(days=7)))

    prev_lat, prev_lon, _ = park_location(last_host)
    travel_km = _haversine_km(prev_lat, prev_lon, cur_lat, cur_lon)
    # East-bound travel (later -> earlier body clock) is harder; sign it that way.
    tz_shift_east = _tz_offset_hours(prev_lon) - _tz_offset_hours(cur_lon)

    # Length of the current stand at this host (consecutive games same host, back to front).
    trip_games = 1.0
    for d, host in reversed(rows):
        if host == host_team_id:
            trip_games += 1.0
        else:
            break

    return {
        "rest_days": rest_days,
        "games_last7": games_last7,
        "travel_km": travel_km,
        "tz_shift_east": tz_shift_east,
        "trip_games": trip_games,
    }


if __name__ == "__main__":
    import sys
    d = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    # Example: Yankees (147) hosting; Mariners (136) visiting from the west coast.
    print("home host=147:", travel_fatigue(147, d, 147))
    print("away (136) at 147:", travel_fatigue(136, d, 147))
