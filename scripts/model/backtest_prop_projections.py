"""Walk-forward projection backtest for the prop model (leakage-safe).

For every finished game in a date range we reconstruct EXACTLY what the model
would have seen the morning of that game:
  - point-in-time hitter/pitcher stats (through the prior day)
  - the real posted batting order (from that game's box score)
  - opposing starter + bullpen as-of the date
  - park factors, handedness platoon, and (optionally) Statcast quality
...then we project standard-line hitter props (hits o0.5 / o1.5, total bases
o1.5) and grade the model's probability against what the player ACTUALLY did.

This measures the thing that matters for improving the model: are the projected
probabilities calibrated and do they beat a naive baseline? It does NOT measure
betting ROI — that needs historical prop *lines/prices*, which our odds plan does
not provide (see the note printed at the end).

Usage:
  python3 backtest_prop_projections.py 2026-05-01 2026-05-14 [max_games_per_day] [statcast]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT_LOCAL = Path(__file__).resolve().parents[2]

from mlb_api import load_or_fetch_games, load_team_abbreviations
from hitter_stats_provider import hitter_stats_as_of
from pitcher_stats_provider import pitcher_stats_as_of
from bullpen_provider import bullpen_stats_as_of
from lineup_provider import _boxscore, confirmed_lineup_by_team, expected_pa_for_slot
from park_factors import park_for_team
from prop_projections import project_hitter, project_pitcher
from prop_odds_provider import PropLine
from handedness_provider import pitcher_throws, batter_bat_side

# Full daily line universe the Top-5 selector ranks over (PP ladders + standards).
HITTER_GRADE = [
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
PITCHER_GRADE = [
    ("pitcher_strikeouts", [3.5, 4.5, 5.5, 6.5, 7.5]),
    ("pitcher_outs", [14.5, 15.5, 17.5, 18.5]),
    ("pitcher_earned_runs", [1.5, 2.5, 3.5]),
    ("pitcher_hits_allowed", [4.5, 5.5, 6.5]),
]


def _mk_line(pid: int, prop: str, line: float, is_home: bool) -> PropLine:
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
        "batter_hits": hits,
        "batter_total_bases": tb,
        "batter_home_runs": hr,
        "batter_rbis": rbi,
        "batter_runs_scored": runs,
        "batter_hits_runs_rbis": hits + runs + rbi,
        "batter_walks": bb,
        "batter_stolen_bases": sb,
        "batter_singles": singles,
        "batter_doubles": doubles,
    }


def _actual_pitching(box: dict, team_id: int, pid: int) -> dict | None:
    node = _player_node(box, team_id, pid)
    pit = (node or {}).get("stats", {}).get("pitching", {})
    if not pit or int(pit.get("gamesStarted", 0) or 0) != 1:
        return None
    outs = _parse_ip(pit.get("inningsPitched")) * 3.0
    return {
        "pitcher_strikeouts": float(pit.get("strikeOuts", 0) or 0),
        "pitcher_outs": outs,
        "pitcher_earned_runs": float(pit.get("earnedRuns", 0) or 0),
        "pitcher_hits_allowed": float(pit.get("hits", 0) or 0),
    }


def run_backtest(start: date, end: date, max_games_per_day: int | None, use_statcast: bool,
                 apply_calib: bool = False):
    quality_fn = None
    if use_statcast:
        from player_statcast_provider import hitter_quality
        quality_fn = hitter_quality

    calib_fn = None
    if apply_calib:
        from prop_calibration import calibrate
        calib_fn = calibrate

    def rec(prop: str, prob: float) -> float:
        return calib_fn(prop, prob) if calib_fn else prob

    abbr_by_id = load_team_abbreviations()
    games = [g for g in load_or_fetch_games(start, end) if g.is_final]
    per_day: dict[date, int] = defaultdict(int)

    # records[(prop,line)] = list of (pred_prob, outcome)
    records: dict[tuple[str, float], list[tuple[float, int]]] = defaultdict(list)
    n_hitters = 0
    n_pitchers = 0

    for g in games:
        if max_games_per_day is not None:
            if per_day[g.game_date] >= max_games_per_day:
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

        # ---- Hitters ----
        for team_id, ids in by_team.items():
            is_home = team_id == g.home_team_id
            opp_team_id = g.away_team_id if is_home else g.home_team_id
            opp_pitcher_id = g.away_pitcher_id if is_home else g.home_pitcher_id
            opp_starter = None
            if opp_pitcher_id:
                try:
                    opp_starter = pitcher_stats_as_of(opp_pitcher_id, D)
                except Exception:
                    opp_starter = None
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
                quality = quality_fn(pid, D) if quality_fn else None
                exp_pa = expected_pa_for_slot(slot)
                n_hitters += 1
                for prop, lines in HITTER_GRADE:
                    for line_val in lines:
                        proj = project_hitter(
                            _mk_line(pid, prop, line_val, is_home), D, opp_starter,
                            park_hr, opp_pitcher_id,
                            exp_pa=exp_pa, run_mult=park_runs, hr_env_mult=park_hr,
                            opp_bullpen=opp_bullpen, quality=quality,
                        )
                        if proj is None:
                            continue
                        outcome = 1 if actual[prop] > line_val else 0
                        records[(prop, line_val)].append((rec(prop, proj.prob_over), outcome))

        # ---- Starting pitchers ----
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
            opp_sides = [batter_bat_side(x) for x in by_team.get(opp_team_id, [])]
            opp_sides = [s for s in opp_sides if s]
            n_pitchers += 1
            for prop, lines in PITCHER_GRADE:
                for line_val in lines:
                    pl = _mk_line(pid, prop, line_val, is_home)
                    pl.opp_abbr = opp_abbr
                    proj = project_pitcher(
                        pl, D, opp_abbr, pitcher_hand=hand, opp_bat_sides=opp_sides,
                    )
                    if proj is None:
                        continue
                    outcome = 1 if actual[prop] > line_val else 0
                    records[(prop, line_val)].append((rec(prop, proj.prob_over), outcome))

    return records, n_hitters, n_pitchers, len(games)


def _report(records: dict[tuple[str, float], list[tuple[float, int]]]):
    print(f"\n{'PROP':28s} {'n':>6s} {'base':>6s} {'pred':>6s} {'bias':>7s} {'acc':>6s} {'brier':>7s} {'baseB':>7s} {'skill':>6s}")
    print("-" * 90)
    for (prop, line_val), rows in sorted(records.items()):
        if not rows:
            continue
        n = len(rows)
        base_rate = sum(o for _, o in rows) / n           # actual over rate
        mean_pred = sum(p for p, _ in rows) / n           # model mean prob
        bias = mean_pred - base_rate                      # >0 = overpredicts overs
        correct = sum(1 for p, o in rows if (p >= 0.5) == (o == 1))
        acc = correct / n
        brier = sum((p - o) ** 2 for p, o in rows) / n
        base_brier = sum((base_rate - o) ** 2 for _, o in rows) / n
        # skill: how much better than the base-rate guess (positive = model adds value)
        skill = (base_brier - brier) / base_brier if base_brier > 0 else 0.0
        label = f"{prop} o{line_val}"
        flag = "  <-- BAD" if brier > base_brier else ""
        print(f"{label:28s} {n:6d} {base_rate:6.3f} {mean_pred:6.3f} {bias:+7.3f} "
              f"{acc:6.3f} {brier:7.4f} {base_brier:7.4f} {skill:+6.2f}{flag}")

    # Calibration across all hit props combined
    print("\nCALIBRATION (all graded props pooled):")
    buckets: dict[int, list[int]] = defaultdict(list)
    for rows in records.values():
        for p, o in rows:
            buckets[min(9, int(p * 10))].append(o)
    print(f"{'pred range':12s} {'n':>7s} {'actual':>8s}")
    for b in range(10):
        rows = buckets.get(b, [])
        if not rows:
            continue
        lo, hi = b / 10, (b + 1) / 10
        print(f"{lo:.1f}-{hi:.1f}      {len(rows):7d} {sum(rows)/len(rows):8.3f}")


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: backtest_prop_projections.py START END [max_games_per_day] [statcast]")
        return
    start = date.fromisoformat(sys.argv[1])
    end = date.fromisoformat(sys.argv[2])
    max_gpd = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else None
    flags = sys.argv[3:]
    use_statcast = "statcast" in flags
    apply_calib = "calibrated" in flags
    dump = "dump" in flags

    print(f"Walk-forward prop backtest {start}..{end} "
          f"(max_games/day={max_gpd}, statcast={use_statcast}, calibrated={apply_calib})")
    records, n_hitters, n_pitchers, n_games = run_backtest(
        start, end, max_gpd, use_statcast, apply_calib=apply_calib)
    print(f"graded {n_hitters} hitter-games + {n_pitchers} pitcher-games across {n_games} games")
    _report(records)

    if dump:
        out = REPO_ROOT_LOCAL / "data" / "prop_backtest_records.json"
        payload = {f"{prop}|{line}": rows for (prop, line), rows in records.items()}
        out.write_text(json.dumps(payload))
        print(f"\ndumped raw (pred,outcome) pairs -> {out}")

        # Train-only split (~first 65% of calendar days) for honest isotonic fit.
        day_keys: dict[str, list] = defaultdict(list)
        # records lack dates — also dump a date-keyed companion from the sim path.
        # Keep a simple chronological half-split by list order within each key as
        # a fallback when dates aren't attached (order follows game walk-forward).
        train_payload: dict[str, list] = {}
        for key, rows in payload.items():
            cut = max(1, int(len(rows) * 0.65))
            train_payload[key] = rows[:cut]
        train_out = REPO_ROOT_LOCAL / "data" / "prop_backtest_records_train.json"
        train_out.write_text(json.dumps(train_payload))
        print(f"dumped train-split records -> {train_out}")

    print("\nNOTE: this validates PROJECTION calibration only. True betting ROI needs "
          "historical prop LINES/PRICES, which our current odds plan does not provide.")


if __name__ == "__main__":
    main()
