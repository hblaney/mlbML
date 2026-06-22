"""Point-in-time bullpen (relief pitching) signal from per-game boxscores.

The MLB Stats API exposes a clean starter/reliever split, but only as season totals
(byDateRange ignores the reliever filter; statSplits ignores the date range), which
would leak future games into a historical backtest. To get a leakage-safe reliever
signal that works identically in training and live, we aggregate relief lines from
each game's boxscore (pitchers with gamesStarted==0) and sum only games strictly
before the prediction date.

NEGATIVE RESULT (Jun 2026): wiring reliever ERA/WHIP/3-day workload into feature_row
produced exactly 0.0000 GBM importance for all 9 columns — the shallow tree never
split on them. Team season pitching ERA/WHIP (already in the model) appears to absorb
the bullpen contribution, and starter ERA differential dominates (44% of importance).
So the bullpen features were NOT shipped. This provider is retained as reusable,
leakage-safe tooling (and the boxscore cache stays warm) for future game-state ideas
(e.g. late-inning win-prob, leverage-weighted reliever quality).

Exposes:
  bullpen_stats_as_of(team_id, game_date) -> BullpenSnapshot
    .era          season-to-date reliever ERA (league-avg fallback early)
    .whip         season-to-date reliever WHIP
    .fatigue_ip3  relief innings thrown in the 3 days before the game (workload)
"""

from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.request import urlopen

import certifi

from mlb_api import load_or_fetch_games

API_BASE = "https://statsapi.mlb.com/api/v1"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
BOX_DIR = CACHE_DIR / "boxscore_bullpen"

LEAGUE_AVG_PEN_ERA = 4.10
LEAGUE_AVG_PEN_WHIP = 1.32
MIN_IP_FOR_RATE = 15.0  # below this, blend toward league average

# season -> {team_id: [ (date, ip, er, h, bb), ... ] sorted by date}
_SEASON_INDEX: dict[int, dict[int, list[tuple[date, float, float, float, float]]]] = {}


@dataclass(frozen=True)
class BullpenSnapshot:
    era: float
    whip: float
    fatigue_ip3: float


def _parse_ip(value: object) -> float:
    if value in (None, ""):
        return 0.0
    text = str(value)
    if "." in text:
        whole, frac = text.split(".", 1)
        try:
            return float(whole) + float(frac) / 3.0
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _game_bullpen_lines(game_pk: int) -> dict[int, dict[str, float]]:
    """Per-team reliever totals for one game. Cached per game_pk."""
    BOX_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = BOX_DIR / f"{game_pk}.json"
    if cache_path.exists():
        try:
            raw = json.loads(cache_path.read_text())
            return {int(k): v for k, v in raw.items()}
        except json.JSONDecodeError:
            cache_path.unlink(missing_ok=True)

    context = ssl.create_default_context(cafile=certifi.where())
    url = f"{API_BASE}/game/{game_pk}/boxscore"
    try:
        with urlopen(url, timeout=30, context=context) as response:
            box = json.load(response)
    except Exception:
        return {}

    result: dict[int, dict[str, float]] = {}
    for side in ("home", "away"):
        team = box.get("teams", {}).get(side, {})
        team_id = team.get("team", {}).get("id")
        if team_id is None:
            continue
        ip = er = h = bb = 0.0
        players = team.get("players", {})
        for pid in team.get("pitchers", []):
            pdata = players.get(f"ID{pid}", {})
            ps = pdata.get("stats", {}).get("pitching", {})
            if not ps:
                continue
            # Starter has gamesStarted == 1; everyone else is a reliever.
            if int(ps.get("gamesStarted", 0) or 0) == 1:
                continue
            ip += _parse_ip(ps.get("inningsPitched"))
            er += float(ps.get("earnedRuns", 0) or 0)
            h += float(ps.get("hits", 0) or 0)
            bb += float(ps.get("baseOnBalls", 0) or 0)
        result[int(team_id)] = {"ip": ip, "er": er, "h": h, "bb": bb}

    cache_path.write_text(json.dumps(result))
    return result


def _season_bounds(game_date: date) -> tuple[int, date, date]:
    season = game_date.year
    start = date(season, 3, 1)
    if game_date < start:
        season -= 1
        start = date(season, 3, 1)
    end = min(game_date, date.today() - timedelta(days=1))
    return season, start, end


def _season_index(season: int, start: date, end: date) -> dict[int, list[tuple[date, float, float, float, float]]]:
    if season in _SEASON_INDEX:
        return _SEASON_INDEX[season]

    games = load_or_fetch_games(start, end)
    index: dict[int, list[tuple[date, float, float, float, float]]] = {}
    for game in games:
        if not game.is_final:
            continue
        lines = _game_bullpen_lines(game.game_pk)
        for team_id, line in lines.items():
            index.setdefault(team_id, []).append(
                (game.game_date, line["ip"], line["er"], line["h"], line["bb"])
            )
    for team_id in index:
        index[team_id].sort(key=lambda row: row[0])
    _SEASON_INDEX[season] = index
    return index


def bullpen_stats_as_of(team_id: int, game_date: date) -> BullpenSnapshot:
    season, start, end = _season_bounds(game_date)
    index = _season_index(season, start, end)
    rows = index.get(team_id, [])

    ip = er = h = bb = 0.0
    fatigue = 0.0
    fatigue_cutoff = game_date - timedelta(days=3)
    for d, gip, ger, gh, gbb in rows:
        if d >= game_date:
            break
        ip += gip
        er += ger
        h += gh
        bb += gbb
        if d >= fatigue_cutoff:
            fatigue += gip

    if ip < MIN_IP_FOR_RATE:
        # Blend the thin sample toward league average so early-season noise is damped.
        w = ip / MIN_IP_FOR_RATE if ip > 0 else 0.0
        raw_era = (9.0 * er / ip) if ip > 0 else LEAGUE_AVG_PEN_ERA
        raw_whip = ((h + bb) / ip) if ip > 0 else LEAGUE_AVG_PEN_WHIP
        era = w * raw_era + (1 - w) * LEAGUE_AVG_PEN_ERA
        whip = w * raw_whip + (1 - w) * LEAGUE_AVG_PEN_WHIP
    else:
        era = 9.0 * er / ip
        whip = (h + bb) / ip

    era = max(1.5, min(9.0, era))
    whip = max(0.7, min(2.5, whip))
    return BullpenSnapshot(era=round(era, 4), whip=round(whip, 4), fatigue_ip3=round(fatigue, 2))


if __name__ == "__main__":
    import sys

    d = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    for tid in (147, 119, 111):
        s = bullpen_stats_as_of(tid, d)
        print(f"team {tid}: ERA {s.era}  WHIP {s.whip}  fatigue_ip3 {s.fatigue_ip3}")
