"""Live PrizePicks MLB lines from partner-api.prizepicks.com.

PrizePicks tags a huge share of the real app board as ``goblin`` / ``demon``
with no ``standard`` row (star pitcher Ks, many hits/TB/HRR posts, etc.).
Filtering to ``standard`` alone drops most of the board.

Board rules:
  - Keep every ``standard`` line.
  - Keep ``goblin`` lines in per-prop starter/hitter bands (skip  junk  ladders).
  - If a (player, prop) has neither standard nor in-band goblin, keep the
    lowest in-band ``demon`` as a last-resort primary (never the 10.5+ juice).
"""

from __future__ import annotations

import json
import os
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / "data" / "cache" / "prizepicks"
CACHE_TTL = int(os.getenv("PRIZEPICKS_TTL_SECONDS", "1800"))  # 30m
MLB_LEAGUE_ID = 2
API_URL = "https://partner-api.prizepicks.com/projections"
CACHE_VERSION = 6  # ace K lines up to 11.5 (was capped at 8.5)

STAT_TO_PROP = {
    "Hits": "batter_hits",
    "Total Bases": "batter_total_bases",
    "Hits+Runs+RBIs": "batter_hits_runs_rbis",
    "Home Runs": "batter_home_runs",
    "RBIs": "batter_rbis",
    "Runs": "batter_runs_scored",
    "Walks": "batter_walks",
    "Stolen Bases": "batter_stolen_bases",
    "Singles": "batter_singles",
    "Doubles": "batter_doubles",
    "Pitcher Strikeouts": "pitcher_strikeouts",
    "Hits Allowed": "pitcher_hits_allowed",
    "Earned Runs Allowed": "pitcher_earned_runs",
    "Walks Allowed": "pitcher_walks",
}

# Goblin/demon lines outside these bands are junk ladders (1.5 K freebies,
# 12.5 K demons, etc.). Inside the band they ARE the app board.
LINE_BANDS: dict[str, tuple[float, float]] = {
    # Include ace ladders (Cole 9.5 / 10.5). Old 8.5 cap dropped those names entirely
    # when PrizePicks only posted the high goblin/demon K.
    "pitcher_strikeouts": (3.5, 11.5),
    "pitcher_hits_allowed": (2.5, 7.5),
    "pitcher_earned_runs": (0.5, 3.5),
    "pitcher_walks": (0.5, 2.5),
    "batter_hits": (0.5, 2.5),
    "batter_total_bases": (0.5, 3.5),
    "batter_hits_runs_rbis": (0.5, 3.5),
    "batter_singles": (0.5, 2.5),
    "batter_doubles": (0.5, 1.5),
    "batter_runs_scored": (0.5, 1.5),
    "batter_rbis": (0.5, 2.5),
    "batter_walks": (0.5, 2.5),
    "batter_stolen_bases": (0.5, 1.5),
    "batter_home_runs": (0.5, 1.5),
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://app.prizepicks.com/",
    "Origin": "https://app.prizepicks.com",
}


@dataclass
class PrizePicksLine:
    player: str
    team: str | None
    opponent: str | None
    prop: str
    prop_label: str
    line: float
    odds_type: str
    start_time: str
    game_id: str | None
    projection_id: str


def _norm_name(name: str) -> str:
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = "".join(c for c in ascii_name.lower() if c.isalnum() or c == " ")
    return " ".join(cleaned.split())


