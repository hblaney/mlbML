"""Grade archived prop predictions against real results -> honest track record.

For every archived daily board (data/prop-predictions/{date}.json) whose games are
final, we pull each player's actual game-log line from the MLB Stats API and settle
the lean (Over/Under vs the line) and the daily parlay. Output is a real,
self-updating track record at public/prop-track-record.json — no manufactured edge,
just measured hit rate and ROI.

DNP (player didn't appear) is treated as a void (excluded), matching how PrizePicks
handles it.
"""

from __future__ import annotations

import json
import ssl
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.request import urlopen

import certifi

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_DIR = REPO_ROOT / "data" / "prop-predictions"
GAMELOG_CACHE = REPO_ROOT / "data" / "cache" / "player_gamelog"
OUT_PATH = REPO_ROOT / "public" / "prop-track-record.json"
MLB_API_BASE = "https://statsapi.mlb.com/api/v1"

# PrizePicks power-play payout multipliers (decimal) by leg count.
PP_POWER_PAYOUT = {2: 3.0, 3: 5.0, 4: 10.0, 5: 20.0, 6: 37.5}

# PrizePicks flex payouts: (correct_legs, n_legs) -> decimal multiplier.
# Standard published tables (partial credit for near-misses).
PP_FLEX_PAYOUT = {
    (3, 3): 2.25,
    (2, 3): 1.25,
    (4, 4): 5.0,
    (3, 4): 1.5,
    (5, 5): 10.0,
    (4, 5): 2.0,
    (3, 5): 0.4,
    (6, 6): 25.0,
    (5, 6): 2.0,
    (4, 6): 0.4,
}


def _parlay_profit(parlay_type: str, n: int, wins: int, pushes: int, losses: int) -> tuple[bool, float]:
    """Return (counted_as_cash, profit) for a settled parlay unit stake."""
    kind = (parlay_type or "power").lower()
    if kind == "flex":
        # Flex grades decisive legs only; pushes shrink the effective board.
        effective_n = n - pushes
        if effective_n < 2:
            return False, 0.0  # void / push the ticket
        payout = PP_FLEX_PAYOUT.get((wins, effective_n), 0.0)
        if payout > 0:
            return True, payout - 1.0
        return False, -1.0
    # Power: every non-push leg must win; pushes survive.
    payout = PP_POWER_PAYOUT.get(n, max(2.0, 2.0 ** (n - 1)))
    if losses == 0:
        return True, payout - 1.0
    return False, -1.0

HITTER_PROPS = {
    "batter_hits", "batter_total_bases", "batter_home_runs", "batter_rbis",
    "batter_runs_scored", "batter_walks", "batter_stolen_bases", "batter_singles",
    "batter_doubles", "batter_hits_runs_rbis",
}
PITCHER_PROPS = {
    "pitcher_strikeouts", "pitcher_outs", "pitcher_earned_runs", "pitcher_hits_allowed",
}


def _get_json(url: str):
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urlopen(url, timeout=30, context=ctx) as response:
        return json.load(response)


def _decimal(american: int) -> float:
    if american == 0:
        return 2.0
    if american < 0:
        return 1.0 + 100.0 / abs(american)
    return 1.0 + american / 100.0


def _gamelog(player_id: int, season: int, group: str) -> dict[str, dict]:
    """{date: stat} for a player's game log, cached."""
    GAMELOG_CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = GAMELOG_CACHE / f"{player_id}_{season}_{group}.json"
    # Refresh cache if it's for the current season (games still being added).
    use_cache = cache_path.exists() and season < date.today().year
    if use_cache:
        try:
            return json.loads(cache_path.read_text())
        except Exception:
            pass
    url = f"{MLB_API_BASE}/people/{player_id}/stats?stats=gameLog&group={group}&season={season}"
    try:
        payload = _get_json(url)
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for block in payload.get("stats", []):
        for split in block.get("splits", []):
            d = split.get("date")
            if d:
                out[d] = split.get("stat", {})
    try:
        cache_path.write_text(json.dumps(out))
    except Exception:
        pass
    return out


