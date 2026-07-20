"""Real MLB player-prop lines from The Odds API.

This is the keystone of the honest prop predictor: instead of inventing a line
(fair value minus a cushion) and then "beating" it, we pull the ACTUAL lines and
two-sided prices that sportsbooks post — the same numbers PrizePicks tracks — then
de-vig them into a true market probability for each prop.

For every upcoming MLB event we fetch player-prop markets from the US books,
remove the vig on each two-sided market, and aggregate a consensus line + implied
P(over) across books. We also resolve each player to their MLB id + team so the
projection engine can look up their stats and matchup.

Set ODDS_API_KEY. Results cache to data/cache/prop_odds/{date}.json.
"""

from __future__ import annotations

import json
import os
import ssl
import time
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import certifi

from mlb_api import load_team_abbreviations, load_team_names

ODDS_API_BASE = "https://api.the-odds-api.com/v4/sports/baseball_mlb"
MLB_API_BASE = "https://statsapi.mlb.com/api/v1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "prop_odds"
CACHE_TTL_SECONDS = int(os.getenv("PROP_ODDS_TTL_SECONDS", "10800"))  # 3h

# Prop markets we pull. Keys are The Odds API market keys.
HITTER_MARKETS = [
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "batter_rbis",
    "batter_runs_scored",
    "batter_walks",
    "batter_stolen_bases",
    "batter_singles",
    "batter_doubles",
    "batter_hits_runs_rbis",
]
PITCHER_MARKETS = [
    "pitcher_strikeouts",
    "pitcher_outs",
    "pitcher_earned_runs",
    "pitcher_hits_allowed",
]
ALL_MARKETS = HITTER_MARKETS + PITCHER_MARKETS

# Odds API / MLB / board abbreviations don't always agree (Athletics, etc.).
_TEAM_ABBR_ALIASES = {
    "ATH": "OAK",
    "OAK": "OAK",
    "AZ": "ARI",
    "ARI": "ARI",
    "CWS": "CHW",
    "CHW": "CHW",
    "TB": "TB",
    "TBR": "TB",
    "SF": "SF",
    "SFG": "SF",
    "KC": "KC",
    "KCR": "KC",
    "SD": "SD",
    "SDP": "SD",
    "WSH": "WSH",
    "WAS": "WSH",
}


def _norm_abbr(abbr: str | None) -> str:
    if not abbr:
        return ""
    return _TEAM_ABBR_ALIASES.get(str(abbr).upper(), str(abbr).upper())


def _same_team(a: str | None, b: str | None) -> bool:
    return bool(a and b and _norm_abbr(a) == _norm_abbr(b))


