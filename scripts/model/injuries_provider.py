"""Optional injury counts by team (ported from mlb-predictor-dashboard)."""

from __future__ import annotations

import json
import os
import ssl
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

import certifi
from mlb_api import load_team_abbreviations

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "injuries"
CACHE_TTL_HOURS = 6

# MLB Stats API team id -> common display name fragments for injury feed matching
_TEAM_NAME_HINTS: dict[int, list[str]] = {
    108: ["Angels", "Los Angeles Angels", "LAA"],
    109: ["Diamondbacks", "Arizona"],
    110: ["Orioles", "Baltimore"],
    111: ["Red Sox", "Boston"],
    112: ["Cubs", "Chicago Cubs"],
    113: ["Reds", "Cincinnati"],
    114: ["Guardians", "Cleveland"],
    115: ["Rockies", "Colorado"],
    116: ["Tigers", "Detroit"],
    117: ["Astros", "Houston"],
    118: ["Royals", "Kansas City"],
    119: ["Dodgers", "Los Angeles Dodgers"],
    120: ["Nationals", "Washington"],
    121: ["Mets", "New York Mets"],
    133: ["Athletics", "Oakland", "A's"],
    134: ["Pirates", "Pittsburgh"],
    135: ["Padres", "San Diego"],
    136: ["Mariners", "Seattle"],
    137: ["Giants", "San Francisco"],
    138: ["Cardinals", "St. Louis"],
    139: ["Rays", "Tampa Bay"],
    140: ["Rangers", "Texas"],
    141: ["Blue Jays", "Toronto"],
    142: ["Twins", "Minnesota"],
    143: ["Phillies", "Philadelphia"],
    144: ["Braves", "Atlanta"],
    145: ["White Sox", "Chicago White Sox"],
    146: ["Marlins", "Miami"],
    147: ["Yankees", "New York Yankees"],
    158: ["Brewers", "Milwaukee"],
}


def _cache_path(snapshot_date: date) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"injuries_{snapshot_date.isoformat()}.json"


def _load_cache(snapshot_date: date) -> dict[str, int] | None:
    path = _cache_path(snapshot_date)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
        cached_at = payload.get("cached_at")
        if not cached_at:
            return payload.get("counts")
        from datetime import datetime

        age = datetime.utcnow() - datetime.fromisoformat(cached_at)
        if age > timedelta(hours=CACHE_TTL_HOURS):
            return None
        return payload.get("counts")
    except (json.JSONDecodeError, ValueError):
        return None


def _save_cache(snapshot_date: date, counts: dict[str, int]) -> None:
    from datetime import datetime

    _cache_path(snapshot_date).write_text(
        json.dumps({"cached_at": datetime.utcnow().isoformat(), "counts": counts}, indent=2)
    )


def _fetch_balldontlie(api_key: str) -> list[dict]:
    request = Request(
        "https://mlb.balldontlie.io/api/v1/player_injuries",
        headers={"Authorization": api_key},
    )
    context = ssl.create_default_context(cafile=certifi.where())
    with urlopen(request, timeout=20, context=context) as response:
        payload = json.load(response)
    return list(payload.get("data") or [])


def _normalize_team_name(value: object) -> str:
    return str(value or "").strip().lower()


def _team_matches(team_name: str, hints: list[str]) -> bool:
    normalized = _normalize_team_name(team_name)
    if not normalized:
        return False
    return any(hint.lower() in normalized or normalized in hint.lower() for hint in hints)


def injury_counts_by_team_id(snapshot_date: date | None = None) -> dict[int, int]:
    """Return active injury counts keyed by MLB team id."""
    snapshot_date = snapshot_date or date.today()
    zero = {team_id: 0 for team_id in _TEAM_NAME_HINTS}
    if snapshot_date < date.today():
        return zero
    cached = _load_cache(snapshot_date)
    if cached is not None:
        return {int(key): int(value) for key, value in cached.items()}

    api_key = (os.getenv("BALLDONTLIE_API_KEY") or "").strip()
    counts = {team_id: 0 for team_id in _TEAM_NAME_HINTS}
    if not api_key:
        return counts

    try:
        rows = _fetch_balldontlie(api_key)
    except Exception:
        return counts

    for item in rows:
        team = item.get("team") or {}
        team_name = team.get("full_name") or team.get("name") or item.get("team")
        for team_id, hints in _TEAM_NAME_HINTS.items():
            if _team_matches(str(team_name), hints):
                counts[team_id] = counts.get(team_id, 0) + 1
                break

    _save_cache(snapshot_date, {str(team_id): count for team_id, count in counts.items()})
    return counts


def injury_counts_for_game(
    home_team_id: int,
    away_team_id: int,
    snapshot_date: date | None = None,
) -> tuple[int, int]:
    counts = injury_counts_by_team_id(snapshot_date)
    return counts.get(home_team_id, 0), counts.get(away_team_id, 0)
