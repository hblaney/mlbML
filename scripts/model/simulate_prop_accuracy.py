"""Daily prop accuracy simulator + strategy search.

For every finished game in a date range we project ALL standard prop lines for
every starter in the lineup / SP, pick a side (Over if P(over)>=0.5 else Under),
and grade it. Then we search selection policies (probability floor, prop family,
Top-N per day) to find configurations whose out-of-sample hit rate clears a
target (default 80%).

This is an accuracy search, not an ROI search. We do not need historical market
lines — only whether the model's chosen side landed.

Usage:
  python3 simulate_prop_accuracy.py 2026-04-04 2026-05-15 [games_per_day]
  python3 simulate_prop_accuracy.py 2026-04-04 2026-05-15 6 search
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
from prop_calibration import calibrate, is_available
from handedness_provider import pitcher_throws, batter_bat_side

REPO = Path(__file__).resolve().parents[2]
DUMP = REPO / "data" / "prop_sim_records.jsonl"

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


def collect(start: date, end: date, max_gpd: int | None) -> list[dict]:
    abbr_by_id = load_team_abbreviations()
    games = [g for g in load_or_fetch_games(start, end) if g.is_final]
    per_day: dict[date, int] = defaultdict(int)
    rows: list[dict] = []
    use_calib = is_available()

    for g in games:
        if max_gpd is not None:
            if per_day[g.game_date] >= max_gpd:
                continue
            per_day[g.game_date] += 1

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
                        p_over = calibrate(prop, proj.prob_over) if use_calib else proj.prob_over
                        over_hit = 1 if actual[prop] > line_val else 0
                        # Choose the side the model thinks is more likely.
                        if p_over >= 0.5:
                            side, conf, hit = "Over", p_over, over_hit
                        else:
                            side, conf, hit = "Under", 1.0 - p_over, 1 - over_hit
                        rows.append({
                            "date": D.isoformat(), "pid": pid, "prop": prop,
                            "line": line_val, "side": side, "conf": round(conf, 4),
                            "p_over": round(p_over, 4), "hit": hit,
                            "actual": actual[prop], "kind": "hitter",
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
                    p_over = calibrate(prop, proj.prob_over) if use_calib else proj.prob_over
                    over_hit = 1 if actual[prop] > line_val else 0
                    if p_over >= 0.5:
                        side, conf, hit = "Over", p_over, over_hit
                    else:
                        side, conf, hit = "Under", 1.0 - p_over, 1 - over_hit
                    rows.append({
                        "date": D.isoformat(), "pid": pid, "prop": prop,
                        "line": line_val, "side": side, "conf": round(conf, 4),
                        "p_over": round(p_over, 4), "hit": hit,
                        "actual": actual[prop], "kind": "pitcher",
                    })
    return rows


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


def evaluate(picked: list[dict]) -> dict:
    if not picked:
        return {"n": 0, "hits": 0, "hit_rate": 0.0, "mean_conf": 0.0, "days": 0}
    hits = sum(r["hit"] for r in picked)
    days = len({r["date"] for r in picked})
    return {
        "n": len(picked),
        "hits": hits,
        "hit_rate": round(hits / len(picked), 4),
        "mean_conf": round(sum(r["conf"] for r in picked) / len(picked), 4),
        "days": days,
    }


PLAYABLE = {
    "batter_hits", "batter_total_bases", "batter_home_runs", "batter_rbis",
    "batter_runs_scored", "batter_hits_runs_rbis", "batter_stolen_bases",
    "pitcher_strikeouts", "pitcher_outs",
}


def search(rows: list[dict], train_end: date, target: float = 0.80) -> list[dict]:
    train = [r for r in rows if date.fromisoformat(r["date"]) <= train_end]
    test = [r for r in rows if date.fromisoformat(r["date"]) > train_end]
    print(f"\nSEARCH train<= {train_end} (n={len(train)})  test (n={len(test)})  target={target:.0%}")

    prop_sets = {
        "all_playable": PLAYABLE,
        "hitter_core": {
            "batter_hits", "batter_total_bases", "batter_hits_runs_rbis",
            "batter_rbis", "batter_runs_scored",
        },
        "pitcher_ks_outs": {"pitcher_strikeouts", "pitcher_outs"},
        "ks_only": {"pitcher_strikeouts"},
        "hrr_hits_tb": {"batter_hits", "batter_total_bases", "batter_hits_runs_rbis"},
        "unders_friendly": {
            "batter_hits", "batter_total_bases", "batter_home_runs",
            "batter_doubles", "batter_stolen_bases", "pitcher_strikeouts",
        },
    }

    results = []
    for name, props in prop_sets.items():
        for topn in (3, 5, 8):
            for min_conf in (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
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

    # Rank by test hit rate, then volume
    results.sort(key=lambda x: (x["test_hr"], x["test_n"]), reverse=True)

    print(f"\n{'props':16s} {'N':>3s} {'conf':>5s} {'side':>6s} "
          f"{'tr_n':>5s} {'tr_hr':>6s} {'te_n':>5s} {'te_hr':>6s} {'days':>4s}")
    print("-" * 72)
    shown = 0
    winners = []
    for r in results:
        flag = " ***" if r["test_hr"] >= target else ""
        if shown < 25 or r["test_hr"] >= target:
            print(f"{r['props']:16s} {r['topn']:3d} {r['min_conf']:5.2f} {r['side']:6s} "
                  f"{r['train_n']:5d} {r['train_hr']:6.3f} {r['test_n']:5d} {r['test_hr']:6.3f} "
                  f"{r['test_days']:4d}{flag}")
            shown += 1
        if r["test_hr"] >= target:
            winners.append(r)
    print(f"\nconfigs clearing {target:.0%} OOS: {len(winners)}")
    return winners


def analyze_failures(rows: list[dict], min_conf: float = 0.70) -> None:
    print(f"\nFAILURE ANALYSIS (conf>={min_conf:.0%}, chosen side):")
    subset = [r for r in rows if r["conf"] >= min_conf]
    by_prop: dict[str, list[int]] = defaultdict(list)
    by_side: dict[str, list[int]] = defaultdict(list)
    by_bucket: dict[str, list[int]] = defaultdict(list)
    for r in subset:
        by_prop[r["prop"]].append(r["hit"])
        by_side[r["side"]].append(r["hit"])
        b = f"{int(r['conf']*10)/10:.1f}"
        by_bucket[b].append(r["hit"])

    print(f"{'prop':28s} {'n':>6s} {'hr':>6s}")
    for prop, hits in sorted(by_prop.items(), key=lambda kv: sum(kv[1])/len(kv[1])):
        print(f"{prop:28s} {len(hits):6d} {sum(hits)/len(hits):6.3f}")
    print("\nby side:")
    for side, hits in by_side.items():
        print(f"  {side}: {sum(hits)/len(hits):.3f} (n={len(hits)})")
    print("\nby conf bucket:")
    for b in sorted(by_bucket):
        hits = by_bucket[b]
        print(f"  {b}: {sum(hits)/len(hits):.3f} (n={len(hits)})")


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: simulate_prop_accuracy.py START END [games_per_day] [search]")
        return
    start = date.fromisoformat(sys.argv[1])
    end = date.fromisoformat(sys.argv[2])
    max_gpd = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 6
    do_search = "search" in sys.argv

    print(f"Simulating props {start}..{end} games/day<={max_gpd} calib={is_available()}")
    rows = collect(start, end, max_gpd)
    print(f"collected {len(rows)} graded (player,prop,line) rows across "
          f"{len({r['date'] for r in rows})} days")

    DUMP.parent.mkdir(parents=True, exist_ok=True)
    with DUMP.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {DUMP}")

    # Baseline: all picks at various floors
    print("\nBASELINE (all qualifying picks, no Top-N cap):")
    for c in (0.55, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90):
        sub = [r for r in rows if r["conf"] >= c and r["prop"] in PLAYABLE]
        if not sub:
            continue
        hr = sum(r["hit"] for r in sub) / len(sub)
        print(f"  conf>={c:.2f}: n={len(sub):5d} hit_rate={hr:.3f}")

    analyze_failures(rows, 0.70)

    if do_search:
        # Hold out last ~30% of days
        days = sorted({r["date"] for r in rows})
        cut = days[int(len(days) * 0.65)] if days else start.isoformat()
        winners = search(rows, date.fromisoformat(cut), target=0.80)
        out = REPO / "data" / "prop_strategy_winners.json"
        out.write_text(json.dumps(winners[:50], indent=2))
        print(f"wrote {out}")

        if winners:
            best = winners[0]
            print("\nBEST OOS CONFIG:")
            print(json.dumps(best, indent=2))
        else:
            print("\nNo config cleared 80% OOS yet — raising floors / narrowing props next.")


if __name__ == "__main__":
    main()
