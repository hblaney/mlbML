"""Overnight research — ticket/strategy strides only. No redundant baseline ablation."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "data" / "overnight-research-state.json"
LOG_PATH = ROOT / "data" / "overnight-research.jsonl"
REPORT_PATH = ROOT / "public" / "overnight-research-report.json"

from backtest_parlays import build_single_candidates, odds_backtest_range, settle_parlay
from daily_auto_model import walk_forward_history
from exhaustive_strategy_search import DayAction, action_to_bet
from historical_odds import HistoricalOddsStore
from mlb_api import load_or_fetch_games, load_team_abbreviations
from strategy_next_tests import (
    build_snapshots,
    day_actions_for_test,
    enrich_moneyline,
    live_parlay_pool,
    pick_corr_parlay,
)

LIVE_START = "2026-06-13"
# Already measured — do not re-run full walk-forward ablation in overnight loop.
BASELINE_GAME_ACCURACY = 0.6066
SHIPPED_TICKET_RECORD = "52-27"


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"cycle": 0, "completed_experiments": [], "best_ticket_hit_rate": 0.6582}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def append_result(row: dict) -> None:
    row["logged_at"] = datetime.now().isoformat(timespec="seconds")
    with LOG_PATH.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def load_ml_rows():
    store = HistoricalOddsStore()
    start, end, odds_meta = odds_backtest_range(store)
    team_abbr = load_team_abbreviations()
    prior = load_or_fetch_games(date(start.year - 1, 3, 20), date(start.year - 1, 10, 5))
    games = load_or_fetch_games(start, end)
    rows = walk_forward_history(games, team_abbr, prior_games=prior)
    ml = enrich_moneyline(build_single_candidates(rows, store), rows)
    return start, end, odds_meta, rows, ml


def ticket_stats(snaps: list[dict], since: str | None = None) -> dict:
    subset = [snap for snap in snaps if not since or snap["date"] >= since]
    wins = sum(1 for snap in subset if snap["bets"][0].get("won"))
    total = len(subset)
    return {
        "tickets": total,
        "record": f"{wins}-{total - wins}",
        "hit_rate": round(wins / total, 4) if total else 0.0,
    }


def experiment_status(_state: dict) -> dict:
    """Anchor: what we know + what's shipped."""
    return {
        "experiment": "status",
        "game_model": f"v2.2-h2h @ {BASELINE_GAME_ACCURACY:.2%} (ablating won't beat this tonight)",
        "ticket_strategy_shipped": f"corr_nl + 68% legs + series fade = {SHIPPED_TICKET_RECORD}",
        "focus": "ticket selection and live rules — not re-running baseline ablation",
    }


def experiment_strategy_compare(_state: dict) -> dict:
    _, _, _, _, ml = load_ml_rows()
    strategies = [
        "corr_nl_reject_both",
        "corr_nl_reject_div",
        "corr_nl_reject_time",
        "no_low_parlay_223s",
        "no_low_skip_forced",
    ]
    ranked = []
    for rule in strategies:
        snaps = build_snapshots(ml, rule)
        ranked.append(
            {
                "strategy": rule,
                "season": ticket_stats(snaps),
                "since_live": ticket_stats(snaps, LIVE_START),
            }
        )
    ranked.sort(key=lambda row: (row["since_live"]["hit_rate"], row["season"]["hit_rate"]), reverse=True)
    return {"experiment": "strategy_compare", "ranked": ranked}


def experiment_min_leg_probability_sweep(_state: dict) -> dict:
    from overnight_improve_live import sweep_live_thresholds

    _, _, _, rows, ml = load_ml_rows()
    sweep = sweep_live_thresholds(ml, rows)
    best = max(sweep, key=lambda row: (row["season"]["hit_rate"], row["since_live_start"]["hit_rate"]))
    return {
        "experiment": "min_leg_probability_sweep",
        "sweep": sweep,
        "best": best,
        "action": f"Keep 68% floor — best season {best['season']['record']}",
    }


def experiment_combined_prob_floor(_state: dict) -> dict:
    _, _, _, _, ml = load_ml_rows()
    floors = [0.35, 0.38, 0.40, 0.42, 0.45, 0.48]
    results = []
    for floor in floors:
        snaps = []
        for day in sorted(ml):
            pool = live_parlay_pool(ml[day])
            ticket = pick_corr_parlay(pool, 2, reject_same_div=True, reject_same_time=True)
            if ticket is None or ticket["probability"] < floor:
                continue
            bet = action_to_bet(DayAction(legs=ticket["legs"], single=None, label="p2"), day)
            snaps.append({"date": day, "bets": [bet]})
        results.append(
            {
                "min_combined_probability": floor,
                "season": ticket_stats(snaps),
                "since_live": ticket_stats(snaps, LIVE_START),
            }
        )
    best = max(results, key=lambda row: (row["season"]["hit_rate"], row["since_live"]["hit_rate"]))
    return {"experiment": "combined_prob_floor", "sweep": results, "best": best}


