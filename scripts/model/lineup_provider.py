"""Featured hitters per team for prop slips (top OPS, leakage-safe)."""

from __future__ import annotations

import json
import ssl
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.request import urlopen

import certifi

from hitter_stats_provider import hitter_stats_as_of

API_BASE = "https://statsapi.mlb.com/api/v1"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "team_rosters"
TOP_N = 4


@lru_cache(maxsize=64)
def _active_roster_ids(team_id: int, season: int) -> list[tuple[int, str]]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{team_id}_{season}.json"
    if cache_path.exists():
        try:
            rows = json.loads(cache_path.read_text())
            return [(int(r["id"]), r["name"]) for r in rows]
        except (json.JSONDecodeError, KeyError, ValueError):
            cache_path.unlink(missing_ok=True)

    url = f"{API_BASE}/teams/{team_id}/roster?rosterType=active&season={season}"
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(url, timeout=30, context=context) as response:
            payload = json.load(response)
    except Exception:
        return []

    rows = [
        {"id": p["person"]["id"], "name": p["person"]["fullName"]}
        for p in payload.get("roster", [])
        if p.get("person", {}).get("id")
    ]
    cache_path.write_text(json.dumps(rows))
    return [(int(r["id"]), r["name"]) for r in rows]


def featured_hitters(team_id: int, game_date: date, *, n: int = TOP_N) -> list[tuple[int, str, float]]:
    """Return top ``n`` hitters on ``team_id`` by OPS as of ``game_date``."""
    roster = _active_roster_ids(team_id, game_date.year)
    scored: list[tuple[int, str, float]] = []
    for pid, name in roster:
        stats = hitter_stats_as_of(pid, game_date)
        pa = stats.get("plate_appearances", 0.0)
        if pa < 20:
            continue
        scored.append((pid, name, float(stats.get("ops", 0.0))))
    scored.sort(key=lambda row: -row[2])
    return scored[:n]
