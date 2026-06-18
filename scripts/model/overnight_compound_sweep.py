"""Phase-2 overnight: fine stake grid on top strategies — compound at tiered %."""

from __future__ import annotations

import itertools
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = ROOT / "data" / "overnight-compound-sweep.jsonl"
REPORT_PATH = ROOT / "public" / "overnight-compound-sweep.json"
LIVE_BANKROLL = 23.28

from overnight_exhaustive import (
    build_strategy_snaps,
    load_ml,
    max_losing_streak,
    risk_adjusted_score,
)
from strategy_research import compound

TOP_STRATEGIES = [
    "no_low_parlay_223s",
    "no_low_min_edge7",
    "no_low_min_edge8",
    "corr_nl_reject_both",
    "corr_nl_prob_65",
    "corr_nl_prob_62",
    "best_ticket",
    "no_low_skip_forced",
]

STAKE_GRID = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45]


def stake_combos() -> list[tuple[str, dict[int, float]]]:
    combos: list[tuple[str, dict[int, float]]] = []
    for s1, s2, s3 in itertools.product(STAKE_GRID, repeat=3):
        if s2 > 0.50 or s1 > 0.45:
            continue
        name = f"s{s1:.2f}_p{s2:.2f}_t{s3:.2f}"
        combos.append((name, {1: s1, 2: s2, 3: s3}))
    return combos


def main() -> None:
    ml = load_ml()
    snaps_cache: dict[str, list] = {}
    results: list[dict] = []

    for strategy in TOP_STRATEGIES:
        snaps_cache[strategy] = build_strategy_snaps(ml, strategy)

    for strategy in TOP_STRATEGIES:
        snaps = snaps_cache[strategy]
        for stake_name, stakes in stake_combos():
            c = compound(snaps, LIVE_BANKROLL, stakes)
            wins, losses = map(int, c["record"].split("-"))
            row = {
                "key": f"{strategy}|{stake_name}",
                "strategy": strategy,
                "stakes": stake_name,
                "stake_pct": stakes,
                "record": c["record"],
                "hit_rate": round(wins / c["days"], 4) if c["days"] else 0.0,
                "compound_return_pct": round((c["end"] / LIVE_BANKROLL - 1) * 100, 2),
                "end_from_23": round(c["end"], 2),
                "min_bankroll": round(c["min_bankroll"], 2),
                "min_bankroll_pct": round(c["min_bankroll"] / LIVE_BANKROLL, 4),
                "max_losing_streak": max_losing_streak(snaps),
                "metric": "tiered_compound_fine_grid",
            }
            row["score"] = round(risk_adjusted_score(row), 4)
            results.append(row)
            with LOG_PATH.open("a") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")

    by_compound = sorted(results, key=lambda r: r["end_from_23"], reverse=True)
    by_balanced = sorted(results, key=lambda r: r["score"], reverse=True)
    safe = [r for r in results if r["min_bankroll_pct"] >= 0.80 and r["max_losing_streak"] <= 4]
    safe.sort(key=lambda r: r["end_from_23"], reverse=True)

    shipped = next((r for r in results if r["strategy"] == "corr_nl_reject_both" and r["stakes"] == "s0.35_p0.40_t0.30"), None)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "live_bankroll": LIVE_BANKROLL,
        "strategies": TOP_STRATEGIES,
        "stake_combos_tested": len(stake_combos()),
        "total_configs": len(results),
        "best_compound": by_compound[0],
        "best_balanced": by_balanced[0],
        "best_safe_compound": safe[0] if safe else None,
        "current_shipped_stakes": shipped,
        "top_15_compound": by_compound[:15],
        "top_15_balanced": by_balanced[:15],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"compound sweep: {len(results)} configs → {REPORT_PATH}", flush=True)
    print(f"  best compound: {by_compound[0]['key']} → ${by_compound[0]['end_from_23']:,.0f}", flush=True)
    print(f"  best balanced: {by_balanced[0]['key']} → ${by_balanced[0]['end_from_23']:,.0f}", flush=True)


if __name__ == "__main__":
    main()