def experiment_skip_forced_parlays(_state: dict) -> dict:
    """Forced top-2 legs drag live — compare with skip."""
    _, _, _, _, ml = load_ml_rows()
    variants = {
        "current_corr": "corr_nl_reject_both",
        "skip_forced": "no_low_skip_forced",
    }
    out = {}
    for label, rule in variants.items():
        snaps = build_snapshots(ml, rule)
        out[label] = {"rule": rule, "season": ticket_stats(snaps), "since_live": ticket_stats(snaps, LIVE_START)}
    return {"experiment": "skip_forced_parlays", "variants": out}


def experiment_calibration_windows(_state: dict) -> dict:
    _, _, _, rows, _ = load_ml_rows()
    windows = {}
    for days in (7, 14, 30):
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        subset = [row for row in rows if row["date"] >= cutoff]
        by_conf: dict[str, list[int]] = {}
        for row in subset:
            by_conf.setdefault(row.get("confidence", "Low"), []).append(int(row["correct"]))
        windows[f"last_{days}d"] = {
            conf: {"games": len(vals), "accuracy": round(sum(vals) / len(vals), 4) if vals else 0.0}
            for conf, vals in sorted(by_conf.items())
        }
    return {"experiment": "calibration_windows", "windows": windows}


def experiment_live_counterfactuals(_state: dict) -> dict:
    _, _, _, _, ml = load_ml_rows()
    days = ["2026-06-13", "2026-06-14", "2026-06-15", "2026-06-16"]
    scenarios = {}
    for day in days:
        if day not in ml:
            continue
        actions = day_actions_for_test(ml[day], "corr_nl_reject_both")
        if not actions:
            scenarios[day] = {"ticket": None, "won": None}
            continue
        bet = action_to_bet(actions[0], day)
        scenarios[day] = {
            "ticket": [leg["team"] for leg in (bet.get("legs") or [bet])],
            "won": bool(bet.get("won")),
        }
    wins = sum(1 for row in scenarios.values() if row.get("won"))
    return {
        "experiment": "live_counterfactuals",
        "fixed_code_record": f"{wins}-{len(scenarios) - wins}",
        "days": scenarios,
    }


def experiment_high_elite_only_parlays(_state: dict) -> dict:
    """Require at least one High/Elite leg in every 2-leg ticket."""
    _, _, _, _, ml = load_ml_rows()
    snaps = []
    for day in sorted(ml):
        pool = [
            c
            for c in live_parlay_pool(ml[day])
            if c.get("confidence") in {"High", "Elite"}
        ]
        ticket = pick_corr_parlay(pool, 2, reject_same_div=True, reject_same_time=True)
        if ticket is None:
            continue
        bet = action_to_bet(DayAction(legs=ticket["legs"], single=None, label="p2"), day)
        snaps.append({"date": day, "bets": [bet]})
    return {
        "experiment": "high_elite_only_parlays",
        "season": ticket_stats(snaps),
        "since_live": ticket_stats(snaps, LIVE_START),
    }


EXPERIMENTS = [
    experiment_status,
    experiment_strategy_compare,
    experiment_min_leg_probability_sweep,
    experiment_combined_prob_floor,
    experiment_skip_forced_parlays,
    experiment_calibration_windows,
    experiment_live_counterfactuals,
    experiment_high_elite_only_parlays,
]


def update_report(state: dict, latest: dict) -> None:
    history = []
    if REPORT_PATH.exists():
        try:
            history = json.loads(REPORT_PATH.read_text()).get("history", [])
        except json.JSONDecodeError:
            pass
    history.append(latest)
    history = history[-50:]

    hit = None
    if "season" in latest and "hit_rate" in latest["season"]:
        hit = latest["season"]["hit_rate"]
    if latest.get("best", {}).get("season", {}).get("hit_rate"):
        hit = latest["best"]["season"]["hit_rate"]
    if hit and hit > state.get("best_ticket_hit_rate", 0):
        state["best_ticket_hit_rate"] = hit

    REPORT_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "cycles_completed": state.get("cycle", 0),
                "shipped_ticket_record": SHIPPED_TICKET_RECORD,
                "game_model_accuracy": BASELINE_GAME_ACCURACY,
                "best_ticket_hit_rate_found": state.get("best_ticket_hit_rate"),
                "latest": latest,
                "history": history,
            },
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle", type=int, default=1)
    args = parser.parse_args()

    state = load_state()
    state["cycle"] = args.cycle
    experiment_fn = EXPERIMENTS[(args.cycle - 1) % len(EXPERIMENTS)]
    name = experiment_fn.__name__

    if name in state.get("completed_experiments", []) and name != "experiment_status":
        print(f"skip {name} (already completed this session)", flush=True)
        return

    print(f"overnight_research cycle={args.cycle} {name}", flush=True)
    try:
        result = experiment_fn(state)
        state.setdefault("completed_experiments", []).append(name)
    except Exception as error:
        result = {"experiment": name, "error": str(error)}
        print(f"FAILED: {error}", flush=True)

    append_result(result)
    update_report(state, result)
    save_state(state)
    print(json.dumps(result, indent=2)[:2000], flush=True)


if __name__ == "__main__":
    main()
