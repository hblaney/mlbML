"""Batter vs LHP/RHP handedness splits + pitcher throwing hand (MLB Stats API).

Platoon matchup is one of the biggest real signals in props: a lefty masher facing
a LHP, a righty who crushes lefties, etc. This provider surfaces:
  - pitcher_throws(pitcher_id): 'L' or 'R'
  - hitter_platoon_multiplier(hitter_id, pitcher_hand, ...): production multiplier
    from the hitter's OPS split vs that hand (shrunk toward 1.0 on small samples).
  - pitcher_k_platoon_multiplier(pitcher_id, ...): K/9 tilt vs L/R hitters.

Live boards use the current season's splits (fully knowable today). Historical
backtests use the PRIOR season's splits only — full-season current splits would
leak future games into past projections.
"""

from __future__ import annotations

import json
import ssl
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.request import urlopen

import certifi

MLB_API_BASE = "https://statsapi.mlb.com/api/v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / "data" / "cache" / "handedness"

LEAGUE_OPS = 0.715
# Shrinkage: split OPS is trusted more with more PAs vs that hand.
SPLIT_PRIOR_PA = 120


def _get_json(url: str):
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urlopen(url, timeout=30, context=ctx) as response:
        return json.load(response)


@lru_cache(maxsize=2048)
def pitcher_throws(pitcher_id: int) -> str | None:
    if not pitcher_id:
        return None
    try:
        payload = _get_json(f"{MLB_API_BASE}/people/{pitcher_id}")
        people = payload.get("people", [])
        if people:
            return people[0].get("pitchHand", {}).get("code")
    except Exception:
        return None
    return None


@lru_cache(maxsize=8192)
def _hitter_splits(hitter_id: int, season: int) -> dict:
    """{'vl': {ops, pa}, 'vr': {ops, pa}} vs LHP/RHP."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"hitter_{hitter_id}_{season}.json"
    use_cache = cache_path.exists() and season < date.today().year
    if use_cache:
        try:
            return json.loads(cache_path.read_text())
        except Exception:
            pass
    url = (
        f"{MLB_API_BASE}/people/{hitter_id}/stats"
        f"?stats=statSplits&sitCodes=vl,vr&group=hitting&season={season}"
    )
    out: dict[str, dict] = {}
    try:
        payload = _get_json(url)
    except Exception:
        return out
    for block in payload.get("stats", []):
        for split in block.get("splits", []):
            code = split.get("split", {}).get("code")
            stat = split.get("stat", {})
            if code in ("vl", "vr"):
                try:
                    out[code] = {
                        "ops": float(stat.get("ops", 0) or 0),
                        "pa": float(stat.get("plateAppearances", 0) or 0),
                    }
                except (TypeError, ValueError):
                    continue
    if season < date.today().year:
        try:
            cache_path.write_text(json.dumps(out))
        except Exception:
            pass
    return out


def _split_season_for(game_date: date) -> int:
    """Season whose splits are fully knowable before ``game_date``.

    Live (today or later): current season. Historical: prior season only, so
    April projections never see June/July platoon data.
    """
    if game_date >= date.today():
        return game_date.year
    return game_date.year - 1


def hitter_platoon_multiplier(
    hitter_id: int | None,
    pitcher_hand: str | None,
    game_date: date,
    overall_ops: float | None = None,
) -> float:
    """Production multiplier from the hitter's OPS split vs the pitcher's hand."""
    if not hitter_id or pitcher_hand not in ("L", "R"):
        return 1.0
    season = _split_season_for(game_date)
    splits = _hitter_splits(hitter_id, season)
    code = "vl" if pitcher_hand == "L" else "vr"
    split = splits.get(code)
    if not split or split["pa"] < 15:
        return 1.0
    base = overall_ops if overall_ops and overall_ops > 0 else LEAGUE_OPS
    raw_mult = split["ops"] / base if base > 0 else 1.0
    # Shrink toward 1.0 based on split sample size.
    weight = split["pa"] / (split["pa"] + SPLIT_PRIOR_PA)
    mult = 1.0 + (raw_mult - 1.0) * weight
    return max(0.80, min(1.25, mult))


@lru_cache(maxsize=8192)
def _pitcher_k_splits(pitcher_id: int, season: int) -> dict:
    """{'vl': {k, bf}, 'vr': {k, bf}} strikeouts vs LHB/RHB."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"pitcher_{pitcher_id}_{season}.json"
    use_cache = cache_path.exists() and season < date.today().year
    if use_cache:
        try:
            return json.loads(cache_path.read_text())
        except Exception:
            pass
    url = (
        f"{MLB_API_BASE}/people/{pitcher_id}/stats"
        f"?stats=statSplits&sitCodes=vl,vr&group=pitching&season={season}"
    )
    out: dict[str, dict] = {}
    try:
        payload = _get_json(url)
    except Exception:
        return out
    for block in payload.get("stats", []):
        for split in block.get("splits", []):
            code = split.get("split", {}).get("code")
            stat = split.get("stat", {})
            if code in ("vl", "vr"):
                try:
                    out[code] = {
                        "k": float(stat.get("strikeOuts", 0) or 0),
                        "bf": float(stat.get("battersFaced", 0) or 0),
                    }
                except (TypeError, ValueError):
                    continue
    if season < date.today().year:
        try:
            cache_path.write_text(json.dumps(out))
        except Exception:
            pass
    return out


@lru_cache(maxsize=4096)
def batter_bat_side(batter_id: int) -> str | None:
    """'L', 'R', or 'S' (switch)."""
    if not batter_id:
        return None
    try:
        payload = _get_json(f"{MLB_API_BASE}/people/{batter_id}")
        people = payload.get("people", [])
        if people:
            return people[0].get("batSide", {}).get("code")
    except Exception:
        return None
    return None


def pitcher_k_rate_by_hand(pitcher_id: int, season: int) -> tuple[float, float, float] | None:
    """Return (k_rate_vs_L, k_rate_vs_R, k_rate_overall) as strikeouts/BF."""
    splits = _pitcher_k_splits(pitcher_id, season)
    vl, vr = splits.get("vl"), splits.get("vr")
    if not vl or not vr or (vl["bf"] + vr["bf"]) < 60:
        return None
    kl = vl["k"] / vl["bf"] if vl["bf"] > 0 else 0.0
    kr = vr["k"] / vr["bf"] if vr["bf"] > 0 else 0.0
    overall = (vl["k"] + vr["k"]) / (vl["bf"] + vr["bf"])
    if overall <= 0:
        return None
    return kl, kr, overall


def pitcher_k_platoon_multiplier(
    pitcher_id: int | None,
    pitcher_hand: str | None,
    opp_bat_sides: list[str] | None,
    game_date: date,
) -> float:
    """K-rate tilt from the opposing lineup's L/R composition vs this pitcher.

    Weights the pitcher's strikeout rate vs LHB/RHB by how many lefties/righties
    they'll actually face (switch hitters bat opposite the pitcher's hand).
    """
    if not pitcher_id or not opp_bat_sides:
        return 1.0
    rates = pitcher_k_rate_by_hand(pitcher_id, _split_season_for(game_date))
    if not rates:
        return 1.0
    kl, kr, overall = rates
    total = 0.0
    n = 0
    for side in opp_bat_sides:
        eff = side
        if side == "S":
            eff = "L" if pitcher_hand == "R" else "R"
        total += kl if eff == "L" else kr
        n += 1
    if n == 0:
        return 1.0
    weighted = total / n
    return max(0.85, min(1.18, weighted / overall))
