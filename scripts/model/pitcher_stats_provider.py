"""Leakage-safe, point-in-time starting-pitcher stats.

The MLB Stats API `stats=season` endpoint returns a pitcher's FINAL full-season
line regardless of the date you ask about. Using it inside a historical feature
row is lookahead leakage: an April game would "know" the pitcher's end-of-season
ERA. Since starter ERA differential is the single most important feature in the
model (~44% of impurity importance), that leakage materially inflated backtests
and — worse — created a train/serve skew, because the live board can only ever
see season-to-date numbers.

This provider returns what was actually knowable before first pitch, using the
same `byDateRange` mechanism as `team_stats_provider`: current-season totals
through the day before the game, shrunk toward the pitcher's prior full season
(a leakage-free Bayesian prior) so early-season samples aren't dominated by a
handful of noisy starts. That both removes the leakage and gives better
early-season estimates than raw current-season-to-date.
"""

from __future__ import annotations

import json
import ssl
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import certifi

API_BASE = "https://statsapi.mlb.com/api/v1"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "pitcher_stats_asof"

# League-average-ish fallback when a pitcher has no current- or prior-season line
# (e.g. a debuting rookie). Matches the historical defaults used elsewhere.
_DEFAULTS: dict[str, float] = {
    "era": 4.35,
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

# Rate stats are shrunk toward the prior season with this many innings of prior weight.
# At 40 current-season IP the estimate is a 50/50 blend; by ~120 IP it is ~75% current.
PRIOR_IP_WEIGHT = 40.0

_RATE_KEYS = (
    "era",
    "whip",
    "avg_allowed",
    "obp_allowed",
    "slg_allowed",
    "ops_allowed",
    "strikeouts_per_9",
    "walks_per_9",
    "hits_per_9",
    "home_runs_per_9",
)

_MEM_CACHE: dict[tuple[int, str], dict[str, float]] = {}


def _to_float(value: object, default: float | None = 0.0) -> float | None:
    if value in (None, "", "-.--"):
        return default
    try:
        return float(str(value))
    except ValueError:
        return default


def _ip_to_float(value: object) -> float:
    """MLB innings pitched like "49.1" means 49 and 1/3 innings."""
    if value in (None, ""):
        return 0.0
    text = str(value)
    if "." in text:
        whole, frac = text.split(".", 1)
        try:
            return float(whole) + float(frac) / 3.0
        except ValueError:
            return 0.0
    return _to_float(value, 0.0) or 0.0


def _season_start(year: int) -> date:
    return date(year, 3, 1)


def _fetch_range(pitcher_id: int, season: int, start: date, end: date) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{pitcher_id}_{season}_{start.isoformat()}_{end.isoformat()}.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except json.JSONDecodeError:
            cache_path.unlink(missing_ok=True)

    params = urlencode(
        {
            "stats": "byDateRange",
            "group": "pitching",
            "season": season,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
        }
    )
    url = f"{API_BASE}/people/{pitcher_id}/stats?{params}"
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(url, timeout=30, context=context) as response:
            payload = json.load(response)
    except Exception:
        return {}

    stats = payload.get("stats") or []
    splits = stats[0].get("splits") if stats else []
    stat = splits[0].get("stat", {}) if splits else {}
    cache_path.write_text(json.dumps(stat))
    return stat


def _parse_line(stat: dict) -> dict[str, float | None]:
    return {
        "era": _to_float(stat.get("era"), None),
        "whip": _to_float(stat.get("whip"), None),
        "avg_allowed": _to_float(stat.get("avg"), None),
        "obp_allowed": _to_float(stat.get("obp"), None),
        "slg_allowed": _to_float(stat.get("slg"), None),
        "ops_allowed": _to_float(stat.get("ops"), None),
        "strikeouts_per_9": _to_float(stat.get("strikeoutsPer9Inn"), None),
        "walks_per_9": _to_float(stat.get("walksPer9Inn"), None),
        "hits_per_9": _to_float(stat.get("hitsPer9Inn"), None),
        "home_runs_per_9": _to_float(stat.get("homeRunsPer9"), None),
        "innings_pitched": _ip_to_float(stat.get("inningsPitched")),
        "games_started": _to_float(stat.get("gamesStarted"), 0.0) or 0.0,
    }


def _blend(current: dict[str, float | None], prior: dict[str, float | None]) -> dict[str, float]:
    """Shrink current-season rate stats toward the prior season by sample size.

    Workload counters (IP, GS) stay as the current-season point-in-time totals.
    """
    ip_c = float(current.get("innings_pitched") or 0.0)
    out: dict[str, float] = {}
    for key in _RATE_KEYS:
        cur = current.get(key)
        pri = prior.get(key)
        if cur is not None and pri is not None and ip_c > 0:
            w = ip_c / (ip_c + PRIOR_IP_WEIGHT)
            out[key] = w * float(cur) + (1.0 - w) * float(pri)
        elif cur is not None and ip_c > 0:
            out[key] = float(cur)
        elif pri is not None:
            out[key] = float(pri)
        else:
            out[key] = _DEFAULTS[key]
    out["innings_pitched"] = ip_c
    out["games_started"] = float(current.get("games_started") or 0.0)
    return out


def pitcher_stats_as_of(pitcher_id: int | None, game_date: date) -> dict[str, float]:
    """Return the pitcher line knowable before first pitch on ``game_date``.

    Current-season totals through the previous day, shrunk toward the prior
    full season. No future information is ever used.
    """
    if not pitcher_id:
        return dict(_DEFAULTS)

    mem_key = (pitcher_id, game_date.isoformat())
    if mem_key in _MEM_CACHE:
        return _MEM_CACHE[mem_key]

    season = game_date.year
    start = _season_start(season)
    end = game_date - timedelta(days=1)

    if end < start:
        # Pre-opening day: fall back entirely to the (fully known) prior season.
        prior_full = _parse_line(
            _fetch_range(pitcher_id, season - 1, _season_start(season - 1), date(season - 1, 11, 30))
        )
        result = {
            key: (float(prior_full[key]) if prior_full.get(key) is not None else _DEFAULTS[key])
            for key in _RATE_KEYS
        }
        result["innings_pitched"] = 0.0
        result["games_started"] = 0.0
        _MEM_CACHE[mem_key] = result
        return result

    current = _parse_line(_fetch_range(pitcher_id, season, start, end))
    prior = _parse_line(
        _fetch_range(pitcher_id, season - 1, _season_start(season - 1), date(season - 1, 11, 30))
    )
    result = _blend(current, prior)
    _MEM_CACHE[mem_key] = result
    return result


def pitcher_era_as_of(pitcher_id: int | None, game_date: date) -> float:
    return pitcher_stats_as_of(pitcher_id, game_date)["era"]


_RECENT_RATES_CACHE: dict[tuple[int, str, int], dict[str, float]] = {}
_GAMELOG_MEM: dict[tuple[int, int], list[dict]] = {}
GAMELOG_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "pitcher_gamelog"


def _pitcher_start_log(pitcher_id: int, season: int) -> list[dict]:
    """Season start log (date, ip, k9), disk-cached once per pitcher-season."""
    mem_key = (pitcher_id, season)
    if mem_key in _GAMELOG_MEM:
        return _GAMELOG_MEM[mem_key]

    GAMELOG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = GAMELOG_CACHE_DIR / f"{pitcher_id}_{season}.json"
    # Refresh in-season logs that are older than 12h so recent starts appear.
    if cache_path.exists():
        age_h = (time.time() - cache_path.stat().st_mtime) / 3600.0
        # Prior seasons are immutable; current season refreshes every 12h.
        if season < date.today().year or age_h < 12:
            try:
                rows = json.loads(cache_path.read_text())
                _GAMELOG_MEM[mem_key] = rows
                return rows
            except json.JSONDecodeError:
                cache_path.unlink(missing_ok=True)

    params = urlencode(
        {
            "stats": "gameLog",
            "group": "pitching",
            "season": season,
        }
    )
    url = f"{API_BASE}/people/{pitcher_id}/stats?{params}"
    context = ssl.create_default_context(cafile=certifi.where())
    rows: list[dict] = []
    try:
        with urlopen(url, timeout=30, context=context) as response:
            payload = json.load(response)
        splits = (payload.get("stats") or [{}])[0].get("splits") or []
        for split in splits:
            raw_day = split.get("date")
            if not raw_day:
                continue
            st = split.get("stat") or {}
            if int(st.get("gamesStarted") or 0) != 1:
                continue
            ip = _ip_to_float(st.get("inningsPitched"))
            so = _to_float(st.get("strikeOuts"), 0.0) or 0.0
            if ip <= 0:
                continue
            rows.append({
                "date": str(raw_day)[:10],
                "ip": ip,
                "k9": so * 9.0 / ip,
            })
        cache_path.write_text(json.dumps(rows))
    except Exception:
        rows = []
    _GAMELOG_MEM[mem_key] = rows
    return rows


def pitcher_recent_start_rates(
    pitcher_id: int | None,
    game_date: date,
    *,
    n: int = 5,
) -> dict[str, float]:
    """Mean IP and K/9 over the last ``n`` starts strictly before ``game_date``."""
    if not pitcher_id or n <= 0:
        return {}
    mem_key = (pitcher_id, game_date.isoformat(), n)
    if mem_key in _RECENT_RATES_CACHE:
        return dict(_RECENT_RATES_CACHE[mem_key])

    starts = []
    for row in _pitcher_start_log(pitcher_id, game_date.year):
        try:
            day = date.fromisoformat(row["date"])
        except ValueError:
            continue
        if day >= game_date:
            continue
        starts.append((float(row["ip"]), float(row["k9"])))

    recent = starts[-n:] if len(starts) >= n else starts
    if not recent:
        _RECENT_RATES_CACHE[mem_key] = {}
        return {}
    out = {
        "exp_ip": sum(x[0] for x in recent) / len(recent),
        "k9": sum(x[1] for x in recent) / len(recent),
        "n_starts": float(len(recent)),
    }
    _RECENT_RATES_CACHE[mem_key] = out
    return dict(out)