def _load_env_file() -> None:
    for env_path in (PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.local"):
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _ctx() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def _get_json(url: str, *, timeout: int = 30):
    with urlopen(url, timeout=timeout, context=_ctx()) as response:
        return json.load(response), dict(response.headers)


def _norm_name(name: str) -> str:
    """Accent- and punctuation-insensitive key for matching player names."""
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = "".join(c for c in ascii_name.lower() if c.isalnum() or c == " ")
    return " ".join(cleaned.split())


def _implied(american: float) -> float:
    if american == 0:
        return 0.0
    if american < 0:
        return abs(american) / (abs(american) + 100.0)
    return 100.0 / (american + 100.0)


@dataclass
class PropLine:
    event_id: str
    commence_time: str
    game_id: str | None          # board-style {away}-{home}-{date}-{pk} if resolvable
    home_abbr: str
    away_abbr: str
    player: str
    player_id: int | None
    team_abbr: str | None
    is_home: bool | None
    opp_abbr: str | None
    prop: str                    # Odds API market key
    line: float                  # consensus point
    over_price: int              # consensus american
    under_price: int             # consensus american
    market_prob_over: float      # de-vigged consensus P(over)
    book_count: int


def _roster_name_map(team_id: int, team_abbr: str, season: int) -> dict[str, tuple[int, str]]:
    """{normalized full name: (player_id, team_abbr)} for a team's active roster."""
    url = f"{MLB_API_BASE}/teams/{team_id}/roster?rosterType=active&season={season}"
    try:
        payload, _ = _get_json(url)
    except Exception:
        return {}
    out: dict[str, tuple[int, str]] = {}
    for row in payload.get("roster", []):
        person = row.get("person", {})
        pid = person.get("id")
        name = person.get("fullName")
        if pid and name:
            out[_norm_name(name)] = (int(pid), team_abbr)
    return out


def _devig_two_sided(over_prices: list[int], under_prices: list[int]) -> float | None:
    """Average de-vigged P(over) across books that priced both sides."""
    probs: list[float] = []
    for over, under in zip(over_prices, under_prices):
        io, iu = _implied(over), _implied(under)
        total = io + iu
        if total > 0:
            probs.append(io / total)
    if not probs:
        return None
    return sum(probs) / len(probs)


def _consensus_american(prices: list[int]) -> int:
    goods = [p for p in prices if p]
    if not goods:
        return 0
    # median is robust to a single off book
    goods.sort()
    mid = len(goods) // 2
    if len(goods) % 2:
        return goods[mid]
    return int(round((goods[mid - 1] + goods[mid]) / 2))


def _median_line(points: list[float]) -> float:
    pts = sorted(points)
    mid = len(pts) // 2
    if len(pts) % 2:
        return pts[mid]
    return (pts[mid - 1] + pts[mid]) / 2


def _fetch_events(api_key: str) -> list[dict]:
    url = f"{ODDS_API_BASE}/events?{urlencode({'apiKey': api_key})}"
    events, _ = _get_json(url)
    return events


def _fetch_event_props(api_key: str, event_id: str, markets: list[str]) -> dict:
    params = urlencode(
        {
            "apiKey": api_key,
            "regions": os.getenv("ODDS_REGIONS", "us"),
            "markets": ",".join(markets),
            "oddsFormat": "american",
        }
    )
    data, headers = _get_json(f"{ODDS_API_BASE}/events/{event_id}/odds?{params}")
    return {"data": data, "remaining": headers.get("x-requests-remaining")}


def _cache_path(day_iso: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{day_iso}.json"


def _read_cache(day_iso: str, max_age: int) -> list[PropLine] | None:
    path = _cache_path(day_iso)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except Exception:
        return None
    if time.time() - float(payload.get("fetched_at", 0)) > max_age:
        return None
    return [PropLine(**row) for row in payload.get("lines", [])]


def _write_cache(day_iso: str, lines: list[PropLine]) -> None:
    path = _cache_path(day_iso)
    path.write_text(
        json.dumps(
            {"fetched_at": time.time(), "day": day_iso, "lines": [asdict(l) for l in lines]},
            indent=2,
        )
    )


def fetch_prop_lines(*, force_refresh: bool = False, max_events: int | None = None) -> list[PropLine]:
    """Fetch real, de-vigged player-prop lines for today's upcoming games."""
    day_iso = date.today().isoformat()
    if not force_refresh:
        cached = _read_cache(day_iso, CACHE_TTL_SECONDS)
        if cached is not None:
            return cached

    _load_env_file()
    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        print("prop_odds: ODDS_API_KEY not set")
        return []

    try:
        events = _fetch_events(api_key)
    except Exception as error:
        print(f"prop_odds: events fetch failed: {error}")
        cached = _read_cache(day_iso, 7 * 24 * 3600)
        return cached or []

    now = datetime.now(timezone.utc)
    upcoming = [
        e for e in events
        if datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) > now
    ]
    upcoming.sort(key=lambda e: e["commence_time"])
    if max_events:
        upcoming = upcoming[:max_events]

    season = date.today().year
    try:
        id_by_name = {v: k for k, v in load_team_names().items()}
        abbr_by_id = load_team_abbreviations()
    except Exception:
        id_by_name, abbr_by_id = {}, {}

    lines: list[PropLine] = []
    for event in upcoming:
        home_name = event.get("home_team", "")
        away_name = event.get("away_team", "")
        home_id = id_by_name.get(home_name)
        away_id = id_by_name.get(away_name)
        home_abbr = abbr_by_id.get(home_id, home_name[:3].upper())
        away_abbr = abbr_by_id.get(away_id, away_name[:3].upper())

        # Player -> (id, team_abbr) via both rosters (for stat lookups + team assignment).
        roster: dict[str, tuple[int, str]] = {}
        if home_id:
            roster.update(_roster_name_map(home_id, home_abbr, season))
        if away_id:
            roster.update(_roster_name_map(away_id, away_abbr, season))

        try:
            result = _fetch_event_props(api_key, event["id"], ALL_MARKETS)
        except HTTPError as error:
            if error.code == 422:  # market not available for this event
                continue
            print(f"prop_odds: props HTTP {error.code} for {away_abbr}@{home_abbr}")
            continue
        except Exception as error:
            print(f"prop_odds: props fetch failed for {away_abbr}@{home_abbr}: {error}")
            continue

        # Collect prices per (player, prop, point) across books.
        agg: dict[tuple[str, str, float], dict[str, list]] = {}
        for book in result["data"].get("bookmakers", []):
            for market in book.get("markets", []):
                mkey = market.get("key")
                if mkey not in ALL_MARKETS:
                    continue
                sides: dict[tuple[str, float], dict[str, int]] = {}
                for outcome in market.get("outcomes", []):
                    player = outcome.get("description") or outcome.get("name")
                    point = outcome.get("point")
                    name = outcome.get("name")
                    price = outcome.get("price")
                    if player is None or point is None or price is None:
                        continue
                    slot = sides.setdefault((player, float(point)), {})
                    if name == "Over":
                        slot["over"] = int(price)
                    elif name == "Under":
                        slot["under"] = int(price)
                for (player, point), slot in sides.items():
                    key = (player, mkey, float(point))
                    bucket = agg.setdefault(key, {"over": [], "under": []})
                    if "over" in slot and "under" in slot:
                        bucket["over"].append(slot["over"])
                        bucket["under"].append(slot["under"])

        # For each player+prop, pick the modal line and de-vig.
        by_player_prop: dict[tuple[str, str], list[tuple[float, dict]]] = {}
        for (player, mkey, point), bucket in agg.items():
            by_player_prop.setdefault((player, mkey), []).append((point, bucket))

        for (player, mkey), point_rows in by_player_prop.items():
            # Prefer the line with the most two-sided books.
            point_rows.sort(key=lambda r: len(r[1]["over"]), reverse=True)
            point, bucket = point_rows[0]
            prob_over = _devig_two_sided(bucket["over"], bucket["under"])
            if prob_over is None:
                continue
            pid_team = roster.get(_norm_name(player))
            player_id = pid_team[0] if pid_team else None
            team_abbr = pid_team[1] if pid_team else None
            is_home = _same_team(team_abbr, home_abbr) if team_abbr else None
            opp_abbr = None
            if team_abbr:
                if is_home:
                    opp_abbr = away_abbr
                elif _same_team(team_abbr, away_abbr):
                    opp_abbr = home_abbr
                    is_home = False
                else:
                    # Unresolved alias mismatch — leave is_home None so generator
                    # does not invent the wrong opposing pitcher.
                    is_home = None
            lines.append(
                PropLine(
                    event_id=event["id"],
                    commence_time=event["commence_time"],
                    game_id=None,
                    home_abbr=home_abbr,
                    away_abbr=away_abbr,
                    player=player,
                    player_id=player_id,
                    team_abbr=team_abbr,
                    is_home=is_home,
                    opp_abbr=opp_abbr,
                    prop=mkey,
                    line=float(point),
                    over_price=_consensus_american(bucket["over"]),
                    under_price=_consensus_american(bucket["under"]),
                    market_prob_over=round(prob_over, 4),
                    book_count=len(bucket["over"]),
                )
            )

    if lines:
        _write_cache(day_iso, lines)
    return lines


def main() -> None:
    lines = fetch_prop_lines(force_refresh=True)
    by_prop: dict[str, int] = {}
    resolved = 0
    for l in lines:
        by_prop[l.prop] = by_prop.get(l.prop, 0) + 1
        if l.player_id:
            resolved += 1
    print(f"prop_odds_ok lines={len(lines)} resolved_players={resolved}")
    for prop in sorted(by_prop):
        print(f"  {prop:24s} {by_prop[prop]}")
    for l in lines[:8]:
        print(
            f"   {l.player:22s} {l.team_abbr or '??':3s} {l.prop:22s} "
            f"line={l.line:<5} P(over)={l.market_prob_over:.3f} books={l.book_count}"
        )


if __name__ == "__main__":
    main()
