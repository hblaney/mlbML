"""Leakage-safe per-start lines from game boxscores (IP + ER for starters).

Schedule data only gives runs scored; boxscores give actual starter workload and
earned runs for point-in-time pitcher-vs-opponent ERA.
"""

from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.request import urlopen

import certifi

API_BASE = "https://statsapi.mlb.com/api/v1"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "boxscore_starters"


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


@dataclass(frozen=True)
class StarterLine:
    pitcher_id: int
    opponent_id: int
    innings_pitched: float
    earned_runs: float
    runs_allowed: int
    team_won: bool


def _fetch_boxscore(game_pk: int) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{game_pk}.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except json.JSONDecodeError:
            cache_path.unlink(missing_ok=True)

    context = ssl.create_default_context(cafile=certifi.where())
    url = f"{API_BASE}/game/{game_pk}/boxscore"
    try:
        with urlopen(url, timeout=30, context=context) as response:
            box = json.load(response)
    except Exception:
        payload = {"home_pitcher_id": None, "away_pitcher_id": None, "starters": {}}
        cache_path.write_text(json.dumps(payload))
        return payload

    home = box.get("teams", {}).get("home", {})
    away = box.get("teams", {}).get("away", {})
    home_id = home.get("team", {}).get("id")
    away_id = away.get("team", {}).get("id")
    home_score = int(home.get("teamStats", {}).get("batting", {}).get("runs", 0) or 0)
    away_score = int(away.get("teamStats", {}).get("batting", {}).get("runs", 0) or 0)

    starters: dict[str, dict[str, float]] = {}

    def _starter_for_side(side: dict, opponent_runs: int) -> tuple[int | None, dict[str, float] | None]:
        players = side.get("players", {})
        for pid in side.get("pitchers", []):
            pdata = players.get(f"ID{pid}", {})
            ps = pdata.get("stats", {}).get("pitching", {})
            if not ps:
                continue
            if int(ps.get("gamesStarted", 0) or 0) != 1:
                continue
            ip = _parse_ip(ps.get("inningsPitched"))
            if ip <= 0:
                continue
            pitcher_id = int(pid)
            return pitcher_id, {
                "ip": ip,
                "er": float(ps.get("earnedRuns", 0) or 0),
                "runs_allowed": float(opponent_runs),
            }
        return None, None

    home_pitcher, home_line = _starter_for_side(home, away_score)
    away_pitcher, away_line = _starter_for_side(away, home_score)

    payload = {
        "home_pitcher_id": home_pitcher,
        "away_pitcher_id": away_pitcher,
        "starters": {},
    }
    if home_pitcher and home_line:
        payload["starters"][str(home_pitcher)] = home_line
    if away_pitcher and away_line:
        payload["starters"][str(away_pitcher)] = away_line

    cache_path.write_text(json.dumps(payload))
    return payload


def starter_line_for_game(
    game_pk: int,
    pitcher_id: int | None,
    opponent_id: int,
    *,
    runs_allowed_fallback: int,
    team_won: bool,
) -> StarterLine | None:
    """Return the starter's boxscore line for this game, or None if unavailable."""
    if not pitcher_id:
        return None
    box = _fetch_boxscore(game_pk)
    raw = box.get("starters", {}).get(str(pitcher_id))
    if not raw:
        return StarterLine(
            pitcher_id=pitcher_id,
            opponent_id=opponent_id,
            innings_pitched=0.0,
            earned_runs=float(runs_allowed_fallback),
            runs_allowed=runs_allowed_fallback,
            team_won=team_won,
        )
    return StarterLine(
        pitcher_id=pitcher_id,
        opponent_id=opponent_id,
        innings_pitched=float(raw.get("ip", 0.0)),
        earned_runs=float(raw.get("er", 0.0)),
        runs_allowed=int(raw.get("runs_allowed", runs_allowed_fallback)),
        team_won=team_won,
    )


def prefetch_season(start: date, end: date) -> None:
    from mlb_api import load_or_fetch_games

    games = load_or_fetch_games(start, end)
    total = len(games)
    for i, game in enumerate(games, 1):
        if game.is_final:
            _fetch_boxscore(game.game_pk)
        if i % 250 == 0 or i == total:
            print(f"starter boxscores {i}/{total}", flush=True)
