"""Leakage-safe, point-in-time hitter stats for prop / FS projections."""

from __future__ import annotations

import json
import ssl
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import certifi

API_BASE = "https://statsapi.mlb.com/api/v1"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "hitter_stats_asof"

_DEFAULTS: dict[str, float] = {
    "hits": 0.85,
    "doubles": 0.18,
    "triples": 0.02,
    "home_runs": 0.10,
    "runs": 0.45,
    "rbi": 0.42,
    "walks": 0.35,
    "hbp": 0.03,
    "stolen_bases": 0.05,
    "strikeouts": 0.90,
    "plate_appearances": 4.0,
    "ops": 0.720,
}

_PRIOR_PA_WEIGHT = 80.0
_MEM_CACHE: dict[tuple[int, str], dict[str, float]] = {}


def _to_float(value: object, default: float = 0.0) -> float:
    if value in (None, "", "-.--"):
        return default
    try:
        return float(str(value))
    except ValueError:
        return default


def _season_start(year: int) -> date:
    return date(year, 3, 1)


def _fetch_range(hitter_id: int, season: int, start: date, end: date) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{hitter_id}_{season}_{start.isoformat()}_{end.isoformat()}.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except json.JSONDecodeError:
            cache_path.unlink(missing_ok=True)

    params = urlencode(
        {
            "stats": "byDateRange",
            "group": "hitting",
            "season": season,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
        }
    )
    url = f"{API_BASE}/people/{hitter_id}/stats?{params}"
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


def _parse_line(stat: dict) -> dict[str, float]:
    hits = _to_float(stat.get("hits"))
    doubles = _to_float(stat.get("doubles"))
    triples = _to_float(stat.get("triples"))
    hrs = _to_float(stat.get("homeRuns"))
    pa = _to_float(stat.get("plateAppearances"), 1.0)
    return {
        "hits": hits,
        "doubles": doubles,
        "triples": triples,
        "home_runs": hrs,
        "runs": _to_float(stat.get("runs")),
        "rbi": _to_float(stat.get("rbi")),
        "walks": _to_float(stat.get("baseOnBalls")),
        "hbp": _to_float(stat.get("hitByPitch")),
        "stolen_bases": _to_float(stat.get("stolenBases")),
        "strikeouts": _to_float(stat.get("strikeOuts")),
        "plate_appearances": pa,
        "ops": _to_float(stat.get("ops"), 0.720),
    }


def _blend(current: dict[str, float], prior: dict[str, float]) -> dict[str, float]:
    pa_c = max(current.get("plate_appearances", 0.0), 0.0)
    out: dict[str, float] = {}
    count_keys = (
        "hits", "doubles", "triples", "home_runs", "runs", "rbi",
        "walks", "hbp", "stolen_bases", "strikeouts", "plate_appearances",
    )
    for key in count_keys:
        cur = current.get(key, 0.0)
        pri = prior.get(key, 0.0)
        if pa_c > 0 and pri > 0:
            w = pa_c / (pa_c + _PRIOR_PA_WEIGHT)
            out[key] = w * cur + (1.0 - w) * pri
        elif pa_c > 0:
            out[key] = cur
        else:
            out[key] = pri
    out["ops"] = current.get("ops") or prior.get("ops") or _DEFAULTS["ops"]
    return out


def hitter_stats_as_of(hitter_id: int | None, game_date: date) -> dict[str, float]:
    if not hitter_id:
        return dict(_DEFAULTS)

    mem_key = (hitter_id, game_date.isoformat())
    if mem_key in _MEM_CACHE:
        return _MEM_CACHE[mem_key]

    season = game_date.year
    start = _season_start(season)
    end = game_date - timedelta(days=1)

    if end < start:
        prior_full = _parse_line(
            _fetch_range(hitter_id, season - 1, _season_start(season - 1), date(season - 1, 11, 30))
        )
        result = prior_full if prior_full.get("plate_appearances", 0) > 0 else dict(_DEFAULTS)
        _MEM_CACHE[mem_key] = result
        return result

    current = _parse_line(_fetch_range(hitter_id, season, start, end))
    prior = _parse_line(
        _fetch_range(hitter_id, season - 1, _season_start(season - 1), date(season - 1, 11, 30))
    )
    if current.get("plate_appearances", 0) <= 0:
        result = prior if prior.get("plate_appearances", 0) > 0 else dict(_DEFAULTS)
    else:
        result = _blend(current, prior)
    _MEM_CACHE[mem_key] = result
    return result


