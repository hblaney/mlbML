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


def projected_lineup(team_id: int, game_date: date) -> list[int]:
    """OPS-ranked 9-man lineup when a confirmed batting order isn't posted yet."""
    roster = _active_roster_ids(team_id, game_date.year)
    scored: list[tuple[int, float, float]] = []
    for pid, _name in roster:
        stats = hitter_stats_as_of(pid, game_date)
        pa = float(stats.get("plate_appearances", 0.0))
        ops = float(stats.get("ops", 0.0))
        # Prefer real hitters; allow thin samples so we can still fill 9.
        if pa < 5 and ops <= 0:
            continue
        scored.append((pid, ops, pa))
    scored.sort(key=lambda row: (-row[1], -row[2]))
    ids = [pid for pid, _ops, _pa in scored[:9]]
    # Pad with remaining roster if OPS filter was too strict.
    if len(ids) < 9:
        for pid, _name in roster:
            if pid not in ids:
                ids.append(pid)
            if len(ids) >= 9:
                break
    return ids[:9]


# Expected plate appearances per lineup slot for a 9-inning game (leadoff bats most).
# Empirically stable: ~4.6 for the top of the order down to ~3.7 for the 9-hole.
_SLOT_PA = {
    1: 4.65, 2: 4.55, 3: 4.44, 4: 4.34, 5: 4.23,
    6: 4.12, 7: 4.00, 8: 3.88, 9: 3.76,
}
DEFAULT_SLOT_PA = 4.15


def expected_pa_for_slot(slot: int | None) -> float:
    if not slot or slot < 1 or slot > 9:
        return DEFAULT_SLOT_PA
    return _SLOT_PA[slot]


@lru_cache(maxsize=64)
def _boxscore(game_pk: int) -> dict:
    if not game_pk:
        return {}
    url = f"{API_BASE}/game/{game_pk}/boxscore"
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(url, timeout=30, context=context) as response:
            return json.load(response)
    except Exception:
        return {}


def confirmed_lineup_by_team(game_pk: int) -> dict[int, list[int]]:
    """{team_id: [player_ids in batting order]} once a lineup is posted."""
    box = _boxscore(game_pk)
    out: dict[int, list[int]] = {}
    for side in ("home", "away"):
        team = box.get("teams", {}).get(side, {})
        team_id = team.get("team", {}).get("id")
        order = team.get("battingOrder", []) or []
        if team_id is None or not order:
            continue
        ids: list[int] = []
        for pid in order[:9]:
            try:
                ids.append(int(pid))
            except (TypeError, ValueError):
                continue
        out[int(team_id)] = ids
    return out


def confirmed_lineup(game_pk: int) -> dict[int, int]:
    """Map player_id -> batting-order slot (1..9) once a lineup is posted.

    Returns an empty dict when lineups aren't out yet, so callers fall back to
    OPS-ranked featured hitters + default PAs.
    """
    out: dict[int, int] = {}
    for ids in confirmed_lineup_by_team(game_pk).values():
        for idx, pid in enumerate(ids):
            out[pid] = idx + 1
    return out


def expected_pa_for_player(player_id: int, lineup_slots: dict[int, int]) -> float:
    """Batting-order-aware expected PAs, falling back to a neutral default."""
    return expected_pa_for_slot(lineup_slots.get(int(player_id)))