def _cache_path(day: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{day}.json"


def _in_band(prop: str, line: float) -> bool:
    band = LINE_BANDS.get(prop)
    if not band:
        return False
    lo, hi = band
    return lo <= line <= hi


def _parse_rows(data: dict) -> list[PrizePicksLine]:
    players: dict[str, dict] = {}
    for inc in data.get("included", []):
        if inc.get("type") == "new_player":
            players[inc["id"]] = inc.get("attributes") or {}

    lines: list[PrizePicksLine] = []
    for row in data.get("data", []):
        attrs = row.get("attributes") or {}
        odds_type = str(attrs.get("odds_type") or "")
        if odds_type not in ("standard", "goblin", "demon"):
            continue
        if attrs.get("is_live"):
            continue
        stat = attrs.get("stat_type") or attrs.get("stat_display_name")
        prop = STAT_TO_PROP.get(stat or "")
        if not prop:
            continue
        line_score = attrs.get("line_score")
        if line_score is None:
            continue
        rel = row.get("relationships") or {}
        pid = (rel.get("new_player") or {}).get("data") or {}
        player_id = pid.get("id")
        player = players.get(player_id or "", {})
        name = player.get("name") or player.get("display_name")
        if not name:
            continue
        lines.append(
            PrizePicksLine(
                player=name,
                team=player.get("team"),
                opponent=attrs.get("description"),
                prop=prop,
                prop_label=stat,
                line=float(line_score),
                odds_type=odds_type,
                start_time=str(attrs.get("start_time") or ""),
                game_id=str(attrs.get("game_id") or "") or None,
                projection_id=str(row.get("id") or ""),
            )
        )
    return lines


def _build_board(all_lines: list[PrizePicksLine]) -> list[PrizePicksLine]:
    """Standard + in-band goblin (+ demon fallback when nothing else)."""
    by_key: dict[tuple[str, str], list[PrizePicksLine]] = {}
    for line in all_lines:
        by_key.setdefault((_norm_name(line.player), line.prop), []).append(line)

    board: list[PrizePicksLine] = []
    seen: set[tuple[str, str, float, str]] = set()

    def _add(line: PrizePicksLine) -> None:
        key = (_norm_name(line.player), line.prop, float(line.line), line.odds_type)
        if key in seen:
            return
        seen.add(key)
        board.append(line)

    for _key, cands in by_key.items():
        standards = [c for c in cands if c.odds_type == "standard"]
        goblins = [
            c for c in cands
            if c.odds_type == "goblin" and _in_band(c.prop, c.line)
        ]
        demons = [
            c for c in cands
            if c.odds_type == "demon" and _in_band(c.prop, c.line)
        ]

        for line in standards:
            _add(line)
        for line in goblins:
            _add(line)

        # Last resort: no standard and no in-band goblin → lowest in-band demon.
        if not standards and not goblins and demons:
            _add(min(demons, key=lambda c: c.line))

    return board


def fetch_prizepicks_lines(
    *,
    odds_type: str = "standard",
    force_refresh: bool = False,
) -> list[PrizePicksLine]:
    """Return the full bettable PrizePicks board (not standard-only)."""
    del odds_type
    day = date.today().isoformat()
    path = _cache_path(day)
    if not force_refresh and path.exists():
        try:
            payload = json.loads(path.read_text())
            if (
                int(payload.get("cache_version") or 0) == CACHE_VERSION
                and time.time() - float(payload.get("fetched_at", 0)) <= CACHE_TTL
            ):
                return [PrizePicksLine(**row) for row in payload.get("lines", [])]
        except Exception:
            pass

    params = {"league_id": MLB_LEAGUE_ID, "per_page": 1000}
    try:
        resp = requests.get(API_URL, headers=HEADERS, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        if path.exists():
            try:
                payload = json.loads(path.read_text())
                print(f"prizepicks_cache_fallback reason={exc}")
                return [PrizePicksLine(**row) for row in payload.get("lines", [])]
            except Exception:
                pass
        raise

    parsed = _parse_rows(data)
    board = _build_board(parsed)
    path.write_text(
        json.dumps(
            {
                "fetched_at": time.time(),
                "cache_version": CACHE_VERSION,
                "raw_count": len(parsed),
                "count": len(board),
                "lines": [asdict(x) for x in board],
            },
            indent=2,
        )
    )
    print(
        f"prizepicks_board raw={len(parsed)} kept={len(board)} "
        f"std={sum(1 for l in board if l.odds_type=='standard')} "
        f"goblin={sum(1 for l in board if l.odds_type=='goblin')} "
        f"demon={sum(1 for l in board if l.odds_type=='demon')}"
    )
    return board


def index_by_player_prop(lines: list[PrizePicksLine]) -> dict[tuple[str, str], PrizePicksLine]:
    out: dict[tuple[str, str], PrizePicksLine] = {}
    for line in lines:
        out[(_norm_name(line.player), line.prop)] = line
    return out


if __name__ == "__main__":
    lines = fetch_prizepicks_lines(force_refresh=True)
    from collections import Counter

    print(f"prizepicks_ok count={len(lines)}")
    print("odds_type", Counter(l.odds_type for l in lines))
    print("props", Counter(l.prop for l in lines).most_common())
    for name in ("Jacob Misiorowski", "Fernando Tatis Jr.", "Bobby Witt Jr."):
        mine = [l for l in lines if l.player == name]
        print(name, [(l.prop, l.line, l.odds_type) for l in mine])
