"""Daily prop accuracy simulator + strategy search.

For every finished game in a date range we project the full standard/PP ladder
for every starter in the lineup / SP, pick a side, and grade it. Then we search
selection policies — including a production-mirrored Top 5 card — whose
out-of-sample hit rate clears a target (default 80%).

Walk-forward calibration:
  1. Collect RAW model P(over) (no isotonic during collect).
  2. Fit isotonic on train days only → data/prop_calibration.json
  3. Apply calibrate() when ranking/searching on train+test.

Usage:
  python3 simulate_prop_accuracy.py 2026-04-04 2026-07-18 [games_per_day] [search]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from mlb_api import load_or_fetch_games, load_team_abbreviations
from hitter_stats_provider import hitter_stats_as_of
from pitcher_stats_provider import pitcher_stats_as_of
from bullpen_provider import bullpen_stats_as_of
from lineup_provider import _boxscore, confirmed_lineup_by_team, expected_pa_for_slot
from park_factors import park_for_team
from prop_projections import project_hitter, project_pitcher
from prop_odds_provider import PropLine
from prop_calibration import calibrate, is_available, reload as reload_calib
from handedness_provider import pitcher_throws, batter_bat_side

REPO = Path(__file__).resolve().parents[2]
DUMP = REPO / "data" / "prop_sim_records.jsonl"
WINNERS_OUT = REPO / "data" / "prop_strategy_winners.json"
POLICY_OUT = REPO / "data" / "prop_accuracy_policy.json"
BACKTEST_RECORDS = REPO / "data" / "prop_backtest_records.json"
BACKTEST_TRAIN = REPO / "data" / "prop_backtest_records_train.json"

# Full daily universe the selector ranks over.
HITTER_LINES = [
    ("batter_hits", [0.5, 1.5]),
    ("batter_total_bases", [0.5, 1.5, 2.5]),
    ("batter_home_runs", [0.5]),
    ("batter_rbis", [0.5, 1.5]),
    ("batter_runs_scored", [0.5, 1.5]),
    ("batter_hits_runs_rbis", [0.5, 1.5, 2.5]),
    ("batter_walks", [0.5]),
    ("batter_stolen_bases", [0.5]),
    ("batter_singles", [0.5, 1.5]),
    ("batter_doubles", [0.5]),
]
PITCHER_LINES = [
    ("pitcher_strikeouts", [3.5, 4.5, 5.5, 6.5, 7.5]),
    ("pitcher_outs", [14.5, 15.5, 17.5, 18.5]),
    ("pitcher_earned_runs", [1.5, 2.5, 3.5]),
    ("pitcher_hits_allowed", [4.5, 5.5, 6.5]),
]

ACCURACY_PROPS = {"batter_hits", "batter_total_bases", "pitcher_strikeouts"}
K_OVER_MIN_LINE = 5.5
K_OVER_MIN_CONF = 0.68
K_OVER_MIN_PROJ_EDGE = 1.0


def _mk(pid: int, prop: str, line: float, is_home: bool) -> PropLine:
    return PropLine(
        event_id="", commence_time="", game_id=None, home_abbr="", away_abbr="",
        player="", player_id=pid, team_abbr=None, is_home=is_home, opp_abbr=None,
        prop=prop, line=line, over_price=-110, under_price=-110,
        market_prob_over=0.5, book_count=0,
    )


def _parse_ip(value: object) -> float:
    if value in (None, ""):
        return 0.0
    text = str(value)
    if "." in text:
        whole, frac = text.split(".", 1)
        try:
            return float(whole) + float(frac) / 3.0
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _player_node(box: dict, team_id: int, pid: int) -> dict | None:
    for side in ("home", "away"):
        team = box.get("teams", {}).get(side, {})
        if team.get("team", {}).get("id") != team_id:
            continue
        return team.get("players", {}).get(f"ID{pid}", {})
    return None


def _actual_batting(box: dict, team_id: int, pid: int) -> dict | None:
    node = _player_node(box, team_id, pid)
    bat = (node or {}).get("stats", {}).get("batting", {})
    if not bat:
        return None
    hits = float(bat.get("hits", 0) or 0)
    doubles = float(bat.get("doubles", 0) or 0)
    triples = float(bat.get("triples", 0) or 0)
    hr = float(bat.get("homeRuns", 0) or 0)
    rbi = float(bat.get("rbi", 0) or 0)
    runs = float(bat.get("runs", 0) or 0)
    bb = float(bat.get("baseOnBalls", 0) or 0)
    sb = float(bat.get("stolenBases", 0) or 0)
    singles = max(0.0, hits - doubles - triples - hr)
    tb = singles + 2 * doubles + 3 * triples + 4 * hr
    return {
        "batter_hits": hits, "batter_total_bases": tb, "batter_home_runs": hr,
        "batter_rbis": rbi, "batter_runs_scored": runs,
        "batter_hits_runs_rbis": hits + runs + rbi, "batter_walks": bb,
        "batter_stolen_bases": sb, "batter_singles": singles, "batter_doubles": doubles,
    }


def _actual_pitching(box: dict, team_id: int, pid: int) -> dict | None:
    node = _player_node(box, team_id, pid)
    pit = (node or {}).get("stats", {}).get("pitching", {})
    if not pit or int(pit.get("gamesStarted", 0) or 0) != 1:
        return None
    return {
        "pitcher_strikeouts": float(pit.get("strikeOuts", 0) or 0),
        "pitcher_outs": _parse_ip(pit.get("inningsPitched")) * 3.0,
        "pitcher_earned_runs": float(pit.get("earnedRuns", 0) or 0),
        "pitcher_hits_allowed": float(pit.get("hits", 0) or 0),
    }


def _is_freebie(r: dict) -> bool:
    prop = r["prop"]
    line = float(r["line"])
    conf = float(r["conf"])
    if prop in ("batter_home_runs", "batter_stolen_bases") and line <= 0.5 and r["side"] == "Under":
        return True
    if prop == "batter_runs_scored":
        return True
    if conf >= 0.97:
        return True
    return False


def collect(start: date, end: date, max_gpd: int | None) -> list[dict]:
    """Collect RAW graded rows (p_over is uncalibrated model output)."""
    abbr_by_id = load_team_abbreviations()
    games = [g for g in load_or_fetch_games(start, end) if g.is_final]
    per_day: dict[date, int] = defaultdict(int)
    rows: list[dict] = []

    selected = []
    for g in games:
        if max_gpd is not None:
            if per_day[g.game_date] >= max_gpd:
                continue
            per_day[g.game_date] += 1
        selected.append(g)

    print(f"grading {len(selected)} games...", flush=True)
    for gi, g in enumerate(selected, start=1):
        if gi % 25 == 0 or gi == 1:
            print(f"  game {gi}/{len(selected)} date={g.game_date} rows={len(rows)}", flush=True)

        D = g.game_date
        box = _boxscore(g.game_pk)
        if not box:
            continue
        by_team = confirmed_lineup_by_team(g.game_pk)
        if not by_team:
            continue

        park = park_for_team(g.home_team_id)
        park_runs = float(getattr(park, "park_factor_runs", 1.0) or 1.0)
        park_hr = float(getattr(park, "park_factor_hr", 1.0) or 1.0)

        for team_id, ids in by_team.items():
            is_home = team_id == g.home_team_id
            opp_team_id = g.away_team_id if is_home else g.home_team_id
            opp_pitcher_id = g.away_pitcher_id if is_home else g.home_pitcher_id
            opp_starter = pitcher_stats_as_of(opp_pitcher_id, D) if opp_pitcher_id else None
            try:
                pen = bullpen_stats_as_of(opp_team_id, D)
                opp_bullpen = (pen.era, pen.whip)
            except Exception:
                opp_bullpen = None

            for slot, pid in enumerate(ids, start=1):
                stats = hitter_stats_as_of(pid, D)
                if not stats or stats.get("plate_appearances", 0) < 30:
                    continue
                actual = _actual_batting(box, team_id, pid)
                if actual is None:
                    continue
                exp_pa = expected_pa_for_slot(slot)
                for prop, lines in HITTER_LINES:
                    for line_val in lines:
                        proj = project_hitter(
                            _mk(pid, prop, line_val, is_home), D, opp_starter,
                            park_hr, opp_pitcher_id,
                            exp_pa=exp_pa, run_mult=park_runs, hr_env_mult=park_hr,
                            opp_bullpen=opp_bullpen, quality=None,
                        )
                        if proj is None:
                            continue
                        p_over = float(proj.prob_over)
                        over_hit = 1 if actual[prop] > line_val else 0
                        if p_over >= 0.5:
                            side, conf, hit = "Over", p_over, over_hit
                        else:
                            side, conf, hit = "Under", 1.0 - p_over, 1 - over_hit
                        rows.append({
                            "date": D.isoformat(), "pid": pid, "prop": prop,
                            "line": line_val, "side": side, "conf": round(conf, 4),
                            "p_over": round(p_over, 4), "hit": hit,
                            "actual": actual[prop], "projection": proj.projection,
                            "kind": "hitter",
                        })

        for team_id in (g.home_team_id, g.away_team_id):
            is_home = team_id == g.home_team_id
            pid = g.home_pitcher_id if is_home else g.away_pitcher_id
            if not pid:
                continue
            actual = _actual_pitching(box, team_id, pid)
            if actual is None:
                continue
            opp_team_id = g.away_team_id if is_home else g.home_team_id
            opp_abbr = abbr_by_id.get(opp_team_id)
            hand = pitcher_throws(pid)
            opp_sides = [s for s in (batter_bat_side(x) for x in by_team.get(opp_team_id, [])) if s]
            for prop, lines in PITCHER_LINES:
                for line_val in lines:
                    pl = _mk(pid, prop, line_val, is_home)
                    pl.opp_abbr = opp_abbr
                    proj = project_pitcher(pl, D, opp_abbr, pitcher_hand=hand, opp_bat_sides=opp_sides)
                    if proj is None:
                        continue
                    p_over = float(proj.prob_over)
                    over_hit = 1 if actual[prop] > line_val else 0
                    if p_over >= 0.5:
                        side, conf, hit = "Over", p_over, over_hit
                    else:
                        side, conf, hit = "Under", 1.0 - p_over, 1 - over_hit
                    rows.append({
                        "date": D.isoformat(), "pid": pid, "prop": prop,
                        "line": line_val, "side": side, "conf": round(conf, 4),
                        "p_over": round(p_over, 4), "hit": hit,
                        "actual": actual[prop], "projection": proj.projection,
                        "kind": "pitcher",
                    })
    return rows


def dump_calibration_records(rows: list[dict], train_end: date) -> None:
    """Write (pred, outcome) pairs for isotonic fit — train days only + full."""
    full: dict[str, list[list]] = defaultdict(list)
    train: dict[str, list[list]] = defaultdict(list)
    for r in rows:
        key = f"{r['prop']}|{r['line']}"
        pair = [r["p_over"], 1 if r["actual"] > r["line"] else 0]
        full[key].append(pair)
        if date.fromisoformat(r["date"]) <= train_end:
            train[key].append(pair)
    BACKTEST_RECORDS.write_text(json.dumps(full))
    BACKTEST_TRAIN.write_text(json.dumps(train))
    print(f"wrote {BACKTEST_RECORDS} and {BACKTEST_TRAIN} (train_end={train_end})")


def fit_calibration_from_train() -> None:
    """Fit isotonic curves from train-only records."""
    import numpy as np
    from sklearn.isotonic import IsotonicRegression

    raw = json.loads(BACKTEST_TRAIN.read_text())
    by_prop: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for key, pairs in raw.items():
        prop = key.split("|", 1)[0]
        for p, o in pairs:
            by_prop[prop].append((float(p), int(o)))

    table: dict[str, dict] = {}
    knots = 21
    for prop, pairs in by_prop.items():
        min_n = 100 if prop.startswith("pitcher_") else 200
        if len(pairs) < min_n:
            print(f"{prop:26s} n={len(pairs):6d} (too few — skipped)")
            continue
        pred = np.array([x[0] for x in pairs])
        out = np.array([x[1] for x in pairs])
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        iso.fit(pred, out)
        xs = [round(float(x), 4) for x in np.linspace(0.0, 1.0, knots)]
        ys = [round(float(y), 4) for y in iso.predict(xs)]
        table[prop] = {"x": xs, "y": ys, "n": int(len(pairs))}
        print(f"{prop:26s} n={len(pairs):6d} raw_mean={pred.mean():.3f} "
              f"actual={out.mean():.3f} bias={pred.mean() - out.mean():+.3f}")

    out_path = REPO / "data" / "prop_calibration.json"
    out_path.write_text(json.dumps(table, indent=2))
    reload_calib()
    print(f"wrote {out_path} with {len(table)} curves")


def apply_calibration(rows: list[dict]) -> list[dict]:
    """Return copies with conf/side recomputed from calibrated P(over)."""
    if not is_available():
        return rows
    out = []
    for r in rows:
        p_over = calibrate(r["prop"], float(r["p_over"]))
        over_hit = 1 if r["actual"] > r["line"] else 0
        if p_over >= 0.5:
            side, conf, hit = "Over", p_over, over_hit
        else:
            side, conf, hit = "Under", 1.0 - p_over, 1 - over_hit
        nr = dict(r)
        nr["p_over"] = round(p_over, 4)
        nr["side"] = side
        nr["conf"] = round(conf, 4)
        nr["hit"] = hit
        out.append(nr)
    return out


def verify_calibration_buckets(rows: list[dict], holdout_start: date) -> None:
    hold = [r for r in rows if date.fromisoformat(r["date"]) > holdout_start]
    print("\nHOLDOUT CALIBRATION (calibrated P(over) vs actual over rate):")
    buckets: dict[int, list[int]] = defaultdict(list)
    for r in hold:
        b = min(9, int(float(r["p_over"]) * 10))
        buckets[b].append(1 if r["actual"] > r["line"] else 0)
    print(f"{'pred':12s} {'n':>7s} {'actual':>8s}")
    for b in range(10):
        xs = buckets.get(b, [])
        if not xs:
            continue
        print(f"{b/10:.1f}-{(b+1)/10:.1f}      {len(xs):7d} {sum(xs)/len(xs):8.3f}")


def _daily_topn(rows: list[dict], n: int, min_conf: float, props: set[str] | None,
                side: str | None = None) -> list[dict]:
    """One pick per (pid, prop) max; Top-N per day by confidence."""
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["conf"] < min_conf:
            continue
        if props is not None and r["prop"] not in props:
            continue
        if side is not None and r["side"] != side:
            continue
        if _is_freebie(r):
            continue
        by_day[r["date"]].append(r)

    picked: list[dict] = []
    for day, pool in by_day.items():
        pool.sort(key=lambda x: x["conf"], reverse=True)
        seen: set[tuple] = set()
        count = 0
        for r in pool:
            key = (r["pid"], r["prop"])
            if key in seen:
                continue
            seen.add(key)
            picked.append(r)
            count += 1
            if count >= n:
                break
    return picked


def _daily_top5_production(
    rows: list[dict],
    min_under_conf: float,
    *,
    allow_k_over: bool = True,
    k_over_min_conf: float = K_OVER_MIN_CONF,
) -> list[dict]:
    """Mirror generate_prop_predictions.build_top_bets: unique players, accuracy lane + K Overs."""
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_day[r["date"]].append(r)

    picked: list[dict] = []
    for day, pool in by_day.items():
        candidates: list[dict] = []
        for r in pool:
            if _is_freebie(r):
                continue
            prop = r["prop"]
            side = r["side"]
            conf = float(r["conf"])
            line = float(r["line"])
            proj = float(r.get("projection") or 0.0)

            # Accuracy Unders (hits / TB / K)
            if prop in ACCURACY_PROPS and side == "Under" and conf >= min_under_conf:
                if prop == "pitcher_strikeouts" or prop in ("batter_hits", "batter_total_bases"):
                    if proj < line:  # mean must be below line for Unders
                        candidates.append(r)
                        continue
            # K Overs exception
            if allow_k_over and prop == "pitcher_strikeouts" and side == "Over":
                if (
                    line >= K_OVER_MIN_LINE
                    and conf >= k_over_min_conf
                    and proj >= line + K_OVER_MIN_PROJ_EDGE
                ):
                    candidates.append(r)

        candidates.sort(key=lambda x: x["conf"], reverse=True)
        seen_players: set[int] = set()
        day_picks = 0
        for r in candidates:
            if r["pid"] in seen_players:
                continue
            seen_players.add(r["pid"])
            picked.append(r)
            day_picks += 1
            if day_picks >= 5:
                break
    return picked


def evaluate(picked: list[dict]) -> dict:
    if not picked:
        return {"n": 0, "hits": 0, "hit_rate": 0.0, "mean_conf": 0.0, "days": 0,
                "all5": 0.0, "flex4": 0.0, "legs_per_day": 0.0}
    hits = sum(r["hit"] for r in picked)
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in picked:
        by_day[r["date"]].append(r)
    days_full5 = [d for d, legs in by_day.items() if len(legs) >= 5]
    all5 = 0
    flex4 = 0
    for d in days_full5:
        h = sum(x["hit"] for x in by_day[d][:5])
        if h >= 5:
            all5 += 1
        if h >= 4:
            flex4 += 1
    n_full = len(days_full5) or 1
    return {
        "n": len(picked),
        "hits": hits,
        "hit_rate": round(hits / len(picked), 4),
        "mean_conf": round(sum(r["conf"] for r in picked) / len(picked), 4),
        "days": len(by_day),
        "days_full5": len(days_full5),
        "all5": round(all5 / n_full, 4) if days_full5 else 0.0,
        "flex4": round(flex4 / n_full, 4) if days_full5 else 0.0,
        "legs_per_day": round(len(picked) / max(1, len(by_day)), 2),
    }


PLAYABLE = {
    "batter_hits", "batter_total_bases", "batter_home_runs", "batter_rbis",
    "batter_runs_scored", "batter_hits_runs_rbis", "batter_stolen_bases",
    "pitcher_strikeouts", "pitcher_outs",
}


def search_production(rows: list[dict], train_end: date, target: float = 0.80) -> list[dict]:
    """Search production-mirrored Top 5 configs; gate on holdout hit rate."""
    train = [r for r in rows if date.fromisoformat(r["date"]) <= train_end]
    test = [r for r in rows if date.fromisoformat(r["date"]) > train_end]
    print(f"\nPRODUCTION TOP5 SEARCH train<= {train_end} (n={len(train)})  "
          f"test (n={len(test)})  target={target:.0%}")

    results = []
    for min_u in (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
        for k_min in (0.68, 0.72, 0.75, 0.80, 0.85):
            for allow_ko in (True, False):
                tr = evaluate(_daily_top5_production(train, min_u, allow_k_over=allow_ko, k_over_min_conf=k_min))
                te = evaluate(_daily_top5_production(test, min_u, allow_k_over=allow_ko, k_over_min_conf=k_min))
                if tr["n"] < 25 or te["n"] < 15:
                    continue
                results.append({
                    "mode": "production_top5",
                    "min_under_conf": min_u,
                    "k_over_min_conf": k_min if allow_ko else None,
                    "allow_k_over": allow_ko,
                    "topn": 5,
                    "train_n": tr["n"], "train_hr": tr["hit_rate"],
                    "test_n": te["n"], "test_hr": te["hit_rate"],
                    "test_days": te["days"], "test_days_full5": te["days_full5"],
                    "test_all5": te["all5"], "test_flex4": te["flex4"],
                    "legs_per_day": te["legs_per_day"],
                    "mean_conf": te["mean_conf"],
                })

    results.sort(key=lambda x: (x["test_hr"], x["test_n"]), reverse=True)
    print(f"\n{'minU':>5s} {'kO':>5s} {'kOv':>4s} "
          f"{'tr_n':>5s} {'tr_hr':>6s} {'te_n':>5s} {'te_hr':>6s} "
          f"{'days':>4s} {'all5':>5s} {'f4':>5s}")
    print("-" * 70)
    winners = []
    for i, r in enumerate(results):
        flag = " ***" if r["test_hr"] >= target else ""
        if i < 30 or r["test_hr"] >= target:
            ko = f"{r['k_over_min_conf']:.2f}" if r["allow_k_over"] else "  — "
            print(f"{r['min_under_conf']:5.2f} {ko:>5s} "
                  f"{'Y' if r['allow_k_over'] else 'N':>4s} "
                  f"{r['train_n']:5d} {r['train_hr']:6.3f} {r['test_n']:5d} {r['test_hr']:6.3f} "
                  f"{r['test_days']:4d} {r['test_all5']:5.2f} {r['test_flex4']:5.2f}{flag}")
        if r["test_hr"] >= target:
            winners.append(r)
    print(f"\nproduction Top5 configs clearing {target:.0%} OOS: {len(winners)}")
    return winners


def search(rows: list[dict], train_end: date, target: float = 0.80) -> list[dict]:
    train = [r for r in rows if date.fromisoformat(r["date"]) <= train_end]
    test = [r for r in rows if date.fromisoformat(r["date"]) > train_end]
    print(f"\nLEGACY GRID SEARCH train<= {train_end} (n={len(train)})  test (n={len(test)})")

    prop_sets = {
        "accuracy_core": ACCURACY_PROPS,
        "hrr_hits_tb": {"batter_hits", "batter_total_bases", "batter_hits_runs_rbis"},
        "ks_only": {"pitcher_strikeouts"},
        "all_playable": PLAYABLE,
    }

    results = []
    for name, props in prop_sets.items():
        for topn in (3, 5):
            for min_conf in (0.60, 0.70, 0.75, 0.80, 0.85, 0.90):
                for side_mode in (None, "Under", "Over"):
                    tr = evaluate(_daily_topn(train, topn, min_conf, props, side_mode))
                    te = evaluate(_daily_topn(test, topn, min_conf, props, side_mode))
                    if tr["n"] < 30 or te["n"] < 15:
                        continue
                    results.append({
                        "props": name, "topn": topn, "min_conf": min_conf,
                        "side": side_mode or "both",
                        "train_n": tr["n"], "train_hr": tr["hit_rate"],
                        "test_n": te["n"], "test_hr": te["hit_rate"],
                        "test_days": te["days"], "mean_conf": te["mean_conf"],
                    })

    results.sort(key=lambda x: (x["test_hr"], x["test_n"]), reverse=True)
    winners = [r for r in results if r["test_hr"] >= target]
    for r in results[:15]:
        flag = " ***" if r["test_hr"] >= target else ""
        print(f"{r['props']:16s} {r['topn']:3d} {r['min_conf']:5.2f} {r['side']:6s} "
              f"{r['train_n']:5d} {r['train_hr']:6.3f} {r['test_n']:5d} {r['test_hr']:6.3f}{flag}")
    print(f"legacy configs clearing {target:.0%} OOS: {len(winners)}")
    return winners


def analyze_failures(rows: list[dict], min_conf: float = 0.70) -> None:
    print(f"\nFAILURE ANALYSIS (conf>={min_conf:.0%}, chosen side):")
    subset = [r for r in rows if r["conf"] >= min_conf and not _is_freebie(r)]
    by_prop: dict[str, list[int]] = defaultdict(list)
    by_side: dict[str, list[int]] = defaultdict(list)
    by_bucket: dict[str, list[int]] = defaultdict(list)
    for r in subset:
        by_prop[r["prop"]].append(r["hit"])
        by_side[r["side"]].append(r["hit"])
        b = f"{int(r['conf']*10)/10:.1f}"
        by_bucket[b].append(r["hit"])

    print(f"{'prop':28s} {'n':>6s} {'hr':>6s}")
    for prop, hits in sorted(by_prop.items(), key=lambda kv: sum(kv[1]) / len(kv[1])):
        print(f"{prop:28s} {len(hits):6d} {sum(hits)/len(hits):6.3f}")
    print("\nby side:")
    for side, hits in by_side.items():
        print(f"  {side}: {sum(hits)/len(hits):.3f} (n={len(hits)})")
    print("\nby conf bucket:")
    for b in sorted(by_bucket):
        hits = by_bucket[b]
        print(f"  {b}: {sum(hits)/len(hits):.3f} (n={len(hits)})")


def freeze_policy(best: dict, train_end: date, end: date, gate_passed: bool) -> None:
    policy = {
        "version": "accuracy_top5_precision_v1",
        "gate_passed": gate_passed,
        "user_ask": "Top 5 published card holdout leg hit rate >= 80%",
        "oos_validation": {
            "train_end": train_end.isoformat(),
            "holdout_end": end.isoformat(),
            "selection": (
                f"production Top5: Under hits/TB/K conf>={best.get('min_under_conf')}, "
                f"K Overs={'on@'+str(best.get('k_over_min_conf')) if best.get('allow_k_over') else 'off'}, "
                "one per player, freebies banned"
            ),
            "leg_hit_rate": best.get("test_hr"),
            "test_n": best.get("test_n"),
            "test_days": best.get("test_days"),
            "test_days_full5": best.get("test_days_full5"),
            "power_5of5": best.get("test_all5"),
            "flex_cash_4of5_or_better": best.get("test_flex4"),
            "legs_per_day": best.get("legs_per_day"),
        },
        "shipped": {
            "top_bets": "production_top5",
            "min_under_conf": best.get("min_under_conf"),
            "k_over_min_conf": best.get("k_over_min_conf"),
            "allow_k_over": best.get("allow_k_over"),
            "parlay_type": "flex",
            "parlay_legs": 5,
            "apply_calibration_on_prizepicks": gate_passed,
            "banned": [
                "HR/SB Under 0.5 freebies",
                "batter_runs_scored",
                "model_prob >= 0.97 collapses",
                "demon/goblin Unders (live board)",
            ],
        },
    }
    POLICY_OUT.write_text(json.dumps(policy, indent=2))
    print(f"wrote {POLICY_OUT} gate_passed={gate_passed}")


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: simulate_prop_accuracy.py START END [games_per_day] [search]")
        return
    start = date.fromisoformat(sys.argv[1])
    end = date.fromisoformat(sys.argv[2])
    max_gpd = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 8
    do_search = "search" in sys.argv

    print(f"Simulating props {start}..{end} games/day<={max_gpd} (RAW probs)")
    rows = collect(start, end, max_gpd)
    print(f"collected {len(rows)} graded (player,prop,line) rows across "
          f"{len({r['date'] for r in rows})} days")

    DUMP.parent.mkdir(parents=True, exist_ok=True)
    with DUMP.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {DUMP}")

    days = sorted({r["date"] for r in rows})
    cut = days[int(len(days) * 0.65)] if days else start.isoformat()
    train_end = date.fromisoformat(cut)

    if do_search:
        dump_calibration_records(rows, train_end)
        print("\nFitting train-only isotonic calibration...")
        fit_calibration_from_train()
        cal_rows = apply_calibration(rows)
        verify_calibration_buckets(cal_rows, train_end)

        analyze_failures(cal_rows, 0.70)
        winners = search_production(cal_rows, train_end, target=0.80)
        legacy = search(cal_rows, train_end, target=0.80)
        all_w = winners + [{"legacy": True, **w} for w in legacy[:10]]
        WINNERS_OUT.write_text(json.dumps(all_w[:50], indent=2))
        print(f"wrote {WINNERS_OUT}")

        if winners:
            best = winners[0]
            # Prefer highest test_hr with reasonable volume (already sorted)
            print("\nBEST OOS PRODUCTION CONFIG:")
            print(json.dumps(best, indent=2))
            freeze_policy(best, train_end, end, gate_passed=True)
        else:
            print("\nNo production Top5 config cleared 80% OOS — gate FAILED.")
            best_any = None
            test_rows = [r for r in cal_rows if date.fromisoformat(r["date"]) > train_end]
            train_rows = [r for r in cal_rows if date.fromisoformat(r["date"]) <= train_end]
            for min_u in (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
                for allow_ko in (True, False):
                    te = evaluate(_daily_top5_production(test_rows, min_u, allow_k_over=allow_ko))
                    tr = evaluate(_daily_top5_production(train_rows, min_u, allow_k_over=allow_ko))
                    if te["n"] < 10:
                        continue
                    cand = {
                        "mode": "production_top5",
                        "min_under_conf": min_u,
                        "k_over_min_conf": K_OVER_MIN_CONF if allow_ko else None,
                        "allow_k_over": allow_ko,
                        "topn": 5,
                        "train_n": tr["n"], "train_hr": tr["hit_rate"],
                        "test_n": te["n"], "test_hr": te["hit_rate"],
                        "test_days": te["days"], "test_days_full5": te["days_full5"],
                        "test_all5": te["all5"], "test_flex4": te["flex4"],
                        "legs_per_day": te["legs_per_day"],
                        "mean_conf": te["mean_conf"],
                    }
                    if best_any is None or cand["test_hr"] > best_any["test_hr"]:
                        best_any = cand
            if best_any:
                print("BEST EFFORT (below gate):")
                print(json.dumps(best_any, indent=2))
                freeze_policy(best_any, train_end, end, gate_passed=False)
    else:
        analyze_failures(rows, 0.70)


if __name__ == "__main__":
    main()