def _actual_value(prop: str, stat: dict) -> float | None:
    if not stat:
        return None

    def g(key: str) -> float:
        try:
            return float(stat.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    if prop == "batter_hits":
        return g("hits")
    if prop == "batter_home_runs":
        return g("homeRuns")
    if prop == "batter_rbis":
        return g("rbi")
    if prop == "batter_runs_scored":
        return g("runs")
    if prop == "batter_walks":
        return g("baseOnBalls")
    if prop == "batter_stolen_bases":
        return g("stolenBases")
    if prop == "batter_doubles":
        return g("doubles")
    if prop == "batter_singles":
        return g("hits") - g("doubles") - g("triples") - g("homeRuns")
    if prop == "batter_total_bases":
        return g("hits") + g("doubles") + 2 * g("triples") + 3 * g("homeRuns")
    if prop == "batter_hits_runs_rbis":
        return g("hits") + g("runs") + g("rbi")
    if prop == "pitcher_strikeouts":
        return g("strikeOuts")
    if prop == "pitcher_earned_runs":
        return g("earnedRuns")
    if prop == "pitcher_hits_allowed":
        return g("hits")
    if prop == "pitcher_outs":
        ip = stat.get("inningsPitched")
        if ip is None:
            return None
        try:
            whole, _, frac = str(ip).partition(".")
            return int(whole) * 3 + int(frac or 0)
        except ValueError:
            return None
    return None


def _grade_leg(leg: dict, game_date: str) -> dict | None:
    """Return {won: bool|None(push), profit: float, actual} or None if void/DNP."""
    pid = leg.get("player_id")
    prop = leg.get("prop")
    if not pid or not prop:
        return None
    season = int(game_date[:4])
    group = "hitting" if prop in HITTER_PROPS else "pitching"
    log = _gamelog(int(pid), season, group)
    stat = log.get(game_date)
    if stat is None:
        return None  # DNP / void
    actual = _actual_value(prop, stat)
    if actual is None:
        return None
    line = float(leg["line"])
    side = leg["side"]
    if actual == line:
        return {"won": None, "profit": 0.0, "actual": actual}
    over_won = actual > line
    won = over_won if side == "Over" else (not over_won)
    profit = (_decimal(int(leg.get("price", 0))) - 1.0) if won else -1.0
    return {"won": won, "profit": profit, "actual": actual}


def grade_all() -> dict:
    today = date.today().isoformat()
    overall = {"graded": 0, "wins": 0, "losses": 0, "pushes": 0, "profit": 0.0}
    by_conf: dict[str, dict] = defaultdict(lambda: {"graded": 0, "wins": 0})
    by_prop: dict[str, dict] = defaultdict(lambda: {"graded": 0, "wins": 0})
    parlay_rec = {"graded": 0, "wins": 0, "profit": 0.0}
    recent: list[dict] = []

    if not ARCHIVE_DIR.exists():
        return _finalize(overall, by_conf, by_prop, parlay_rec, recent)

    for path in sorted(ARCHIVE_DIR.glob("*.json")):
        game_date = path.stem
        if game_date >= today:
            continue  # only grade completed days
        try:
            board = json.loads(path.read_text())
        except Exception:
            continue

        day_wins = day_losses = day_pushes = 0
        for leg in board.get("predictions", []):
            result = _grade_leg(leg, game_date)
            if result is None:
                continue
            overall["graded"] += 1
            conf = leg.get("confidence", "Low")
            prop = leg.get("prop", "?")
            by_conf[conf]["graded"] += 1
            by_prop[prop]["graded"] += 1
            if result["won"] is None:
                overall["pushes"] += 1
                day_pushes += 1
            elif result["won"]:
                overall["wins"] += 1
                by_conf[conf]["wins"] += 1
                by_prop[prop]["wins"] += 1
                day_wins += 1
            else:
                overall["losses"] += 1
                day_losses += 1
            overall["profit"] += result["profit"]

        # Grade the archived daily parlay (power vs flex payout tables).
        parlay = board.get("parlay", {})
        legs = parlay.get("legs", [])
        if len(legs) >= 2:
            leg_results = [_grade_leg(l, game_date) for l in legs]
            if all(r is not None for r in leg_results):
                graded_legs = [r for r in leg_results if r is not None]
                n = len(graded_legs)
                wins = sum(1 for r in graded_legs if r["won"] is True)
                pushes = sum(1 for r in graded_legs if r["won"] is None)
                losses = sum(1 for r in graded_legs if r["won"] is False)
                cashed, profit = _parlay_profit(
                    str(parlay.get("type") or "power"), n, wins, pushes, losses
                )
                if profit != 0.0 or cashed:
                    parlay_rec["graded"] += 1
                    if cashed:
                        parlay_rec["wins"] += 1
                    parlay_rec["profit"] += profit
                recent.append(
                    {
                        "date": game_date,
                        "legs": n,
                        "type": parlay.get("type") or "power",
                        "won": cashed,
                        "record": f"{day_wins}-{day_losses}",
                    }
                )

    return _finalize(overall, by_conf, by_prop, parlay_rec, recent)


def _rate(wins: int, graded: int) -> float:
    return round(wins / graded, 4) if graded else 0.0


def _finalize(overall, by_conf, by_prop, parlay_rec, recent) -> dict:
    decided = overall["wins"] + overall["losses"]
    result = {
        "generated_at": date.today().isoformat(),
        "overall": {
            "graded": overall["graded"],
            "wins": overall["wins"],
            "losses": overall["losses"],
            "pushes": overall["pushes"],
            "hit_rate": _rate(overall["wins"], decided),
            "roi": round(overall["profit"] / overall["graded"], 4) if overall["graded"] else 0.0,
        },
        "by_confidence": {
            k: {"graded": v["graded"], "wins": v["wins"], "hit_rate": _rate(v["wins"], v["graded"])}
            for k, v in sorted(by_conf.items())
        },
        "by_prop": {
            k: {"graded": v["graded"], "wins": v["wins"], "hit_rate": _rate(v["wins"], v["graded"])}
            for k, v in sorted(by_prop.items())
        },
        "parlay": {
            "graded": parlay_rec["graded"],
            "wins": parlay_rec["wins"],
            "hit_rate": _rate(parlay_rec["wins"], parlay_rec["graded"]),
            "roi": round(parlay_rec["profit"] / parlay_rec["graded"], 4) if parlay_rec["graded"] else 0.0,
        },
        "recent": recent[-30:],
    }
    return result


def main() -> None:
    result = grade_all()
    OUT_PATH.write_text(json.dumps(result, indent=2))
    o = result["overall"]
    print(
        f"prop_grade_ok graded={o['graded']} record={o['wins']}-{o['losses']} "
        f"push={o['pushes']} hit={o['hit_rate']:.3f} roi={o['roi']:+.3f} "
        f"| parlay {result['parlay']['wins']}/{result['parlay']['graded']}"
    )


if __name__ == "__main__":
    main()
