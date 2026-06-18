"""Exhaustive overnight sweep — every strategy × stake tier × leg-prob floor.

Loads walk-forward data once, caches snapshots, scores on realistic $23 bankroll.
Writes incremental results + consolidated morning report.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "overnight-ml-cache.pkl"
STATE_PATH = ROOT / "data" / "overnight-exhaustive-state.json"
LOG_PATH = ROOT / "data" / "overnight-exhaustive.jsonl"
REPORT_PATH = ROOT / "public" / "overnight-morning-report.json"
LIVE_BANKROLL = 23.28

from backtest_parlays import build_single_candidates, odds_backtest_range
from daily_auto_model import walk_forward_history
from exhaustive_strategy_search import DayAction, action_to_bet
from historical_odds import HistoricalOddsStore
from mlb_api import load_or_fetch_games, load_team_abbreviations
from strategy_next_tests import (
    STAKE_TIERED,
    build_snapshots,
    day_actions_for_test,
    enrich_moneyline,
    live_parlay_pool,
    load_moneyline_by_day,
    model_pick_candidates,
    pick_always_n_corr,
    pick_corr_parlay,
    pick_two_or_three_or_single_custom,
    season_start_for,
    no_low_pool,
)
from strategy_research import compound

# --- strategy catalog ---
STRATEGY_RULES = [
    "no_low_parlay_223s",
    "corr_nl_reject_both",
    "corr_nl_reject_div",
    "corr_nl_reject_time",
    "corr_nl_penalize_div15",
    "corr_nl_penalize_time10",
    "corr_nl_penalize_both",
    "best_ticket",
    "no_low_best_ticket",
    "no_low_skip_forced",
    "no_low_selective_best",
    "no_low_min_edge5",
    "no_low_min_edge6",
    "no_low_min_edge7",
    "no_low_min_edge8",
    "no_low_min_edge9",
    "no_low_min_edge10",
    "no_low_min_edge12",
    "no_low_min_score025",
    "no_low_min_score050",
    "no_low_min_score075",
    "no_low_min_score100",
]

STAKE_TIERS: dict[str, dict[int, float]] = {
    "shipped_35_45_10": {1: 0.35, 2: 0.45, 3: 0.10},
    "shipped_35_40_30": {1: 0.35, 2: 0.40, 3: 0.30},
    "aggressive_45_50_35": {1: 0.45, 2: 0.50, 3: 0.35},
    "mod_25_30_20": {1: 0.25, 2: 0.30, 3: 0.20},
    "cons_20_25_15": {1: 0.20, 2: 0.25, 3: 0.15},
    "safe_15_20_10": {1: 0.15, 2: 0.20, 3: 0.10},
    "flat_25": {1: 0.25, 2: 0.25, 3: 0.25},
    "flat_20": {1: 0.20, 2: 0.20, 3: 0.20},
    "flat_15": {1: 0.15, 2: 0.15, 3: 0.15},
    "flat_10": {1: 0.10, 2: 0.10, 3: 0.10},
}

LEG_PROB_FLOORS = [0.62, 0.65, 0.68, 0.70, 0.72]


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"completed_keys": [], "total_tested": 0}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def append_log(row: dict) -> None:
    row["logged_at"] = datetime.now().isoformat(timespec="seconds")
    with LOG_PATH.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def load_ml(*, refresh: bool = False) -> dict[str, list[dict]]:
    if not refresh and CACHE_PATH.exists():
        with CACHE_PATH.open("rb") as handle:
            cached = pickle.load(handle)
        if cached.get("end") == (date.today() - __import__("datetime").timedelta(days=1)).isoformat():
            return cached["ml"]

    store = HistoricalOddsStore()
    start, end, _ = odds_backtest_range(store)
    prior = (season_start_for(start.year - 1), date(start.year - 1, 10, 5))
    ml, _ = load_moneyline_by_day(start, end, prior[0], prior[1])
    ml = {d: c for d, c in ml.items() if date.fromisoformat(d) <= end}
    team_abbr = load_team_abbreviations()
    games = load_or_fetch_games(start, end)
    rows = walk_forward_history(games, team_abbr, prior_games=load_or_fetch_games(*prior))
    ml = enrich_moneyline(build_single_candidates(rows, store), rows)

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("wb") as handle:
        pickle.dump({"ml": ml, "end": end.isoformat(), "built_at": datetime.now().isoformat()}, handle)
    return ml


def max_losing_streak(snaps: list[dict]) -> int:
    mx = cur = 0
    for snap in snaps:
        if snap["bets"][0]["won"]:
            mx = max(mx, cur)
            cur = 0
        else:
            cur += 1
    return max(mx, cur)


def build_corr_nl_snaps(ml: dict[str, list[dict]], min_prob: float) -> list[dict]:
    """corr_nl_reject_both with custom parlay leg probability floor."""
    snaps = []
    for day in sorted(ml):
        live = model_pick_candidates(ml[day])
        pool = [
            c
            for c in no_low_pool(live)
            if c["model_probability"] >= min_prob
        ]
        p2 = pick_always_n_corr(pool, 2, reject_same_div=True, reject_same_time=True)
        p3 = pick_corr_parlay(pool, 3, reject_same_div=True, reject_same_time=True)
        actions = pick_two_or_three_or_single_custom(live, pool=pool, p2_ticket=p2, p3_ticket=p3)
        if not actions:
            continue
        snaps.append({"date": day, "bets": [action_to_bet(a, day) for a in actions]})
    return snaps


def build_strategy_snaps(ml: dict[str, list[dict]], strategy_key: str) -> list[dict]:
    if strategy_key.startswith("corr_nl_prob_"):
        floor = float(strategy_key.split("_")[-1]) / 100.0
        return build_corr_nl_snaps(ml, floor)
    return build_snapshots(ml, strategy_key)


def all_experiment_keys() -> list[str]:
    keys = []
    for rule in STRATEGY_RULES:
        for stake in STAKE_TIERS:
            keys.append(f"{rule}|{stake}")
    for floor in LEG_PROB_FLOORS:
        for stake in STAKE_TIERS:
            keys.append(f"corr_nl_prob_{int(floor*100)}|{stake}")
    return keys


def risk_adjusted_score(row: dict) -> float:
    """Primary metric: compound wallet growth at tiered stake %, with drawdown/streak penalty."""
    retention = row["min_bankroll"] / LIVE_BANKROLL if LIVE_BANKROLL else 0
    compound_return = row.get("compound_return_pct", 0.0)
    return (
        compound_return * 50.0
        + retention * 30.0
        - row["max_losing_streak"] * 12.0
        + row["hit_rate"] * 15.0
    )


def evaluate_combo(ml: dict, rule: str, stake_key: str) -> dict:
    snaps = build_strategy_snaps(ml, rule)
    stakes = STAKE_TIERS[stake_key]
    c = compound(snaps, LIVE_BANKROLL, stakes)
    wins, losses = map(int, c["record"].split("-"))
    row = {
        "key": f"{rule}|{stake_key}",
        "strategy": rule,
        "stakes": stake_key,
        "stake_pct": stakes,
        "record": c["record"],
        "hit_rate": round(wins / c["days"], 4) if c["days"] else 0.0,
        "bet_days": c["days"],
        "flat_roi": round(c["flat_roi"], 4),
        "flat_profit": round(c["flat_profit"], 2),
        "compound_profit": round(c["end"] - LIVE_BANKROLL, 2),
        "compound_return_pct": round((c["end"] / LIVE_BANKROLL - 1) * 100, 2) if LIVE_BANKROLL else 0.0,
        "end_from_23": round(c["end"], 2),
        "min_bankroll": round(c["min_bankroll"], 2),
        "min_bankroll_pct": round(c["min_bankroll"] / LIVE_BANKROLL, 4) if LIVE_BANKROLL else 0.0,
        "max_losing_streak": max_losing_streak(snaps),
        "score": 0.0,
        "metric": "tiered_compound",
    }
    row["score"] = round(risk_adjusted_score(row), 4)
    return row


def write_morning_report(all_results: list[dict]) -> None:
    if not all_results:
        return

    # Backfill compound fields for older log rows
    for row in all_results:
        if "compound_return_pct" not in row and row.get("end_from_23"):
            row["compound_return_pct"] = round((row["end_from_23"] / LIVE_BANKROLL - 1) * 100, 2)
            row["compound_profit"] = round(row["end_from_23"] - LIVE_BANKROLL, 2)
        if "min_bankroll_pct" not in row and row.get("min_bankroll"):
            row["min_bankroll_pct"] = round(row["min_bankroll"] / LIVE_BANKROLL, 4)

    by_compound = sorted(all_results, key=lambda r: (r.get("end_from_23", 0), r.get("compound_return_pct", 0)), reverse=True)
    by_compound_safe = sorted(
        all_results,
        key=lambda r: (r.get("compound_return_pct", 0), r.get("min_bankroll", 0), -r.get("max_losing_streak", 99)),
        reverse=True,
    )
    by_balanced = sorted(all_results, key=lambda r: r["score"], reverse=True)
    by_safety = sorted(all_results, key=lambda r: (r["max_losing_streak"], -r["min_bankroll"], -r.get("end_from_23", 0)))

    shipped = next((r for r in all_results if r["strategy"] == "no_low_parlay_223s" and r["stakes"] == "shipped_35_45_10"), None)

    REPORT_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "live_bankroll": LIVE_BANKROLL,
                "ranking_method": "tiered_compound_stakes",
                "note": "All end_from_23 values assume $23.28 start, reinvesting 1/2/3-leg stake % each bet day.",
                "total_configs_tested": len(all_results),
                "executive_summary": {
                    "best_compound": by_compound[0],
                    "best_compound_balanced": by_balanced[0],
                    "best_compound_safe": next(
                        (r for r in by_compound_safe if r.get("min_bankroll_pct", 0) >= 0.75 and r.get("max_losing_streak", 99) <= 4),
                        by_compound_safe[0],
                    ),
                    "safest_profitable": next((r for r in by_safety if r.get("compound_return_pct", 0) > 0), by_safety[0]),
                    "current_shipped": shipped,
                },
                "top_10_by_compound": by_compound[:10],
                "top_10_balanced": by_balanced[:10],
                "top_10_safest_compound": [r for r in by_safety if r.get("compound_return_pct", 0) > 50][:10],
                "recommendation": _recommendation(by_balanced[0], shipped, by_compound[0]),
            },
            indent=2,
        )
    )


def _recommendation(best_balanced: dict, shipped: dict | None, best_compound: dict) -> dict:
    msg = []
    if shipped:
        msg.append(
            f"Current shipped: ${shipped['end_from_23']:,.0f} from ${LIVE_BANKROLL} "
            f"({shipped.get('compound_return_pct', 0):+.0f}% compound), "
            f"min wallet ${shipped['min_bankroll']:.2f}, max L-streak {shipped['max_losing_streak']}"
        )
    if best_compound["key"] != (shipped or {}).get("key"):
        msg.append(
            f"Max compound: {best_compound['strategy']} @ {best_compound['stakes']} "
            f"→ ${best_compound['end_from_23']:,.0f} ({best_compound.get('compound_return_pct', 0):+.0f}%), "
            f"min ${best_compound['min_bankroll']:.2f}, L-streak {best_compound['max_losing_streak']}"
        )
    if best_balanced["key"] != best_compound["key"]:
        msg.append(
            f"Best risk-adjusted compound: {best_balanced['strategy']} @ {best_balanced['stakes']} "
            f"→ ${best_balanced['end_from_23']:,.0f} ({best_balanced.get('compound_return_pct', 0):+.0f}%)"
        )
    return {
        "messages": msg,
        "suggested_live": {
            "strategy": best_balanced["strategy"],
            "stakes": best_balanced["stakes"],
            "stake_pct": best_balanced["stake_pct"],
            "reason": "best compound return vs drawdown on $23 tiered stakes",
        },
    }


def run_batch(ml: dict, keys: list[str], state: dict) -> list[dict]:
    results = []
    for key in keys:
        if key in state.get("completed_keys", []):
            continue
        rule, stake = key.rsplit("|", 1)
        try:
            row = evaluate_combo(ml, rule, stake)
            row["key"] = key
            results.append(row)
            append_log(row)
            state.setdefault("completed_keys", []).append(key)
            state["total_tested"] = state.get("total_tested", 0) + 1
            print(
                f"  {key}: compound={row['compound_return_pct']:+.0f}% ${row['end_from_23']:,.0f} "
                f"{row['record']} min=${row['min_bankroll']:.2f} L={row['max_losing_streak']}",
                flush=True,
            )
        except Exception as error:
            append_log({"key": key, "error": str(error)})
            print(f"  FAIL {key}: {error}", flush=True)
    save_state(state)
    return results


def load_all_logged() -> list[dict]:
    rows = []
    if LOG_PATH.exists():
        for line in LOG_PATH.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if "flat_roi" in row:
                    rows.append(row)
            except json.JSONDecodeError:
                pass
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Run entire grid in one pass")
    parser.add_argument("--batch-size", type=int, default=12)
    parser.add_argument("--rerank-only", action="store_true", help="Regenerate report from logs")
    parser.add_argument("--refresh-cache", action="store_true")
    args = parser.parse_args()

    state = load_state()
    all_keys = all_experiment_keys()
    print(f"exhaustive: {len(all_keys)} total configs, {state.get('total_tested', 0)} done", flush=True)

    if args.rerank_only:
        all_results = load_all_logged()
        by_key: dict[str, dict] = {}
        for row in all_results:
            by_key[row["key"]] = row
            if "score" not in row or row.get("metric") != "tiered_compound":
                row["score"] = round(risk_adjusted_score(row), 4)
        write_morning_report(list(by_key.values()))
        print(f"Re-ranked {len(by_key)} configs by compound → {REPORT_PATH}", flush=True)
        return

    if args.refresh_cache:
        load_ml(refresh=True)

    print("Loading walk-forward data (cached after first run)...", flush=True)
    ml = load_ml()

    if args.full:
        pending = [k for k in all_keys if k not in state.get("completed_keys", [])]
        batch_size = max(1, len(pending))
    else:
        pending = [k for k in all_keys if k not in state.get("completed_keys", [])]
        batch_size = args.batch_size

    if not pending:
        print("All configs tested — refreshing morning report.", flush=True)
    else:
        batch = pending[:batch_size]
        print(f"Testing batch of {len(batch)} ({len(pending)} remaining)...", flush=True)
        run_batch(ml, batch, state)

    all_results = load_all_logged()
  # dedupe by key, keep latest
    by_key: dict[str, dict] = {}
    for row in all_results:
        by_key[row["key"]] = row
    write_morning_report(list(by_key.values()))
    print(f"Morning report: {REPORT_PATH} ({len(by_key)} configs)", flush=True)


if __name__ == "__main__":
    main()
