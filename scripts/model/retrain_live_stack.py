"""Retrain evaluation: model v2.14 + betting-strategy holdout on last 21 days."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from backtest_parlays import season_start_for
from daily_auto_model import MODEL_VERSION, walk_forward_history
from exhaustive_strategy_search import (
    action_to_bet,
    day_actions_for_rule,
    flat_stats_for_snapshots,
    load_moneyline_by_day,
)
from strategy_next_tests import build_snapshots, compound, enrich_moneyline, summarize
from mlb_api import load_or_fetch_games, load_team_abbreviations

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = REPO_ROOT / "public" / "model-retrain-report.json"
PLAN_PATH = REPO_ROOT / "public" / "betting-plan.json"
GUARD_PATH = REPO_ROOT / "public" / "strategy-guard.json"

HOLDOUT_DAYS = 21
STRATEGIES = [
    "edge_value_ticket",
    "best_ticket",
    "high_elite_edge1",
    "high_elite_76_parlay",
]
STAKE_TIERED = {1: 0.12, 2: 0.18, 3: 0.18, 4: 0.18}


def ticket_stats(snaps: list[dict], *, start: str | None = None, end: str | None = None) -> dict:
    filtered = snaps
    if start:
        filtered = [s for s in filtered if s["date"] >= start]
    if end:
        filtered = [s for s in filtered if s["date"] <= end]
    wins = sum(1 for s in filtered if s.get("bets") and s["bets"][0].get("won"))
    losses = sum(1 for s in filtered if s.get("bets") and s["bets"][0].get("won") is False)
    days = len(filtered)
    total = wins + losses
    return {
        "bet_days": days,
        "record": f"{wins}-{losses}",
        "hit_rate": round(wins / total, 4) if total else None,
        "flat": flat_stats_for_snapshots(filtered),
    }


def main() -> None:
    end = date.today() - timedelta(days=1)
    start = date(2026, 3, 20)
    holdout_start = (end - timedelta(days=HOLDOUT_DAYS - 1)).isoformat()
    prior = (season_start_for(2025), date(2025, 8, 17))

    print(f"model={MODEL_VERSION} holdout>={holdout_start} through {end.isoformat()}")
    ml, _ = load_moneyline_by_day(start, end, prior[0], prior[1])
    ml = {day: c for day, c in ml.items() if date.fromisoformat(day) <= end}

    rows = walk_forward_history(
        load_or_fetch_games(start, end),
        load_team_abbreviations(),
        prior_games=load_or_fetch_games(*prior),
    )
    ml = enrich_moneyline(ml, rows)

    recent_rows = [r for r in rows if r["date"] >= holdout_start]
    recent_acc = sum(r["correct"] for r in recent_rows) / len(recent_rows) if recent_rows else 0.0

    results: list[dict] = []
    for rule in STRATEGIES:
        snaps = build_snapshots(ml, rule)
        holdout = ticket_stats(snaps, start=holdout_start, end=end.isoformat())
        season = summarize(rule, snaps)
        end10 = compound(snaps, 10.0, STAKE_TIERED)["end"]
        results.append(
            {
                "strategy": rule,
                "holdout": holdout,
                "season": {
                    "record": season["record"],
                    "bet_days": season["bet_days"],
                    "flat_roi": season["flat_roi"],
                },
                "compound_from_10": round(end10, 2),
            }
        )
        print(
            f"{rule:22s} holdout {holdout['record']:>5s} ({holdout['hit_rate'] or 0:.1%}) "
            f"days={holdout['bet_days']:>2d}  $10->{end10:>6.2f}"
        )

    # Pick holdout winner: highest hit rate with min 3 bet days; tie-break ROI from $10
    eligible = [r for r in results if (r["holdout"]["bet_days"] or 0) >= 3]
    if not eligible:
        eligible = results
    winner = max(
        eligible,
        key=lambda r: (
            r["holdout"]["hit_rate"] or 0.0,
            r["holdout"]["flat"].get("roi", 0.0),
            -r["holdout"]["bet_days"],
        ),
    )
    live_strategy = winner["strategy"]
    print(f"\nLIVE_STRATEGY => {live_strategy}")

    report = {
        "generated_at": date.today().isoformat(),
        "model_version": MODEL_VERSION,
        "holdout_start": holdout_start,
        "holdout_end": end.isoformat(),
        "holdout_game_accuracy": round(recent_acc, 4),
        "strategies": results,
        "live_strategy": live_strategy,
        "changes": [
            "v2.14: recency-weighted training (2.25x last 21d)",
            "v3 pipeline: real market edge (pick - book), no market-agree boost",
            "coin-flip market blend 30% -> 42%",
            "betting: edge-first scoring + edge_value_ticket skip gate",
        ],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2))

    if PLAN_PATH.exists():
        plan = json.loads(PLAN_PATH.read_text())
        plan["strategy"] = live_strategy
        plan["generated_at"] = date.today().isoformat()
        plan["retuned_from"] = (
            f"Jun 24 retrain — model {MODEL_VERSION}, holdout {holdout_start}..{end.isoformat()} "
            f"winner {live_strategy} ({winner['holdout']['record']})"
        )
        PLAN_PATH.write_text(json.dumps(plan, indent=2))

    if GUARD_PATH.exists():
        guard = json.loads(GUARD_PATH.read_text())
        guard["live_strategy"] = live_strategy
        guard["generated_at"] = date.today().isoformat()
        GUARD_PATH.write_text(json.dumps(guard, indent=2))

    print(f"wrote {REPORT_PATH.name}")


if __name__ == "__main__":
    main()
