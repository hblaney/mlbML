"""Rigorous overnight sweep — every strategy rule × tiered stake combo, compound-ranked."""

from __future__ import annotations

import argparse
import json
import pickle
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAP_CACHE = ROOT / "data" / "overnight-rigorous-snaps.pkl"
STATE_PATH = ROOT / "data" / "overnight-rigorous-state.json"
LOG_PATH = ROOT / "data" / "overnight-rigorous.jsonl"
REPORT_PATH = ROOT / "public" / "overnight-rigorous-report.json"
LIVE_BANKROLL = 23.28

from exhaustive_strategy_search import build_daily_snapshots, strategy_grid
from overnight_compound_sweep import stake_combos
from overnight_exhaustive import (
    LEG_PROB_FLOORS,
    STAKE_TIERS,
    STRATEGY_RULES,
    build_corr_nl_snaps,
    build_strategy_snaps,
    load_ml,
    max_losing_streak,
    risk_adjusted_score,
)
from strategy_research import build_snapshots as research_build_snapshots
from strategy_research import compound

RESEARCH_RULES = [
    "two_or_three_or_single",
    "no_low_parlay_223s",
    "no_low_forced_only_223s",
    "no_low_never_skip_223s",
    "medium_plus_223s",
    "no_forced_223s",
    "no_low_no_forced_223s",
    "min_edge8_223s",
    "no_low_min_edge8_223s",
    "filtered_223s_only",
    "high_elite_parlay_or_single",
    "best_combo_score_day",
]


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"completed": [], "phase": "discover"}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def append_log(row: dict) -> None:
    row["logged_at"] = datetime.now().isoformat(timespec="seconds")
    with LOG_PATH.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def discover_all_strategies(ml: dict) -> dict[str, list[dict]]:
    """Build snapshots once per strategy; cache to disk."""
    if SNAP_CACHE.exists():
        with SNAP_CACHE.open("rb") as handle:
            cached = pickle.load(handle)
        if cached.get("ml_end"):
            return cached["snaps"]

    snaps: dict[str, list[dict]] = {}

    for strategy_id, rule, threshold in strategy_grid():
        key = f"ex:{strategy_id}"
        try:
            built = build_daily_snapshots(ml, rule, threshold)
            if len(built) >= 15:
                snaps[key] = built
        except Exception:
            pass

    for rule in STRATEGY_RULES:
        key = f"nt:{rule}"
        try:
            built = build_strategy_snaps(ml, rule)
            if len(built) >= 15:
                snaps[key] = built
        except Exception:
            pass

    for floor in LEG_PROB_FLOORS:
        key = f"nt:corr_nl_prob_{int(floor * 100)}"
        try:
            built = build_corr_nl_snaps(ml, floor)
            if len(built) >= 15:
                snaps[key] = built
        except Exception:
            pass

    for rule in RESEARCH_RULES:
        key = f"sr:{rule}"
        try:
            built = research_build_snapshots(ml, rule)
            if len(built) >= 15:
                snaps[key] = built
        except Exception:
            pass

    SNAP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with SNAP_CACHE.open("wb") as handle:
        pickle.dump({"snaps": snaps, "ml_end": "cached", "built_at": datetime.now().isoformat()}, handle)
    print(f"discovered {len(snaps)} strategies with snapshots", flush=True)
    return snaps


def all_eval_keys(snaps: dict[str, list[dict]]) -> list[tuple[str, str, dict[int, float]]]:
    keys: list[tuple[str, str, dict[int, float]]] = []
    for strat_key in snaps:
        for tier_name, stakes in STAKE_TIERS.items():
            keys.append((strat_key, tier_name, stakes))
        for stake_name, stakes in stake_combos():
            keys.append((strat_key, stake_name, stakes))
    return keys


def evaluate(strat_key: str, stake_name: str, stakes: dict[int, float], snaps: list[dict]) -> dict:
    c = compound(snaps, LIVE_BANKROLL, stakes)
    wins, losses = map(int, c["record"].split("-"))
    row = {
        "key": f"{strat_key}|{stake_name}",
        "strategy": strat_key,
        "stakes": stake_name,
        "stake_pct": stakes,
        "record": c["record"],
        "hit_rate": round(wins / c["days"], 4) if c["days"] else 0.0,
        "bet_days": c["days"],
        "compound_return_pct": round((c["end"] / LIVE_BANKROLL - 1) * 100, 2),
        "end_from_23": round(c["end"], 2),
        "min_bankroll": round(c["min_bankroll"], 2),
        "min_bankroll_pct": round(c["min_bankroll"] / LIVE_BANKROLL, 4),
        "max_losing_streak": max_losing_streak(snaps),
        "flat_roi": round(c.get("flat_roi", 0), 4),
        "metric": "rigorous_tiered_compound",
    }
    row["score"] = round(risk_adjusted_score(row), 4)
    return row


def write_report(results: list[dict]) -> None:
    if not results:
        return
    by_compound = sorted(results, key=lambda r: r["end_from_23"], reverse=True)
    by_balanced = sorted(results, key=lambda r: r["score"], reverse=True)
    acceptable = [r for r in results if r["min_bankroll"] >= 12.5]
    acceptable.sort(key=lambda r: r["end_from_23"], reverse=True)

    REPORT_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "live_bankroll": LIVE_BANKROLL,
                "min_bankroll_floor_accepted": 12.5,
                "total_configs": len(results),
                "strategies_tested": len({r["strategy"] for r in results}),
                "best_compound_overall": by_compound[0],
                "best_compound_min_12_50": acceptable[0] if acceptable else by_compound[0],
                "best_balanced": by_balanced[0],
                "top_25_compound": by_compound[:25],
                "top_25_balanced": by_balanced[:25],
                "top_25_min_12_50": acceptable[:25],
            },
            indent=2,
        )
    )


def load_logged() -> dict[str, dict]:
    by_key: dict[str, dict] = {}
    if LOG_PATH.exists():
        for line in LOG_PATH.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if "end_from_23" in row:
                    by_key[row["key"]] = row
            except json.JSONDecodeError:
                pass
    return by_key


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    state = load_state()
    print("rigorous sweep: loading data...", flush=True)
    ml = load_ml()
    snaps = discover_all_strategies(ml)
    eval_keys = all_eval_keys(snaps)
    print(f"rigorous: {len(snaps)} strategies × {len(eval_keys) // len(snaps)} stake profiles = {len(eval_keys)} configs", flush=True)

    pending = [(sk, sn, st) for sk, sn, st in eval_keys if f"{sk}|{sn}" not in state.get("completed", [])]
    if args.full:
        batch = pending
    else:
        batch = pending[: args.batch_size]

    if not batch:
        print("rigorous: all configs done, refreshing report", flush=True)
    else:
        print(f"rigorous: testing {len(batch)} ({len(pending)} remaining)...", flush=True)
        for strat_key, stake_name, stakes in batch:
            try:
                row = evaluate(strat_key, stake_name, stakes, snaps[strat_key])
                append_log(row)
                state.setdefault("completed", []).append(row["key"])
                if len(state["completed"]) % 50 == 0:
                    save_state(state)
            except Exception as error:
                append_log({"key": f"{strat_key}|{stake_name}", "error": str(error)})

    save_state(state)
    write_report(list(load_logged().values()))
    print(f"rigorous report → {REPORT_PATH} ({len(load_logged())} configs logged)", flush=True)


if __name__ == "__main__":
    main()
