"""Overnight research runner — rotates real experiments, not just board refresh."""

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

# One ablation per cycle (full quick suite over ~6 cycles)
from ablate_v3_components import ABLATIONS_QUICK, Ablation, walk_forward
from backtest_parlays import build_single_candidates, odds_backtest_range
from daily_auto_model import walk_forward_history
from exhaustive_strategy_search import action_to_bet
from historical_odds import HistoricalOddsStore
from mlb_api import load_or_fetch_games, load_team_abbreviations
from strategy_next_tests import build_snapshots, day_actions_for_test, enrich_moneyline

LIVE_START = "2026-06-13"


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"cycle": 0, "ablation_index": 0, "best_ticket_hit_rate": 0.0, "best_game_accuracy": 0.0}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def append_result(row: dict) -> None:
    row["logged_at"] = datetime.now().isoformat(timespec="seconds")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
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


def experiment_ablation(state: dict) -> dict:
    idx = state["ablation_index"] % len(ABLATIONS_QUICK)
    spec = ABLATIONS_QUICK[idx]
    state["ablation_index"] = idx + 1

    store = HistoricalOddsStore()
    start, end, _ = odds_backtest_range(store)
    team_abbr = load_team_abbreviations()
    prior = load_or_fetch_games(date(start.year - 1, 3, 20), date(start.year - 1, 10, 5))
    games = load_or_fetch_games(start, end)
    row = walk_forward(spec, games, team_abbr, prior)
    row["experiment"] = "ablation"
    row["spec_index"] = idx
    return row


def experiment_strategy_thresholds() -> dict:
    from overnight_improve_live import sweep_live_thresholds

    _, _, _, rows, ml = load_ml_rows()
    sweep = sweep_live_thresholds(ml, rows)
    best = max(sweep, key=lambda row: (row["season"]["hit_rate"], row["since_live_start"]["hit_rate"]))
    return {
        "experiment": "strategy_threshold_sweep",
        "sweep": sweep,
        "best_min_medium": best["min_medium_probability"],
        "best_season": best["season"],
        "best_since_live": best["since_live_start"],
    }


def experiment_ticket_strategies() -> dict:
    _, _, _, rows, ml = load_ml_rows()
    strategies = [
        "corr_nl_reject_both",
        "corr_nl_reject_div",
        "corr_nl_reject_time",
        "no_low_parlay_223s",
        "no_low_skip_forced",
    ]
    results = []
    for rule in strategies:
        snaps = build_snapshots(ml, rule)
        results.append(
            {
                "strategy": rule,
                "season": ticket_stats(snaps),
                "since_live_start": ticket_stats(snaps, LIVE_START),
            }
        )
    results.sort(key=lambda row: row["since_live_start"]["hit_rate"], reverse=True)
    return {"experiment": "ticket_strategy_compare", "ranked": results}


def experiment_calibration_windows() -> dict:
    _, _, _, rows, _ = load_ml_rows()
    windows = {}
    for days in (7, 14, 30):
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        subset = [row for row in rows if row["date"] >= cutoff]
        by_conf: dict[str, list[int]] = {}
        for row in subset:
            by_conf.setdefault(row.get("confidence", "Low"), []).append(int(row["correct"]))
        windows[f"last_{days}d"] = {
            conf: {
                "games": len(vals),
                "accuracy": round(sum(vals) / len(vals), 4) if vals else 0.0,
            }
            for conf, vals in sorted(by_conf.items())
        }
    season_correct = sum(int(row["correct"]) for row in rows)
    return {
        "experiment": "calibration_windows",
        "season_game_accuracy": round(season_correct / len(rows), 4) if rows else 0.0,
        "windows": windows,
    }


def experiment_live_counterfactuals() -> dict:
    """What-if on user's live window Jun 13-16."""
    from strategy_next_tests import day_actions_for_test
    from exhaustive_strategy_search import action_to_bet

    _, _, _, rows, ml = load_ml_rows()
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
            "model_probability": bet.get("model_probability"),
        }
    wins = sum(1 for row in scenarios.values() if row.get("won"))
    return {
        "experiment": "live_counterfactuals",
        "days": scenarios,
        "fixed_code_record": f"{wins}-{len(scenarios) - wins}",
    }


def experiment_combined_prob_floor() -> dict:
    """Sweep minimum 2-leg combined probability for corr strategy."""
    from backtest_parlays import settle_parlay
    from strategy_next_tests import live_parlay_pool, pick_corr_parlay

    _, _, _, _, ml = load_ml_rows()
    floors = [0.35, 0.38, 0.40, 0.42, 0.45]
    results = []
    for floor in floors:
        snaps = []
        for day in sorted(ml):
            pool = live_parlay_pool(ml[day])
            ticket = pick_corr_parlay(pool, 2, reject_same_div=True, reject_same_time=True)
            if ticket is None:
                continue
            if ticket["probability"] < floor:
                continue
            bet = action_to_bet(
                __import__("exhaustive_strategy_search").DayAction(legs=ticket["legs"], single=None, label="p2"),
                day,
            )
            snaps.append({"date": day, "bets": [bet]})
        results.append({"min_combined_probability": floor, "season": ticket_stats(snaps), "since_live": ticket_stats(snaps, LIVE_START)})
    best = max(results, key=lambda row: (row["since_live"]["hit_rate"], row["season"]["hit_rate"]))
    return {"experiment": "combined_prob_floor", "sweep": results, "best": best}


EXPERIMENTS = [
    experiment_ablation,
    experiment_strategy_thresholds,
    experiment_ticket_strategies,
    experiment_calibration_windows,
    experiment_live_counterfactuals,
    experiment_combined_prob_floor,
]


def update_report(state: dict, latest: dict) -> None:
    history = []
    if REPORT_PATH.exists():
        try:
            history = json.loads(REPORT_PATH.read_text()).get("history", [])
        except json.JSONDecodeError:
            history = []
    history.append(latest)
    history = history[-40:]

    if latest.get("experiment") == "ablation" and latest.get("accuracy", 0) > state.get("best_game_accuracy", 0):
        state["best_game_accuracy"] = latest["accuracy"]
        state["best_game_model"] = latest.get("name")

    if latest.get("experiment") == "strategy_threshold_sweep":
        hit = latest.get("best_since_live", {}).get("hit_rate", 0)
        if hit > state.get("best_ticket_hit_rate", 0):
            state["best_ticket_hit_rate"] = hit
            state["best_ticket_threshold"] = latest.get("best_min_medium")

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cycles_completed": state.get("cycle", 0),
        "best_game_accuracy": state.get("best_game_accuracy"),
        "best_game_model": state.get("best_game_model"),
        "best_ticket_hit_rate": state.get("best_ticket_hit_rate"),
        "best_ticket_threshold": state.get("best_ticket_threshold"),
        "latest": latest,
        "history": history,
    }
    REPORT_PATH.write_text(json.dumps(payload, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle", type=int, default=1)
    args = parser.parse_args()

    state = load_state()
    state["cycle"] = args.cycle
    experiment_fn = EXPERIMENTS[(args.cycle - 1) % len(EXPERIMENTS)]
    name = experiment_fn.__name__

    print(f"overnight_research cycle={args.cycle} experiment={name}", flush=True)
    try:
        result = experiment_fn(state)
    except Exception as error:
        result = {"experiment": name, "error": str(error)}
        print(f"FAILED: {error}", flush=True)

    append_result(result)
    update_report(state, result)
    save_state(state)
    print(json.dumps(result, indent=2)[:1200], flush=True)


if __name__ == "__main__":
    main()