_RECENT_CACHE: dict[tuple[int, str, int], dict[str, float]] = {}
_LAST_N_TB_CACHE: dict[tuple[int, str, int], list[float]] = {}


def hitter_recent_rates(
    hitter_id: int | None,
    game_date: date,
    *,
    lookback_days: int = 14,
) -> dict[str, float]:
    """Per-PA rates over the last ``lookback_days`` ending yesterday (no leakage)."""
    if not hitter_id:
        return {}
    mem_key = (hitter_id, game_date.isoformat(), lookback_days)
    if mem_key in _RECENT_CACHE:
        return _RECENT_CACHE[mem_key]

    end = game_date - timedelta(days=1)
    start = end - timedelta(days=lookback_days - 1)
    if end < _season_start(game_date.year):
        _RECENT_CACHE[mem_key] = {}
        return {}
    start = max(start, _season_start(game_date.year))
    parsed = _parse_line(_fetch_range(hitter_id, game_date.year, start, end))
    pa = parsed.get("plate_appearances", 0.0)
    if pa < 8:
        _RECENT_CACHE[mem_key] = {}
        return {}
    hits = parsed.get("hits", 0.0)
    doubles = parsed.get("doubles", 0.0)
    triples = parsed.get("triples", 0.0)
    hr = parsed.get("home_runs", 0.0)
    singles = max(0.0, hits - doubles - triples - hr)
    tb = singles + 2 * doubles + 3 * triples + 4 * hr
    so = parsed.get("strikeouts", 0.0)
    out = {
        "plate_appearances": pa,
        "hit_pa": hits / pa,
        "tb_pa": tb / pa,
        "hr_pa": hr / pa,
        "k_pa": so / pa,
        "avg_tb_per_game": tb / max(1.0, pa / 4.2),
    }
    _RECENT_CACHE[mem_key] = out
    return out


def hitter_last_n_total_bases(
    hitter_id: int | None,
    game_date: date,
    n: int = 3,
) -> list[float]:
    """Total bases in each of the last n games strictly before ``game_date``."""
    if not hitter_id or n <= 0:
        return []
    mem_key = (hitter_id, game_date.isoformat(), n)
    if mem_key in _LAST_N_TB_CACHE:
        return _LAST_N_TB_CACHE[mem_key]

    season = game_date.year
    params = urlencode(
        {
            "stats": "gameLog",
            "group": "hitting",
            "season": season,
        }
    )
    url = f"{API_BASE}/people/{hitter_id}/stats?{params}"
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(url, timeout=30, context=context) as response:
            payload = json.load(response)
    except Exception:
        _LAST_N_TB_CACHE[mem_key] = []
        return []

    splits = (payload.get("stats") or [{}])[0].get("splits") or []
    tbs: list[float] = []
    for split in splits:
        raw_day = split.get("date")
        if not raw_day:
            continue
        try:
            day = date.fromisoformat(str(raw_day)[:10])
        except ValueError:
            continue
        if day >= game_date:
            continue
        st = split.get("stat") or {}
        if st.get("totalBases") is not None:
            tbs.append(_to_float(st.get("totalBases")))
        else:
            hits = _to_float(st.get("hits"))
            doubles = _to_float(st.get("doubles"))
            triples = _to_float(st.get("triples"))
            hr = _to_float(st.get("homeRuns"))
            singles = max(0.0, hits - doubles - triples - hr)
            tbs.append(singles + 2 * doubles + 3 * triples + 4 * hr)

    out = tbs[-n:] if len(tbs) >= n else tbs
    _LAST_N_TB_CACHE[mem_key] = out
    return out
