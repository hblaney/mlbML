"""Fetch MLB schedule and team metadata from the public Stats API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.request import urlopen

API_BASE = "https://statsapi.mlb.com/api/v1"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
_PITCHER_STATS_CACHE: dict[tuple[int, int], dict[str, float]] = {}


@dataclass(frozen=True)
class GameRecord:
    game_pk: int
    game_date: date
    game_datetime_iso: str
    home_team_id: int
    away_team_id: int
    home_score: int | None
    away_score: int | None
    home_pitcher_id: int | None
    away_pitcher_id: int | None
    home_pitcher_name: str | None = None
    away_pitcher_name: str | None = None
    is_final: bool = True

    @property
    def home_won(self) -> bool:
        if self.home_score is None or self.away_score is None:
            raise ValueError("Cannot determine winner for an unfinished game.")
        return self.home_score > self.away_score


def _get_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=30) as response:
        return json.load(response)


def load_team_abbreviations() -> dict[int, str]:
    payload = _get_json(f"{API_BASE}/teams?sportId=1&season={date.today().year}")
    return {team["id"]: team["abbreviation"] for team in payload["teams"]}


def load_team_names() -> dict[int, str]:
    payload = _get_json(f"{API_BASE}/teams?sportId=1&season={date.today().year}")
    return {team["id"]: team["name"] for team in payload["teams"]}


def _parse_game(game: dict[str, Any], *, final_only: bool, schedule_date: date) -> GameRecord | None:
    status = game.get("status", {}).get("abstractGameState")
    if final_only and status != "Final":
        return None

    home = game["teams"]["home"]
    away = game["teams"]["away"]
    home_pitcher = home.get("probablePitcher") or {}
    away_pitcher = away.get("probablePitcher") or {}

    return GameRecord(
        game_pk=game["gamePk"],
        game_date=schedule_date,
        game_datetime_iso=game["gameDate"],
        home_team_id=home["team"]["id"],
        away_team_id=away["team"]["id"],
        home_score=home.get("score"),
        away_score=away.get("score"),
        home_pitcher_id=home_pitcher.get("id"),
        away_pitcher_id=away_pitcher.get("id"),
        home_pitcher_name=home_pitcher.get("fullName"),
        away_pitcher_name=away_pitcher.get("fullName"),
        is_final=status == "Final",
    )


def fetch_games(start: date, end: date, *, final_only: bool = True) -> list[GameRecord]:
    games: list[GameRecord] = []
    cursor = start

    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=6), end)
        url = (
            f"{API_BASE}/schedule?sportId=1&gameType=R"
            f"&startDate={cursor.isoformat()}&endDate={chunk_end.isoformat()}"
            "&hydrate=probablePitcher"
        )
        payload = _get_json(url)

        for day in payload.get("dates", []):
            schedule_date = date.fromisoformat(day["date"])
            for game in day.get("games", []):
                parsed = _parse_game(game, final_only=final_only, schedule_date=schedule_date)
                if parsed is None:
                    continue
                if final_only and (parsed.home_score is None or parsed.away_score is None):
                    continue
                games.append(parsed)

        cursor = chunk_end + timedelta(days=1)

    games.sort(key=lambda item: (item.game_date, item.game_pk))
    return games


def load_or_fetch_games(start: date, end: date) -> list[GameRecord]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"games_v2_{start.isoformat()}_{end.isoformat()}.json"

    if cache_path.exists():
        raw = json.loads(cache_path.read_text())
        return [
            GameRecord(
                game_pk=item["game_pk"],
                game_date=date.fromisoformat(item["game_date"]),
                game_datetime_iso=item.get("game_datetime_iso", item["game_date"]),
                home_team_id=item["home_team_id"],
                away_team_id=item["away_team_id"],
                home_score=item["home_score"],
                away_score=item["away_score"],
                home_pitcher_id=item.get("home_pitcher_id"),
                away_pitcher_id=item.get("away_pitcher_id"),
                home_pitcher_name=item.get("home_pitcher_name"),
                away_pitcher_name=item.get("away_pitcher_name"),
                is_final=item.get("is_final", True),
            )
            for item in raw
        ]

    games = fetch_games(start, end)
    cache_path.write_text(
        json.dumps(
            [
                {
                    "game_pk": game.game_pk,
                    "game_date": game.game_date.isoformat(),
                    "game_datetime_iso": game.game_datetime_iso,
                    "home_team_id": game.home_team_id,
                    "away_team_id": game.away_team_id,
                    "home_score": game.home_score,
                    "away_score": game.away_score,
                    "home_pitcher_id": game.home_pitcher_id,
                    "away_pitcher_id": game.away_pitcher_id,
                    "home_pitcher_name": game.home_pitcher_name,
                    "away_pitcher_name": game.away_pitcher_name,
                    "is_final": game.is_final,
                }
                for game in games
            ],
            indent=2,
        )
    )
    return games


def fetch_upcoming_games(start: date, end: date) -> list[GameRecord]:
    return fetch_games(start, end, final_only=False)


def _to_float(value: object, default: float) -> float:
    if value in (None, "", "-.--"):
        return default
    try:
        return float(str(value))
    except ValueError:
        return default


def fetch_pitcher_season_stats(pitcher_id: int, season: int) -> dict[str, float]:
    memory_key = (pitcher_id, season)
    if memory_key in _PITCHER_STATS_CACHE:
        return _PITCHER_STATS_CACHE[memory_key]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"pitcher_stats_v2_{pitcher_id}_{season}.json"
    if cache_path.exists():
        stats = json.loads(cache_path.read_text())
        _PITCHER_STATS_CACHE[memory_key] = stats
        return stats

    url = (
        f"{API_BASE}/people/{pitcher_id}/stats"
        f"?stats=season&group=pitching&season={season}"
    )
    payload = _get_json(url)
    splits = payload.get("stats", [{}])[0].get("splits", [])
    stats = {
        "era": 4.5,
        "whip": 1.3,
        "avg_allowed": 0.250,
        "obp_allowed": 0.320,
        "slg_allowed": 0.400,
        "ops_allowed": 0.720,
        "strikeouts_per_9": 8.0,
        "walks_per_9": 3.0,
        "hits_per_9": 8.5,
        "home_runs_per_9": 1.1,
        "innings_pitched": 0.0,
        "games_started": 0.0,
    }
    if splits:
        raw = splits[0].get("stat", {})
        stats = {
            "era": _to_float(raw.get("era"), stats["era"]),
            "whip": _to_float(raw.get("whip"), stats["whip"]),
            "avg_allowed": _to_float(raw.get("avg"), stats["avg_allowed"]),
            "obp_allowed": _to_float(raw.get("obp"), stats["obp_allowed"]),
            "slg_allowed": _to_float(raw.get("slg"), stats["slg_allowed"]),
            "ops_allowed": _to_float(raw.get("ops"), stats["ops_allowed"]),
            "strikeouts_per_9": _to_float(raw.get("strikeoutsPer9Inn"), stats["strikeouts_per_9"]),
            "walks_per_9": _to_float(raw.get("walksPer9Inn"), stats["walks_per_9"]),
            "hits_per_9": _to_float(raw.get("hitsPer9Inn"), stats["hits_per_9"]),
            "home_runs_per_9": _to_float(raw.get("homeRunsPer9"), stats["home_runs_per_9"]),
            "innings_pitched": _to_float(raw.get("inningsPitched"), stats["innings_pitched"]),
            "games_started": _to_float(raw.get("gamesStarted"), stats["games_started"]),
        }

    cache_path.write_text(json.dumps(stats))
    _PITCHER_STATS_CACHE[memory_key] = stats
    return stats


def fetch_pitcher_season_era(pitcher_id: int, season: int) -> float:
    return fetch_pitcher_season_stats(pitcher_id, season)["era"]
