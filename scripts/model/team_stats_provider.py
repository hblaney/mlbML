"""Real pre-game MLB team stats from MLB Stats API date ranges."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from context import TeamStatSnapshot

API_BASE = "https://statsapi.mlb.com/api/v1"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "team_stats"


def _to_float(value: object, default: float = 0.0) -> float:
    if value in (None, "", "-.--"):
        return default
    try:
        return float(str(value))
    except ValueError:
        return default


def _fetch_team_stat(team_id: int, season: int, group: str, start: date, end: date) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{team_id}_{season}_{group}_{start.isoformat()}_{end.isoformat()}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    params = urlencode(
        {
            "stats": "byDateRange",
            "group": group,
            "season": season,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
        }
    )
    url = f"{API_BASE}/teams/{team_id}/stats?{params}"
    with urlopen(url, timeout=30) as response:
        payload = json.load(response)

    stats = payload.get("stats") or []
    splits = stats[0].get("splits") if stats else []
    stat = splits[0].get("stat", {}) if splits else {}
    cache_path.write_text(json.dumps(stat))
    return stat


def _season_start(game_date: date) -> date:
    return date(game_date.year, 3, 1)


def raw_team_stats_as_of(team_id: int, game_date: date) -> tuple[dict, dict]:
    """Return raw hitting and pitching stat dictionaries available pre-game."""
    end = game_date - timedelta(days=1)
    start = _season_start(game_date)
    season = game_date.year

    if end < start:
        season -= 1
        start = date(season, 3, 1)
        end = date(season, 11, 30)

    return (
        _fetch_team_stat(team_id, season, "hitting", start, end),
        _fetch_team_stat(team_id, season, "pitching", start, end),
    )


def team_stats_as_of(team_id: int, game_date: date) -> TeamStatSnapshot:
    """Return team stats available before first pitch.

    Uses current-season date-range stats through the previous day. In the first
    few days of a season, falls back to the prior season to avoid future leakage.
    """
    end = game_date - timedelta(days=1)
    start = _season_start(game_date)
    season = game_date.year

    if end < start:
        season -= 1
        start = date(season, 3, 1)
        end = date(season, 11, 30)

    hitting = _fetch_team_stat(team_id, season, "hitting", start, end)
    pitching = _fetch_team_stat(team_id, season, "pitching", start, end)
    games = max(_to_float(hitting.get("gamesPlayed"), 1.0), 1.0)
    pitching_games = max(_to_float(pitching.get("gamesPlayed"), games), 1.0)
    pa = max(_to_float(hitting.get("plateAppearances"), 1.0), 1.0)
    bf = max(_to_float(pitching.get("battersFaced"), 1.0), 1.0)

    return TeamStatSnapshot(
        batting_avg=_to_float(hitting.get("avg")),
        obp=_to_float(hitting.get("obp")),
        slg=_to_float(hitting.get("slg")),
        ops=_to_float(hitting.get("ops")),
        babip=_to_float(hitting.get("babip")),
        runs_per_game=_to_float(hitting.get("runs")) / games,
        home_runs_per_game=_to_float(hitting.get("homeRuns")) / games,
        strikeout_rate=_to_float(hitting.get("strikeOuts")) / pa,
        walk_rate=_to_float(hitting.get("baseOnBalls")) / pa,
        stolen_bases_per_game=_to_float(hitting.get("stolenBases")) / games,
        left_on_base_per_game=_to_float(hitting.get("leftOnBase")) / games,
        pitching_era=_to_float(pitching.get("era"), 4.5),
        pitching_whip=_to_float(pitching.get("whip"), 1.3),
        pitching_avg_allowed=_to_float(pitching.get("avg")),
        pitching_obp_allowed=_to_float(pitching.get("obp")),
        pitching_slg_allowed=_to_float(pitching.get("slg")),
        pitching_ops_allowed=_to_float(pitching.get("ops")),
        strikeouts_per_9=_to_float(pitching.get("strikeoutsPer9Inn")),
        walks_per_9=_to_float(pitching.get("walksPer9Inn")),
        hits_per_9=_to_float(pitching.get("hitsPer9Inn")),
        home_runs_per_9=(_to_float(pitching.get("homeRuns")) / pitching_games) * 9 / 9,
    )
