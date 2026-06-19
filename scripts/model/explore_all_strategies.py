"""Exhaustive strategy + stake explorer — run continuously to beat the live plan.

Tests ticket rules (any leg count, med60 thresholds, legacy rules) × stake presets
(compound tiered + flat %). Output: public/strategy-explorer.json
"""

from __future__ import annotations

import itertools
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Callable

from backtest_parlays import STAKE, season_start_for, settle_parlay
from backtest_strategy_optimizer import leg_score_for_parlay, pick_forced_top_legs
from daily_auto_model import walk_forward_history
from exhaustive_strategy_search import (
    DayAction,
    action_to_bet,
    day_actions_for_rule,
    load_moneyline_by_day,
    pick_always_n,
    pick_filtered,
)
from mlb_api import load_or_fetch_games, load_team_abbreviations
from strategy_next_tests import (
    CONF_OK,
    build_snapshots,
    day_actions_for_test,
    enrich_moneyline,
    no_low_pool,
    top_n_by_prob,
)
from strategy_research import DAILY_CAP, compound

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "strategy-explorer.json"
LIVE_STRATEGY = "trg59_top_prob_2"
START_BANKROLL = 25.0
MED60_THRESHOLDS = (0.58, 0.59, 0.60, 0.61, 0.62, 0.65)
PICK_METHODS = ("top_prob", "always", "forced")
LEG_SETS = (
    (2,),
    (3,),
    (4,),
    (2, 3),
    (2, 4),
    (2, 3, 4),
    (3, 4),
)

BASE_RULES_TEST = (
    "med60_force2_223s",
    "no_low_parlay_223s",
    "best_ticket",
    "no_low_skip_forced",
    "corr_nl_reject_both",
)

BASE_RULES_EXHAUSTIVE = (
    "always_2",
    "always_3",
    "always_4",
    "two_or_three_or_single",
    "two_or_three_best",
    "filtered_two_else_three",
    "positive_ev_top2",
)


def pool_at_threshold(candidates: list[dict], threshold: float) -> list[dict]:
    return [c for c in no_low_pool(candidates) if float(c.get("model_probability", 0)) >= threshold]


def ticket_for_method(pool: list[dict], leg_count: int, method: str) -> dict | None:
    if len(pool) < leg_count:
        return None
    if method == "always":
        return pick_always_n(pool, leg_count)
    if method == "filtered":
        return pick_filtered(pool, leg_count)
    if method == "forced":
        return pick_forced_top_legs(pool, leg_count)
    if method == "top_prob":
        legs = top_n_by_prob(pool, leg_count)
        if len(legs) < leg_count:
            return None
        ticket = settle_parlay(legs)
        ticket["legs"] = legs
        ticket["score"] = leg_score_for_parlay(legs)
        ticket["strategy"] = f"top{leg_count}_prob"
        return ticket
    raise ValueError(method)


def make_med60_rule(
    threshold: float,
    leg_counts: tuple[int, ...],
    method: str,
    *,
    allow_single: bool = False,
    fallback: str = "no_low_parlay_223s",
) -> tuple[str, Callable]:
    leg_counts = tuple(sorted(set(leg_counts)))
    label = f"med{int(threshold * 100)}_{method}_{'-'.join(map(str, leg_counts))}"
    if allow_single:
        label += "_+single"

    def rule(candidates: list[dict]) -> list[DayAction]:
        pool = pool_at_threshold(candidates, threshold)
        if len(pool) < min(leg_counts):
            return day_actions_for_rule(candidates, fallback)

        opts: list[tuple[float, dict, str]] = []
        for n in leg_counts:
            if len(pool) < n:
                continue
            ticket = ticket_for_method(pool, n, method)
            if ticket and ticket.get("legs"):
                opts.append((float(ticket["score"]), ticket, f"p{n}"))

        if allow_single:
            from backtest_daily_recommendations import pick_best_moneyline

            single, _ = pick_best_moneyline(candidates)
            if single:
                opts.append((single["ev"] * single["model_probability"], single, "single"))

        if not opts:
            return day_actions_for_rule(candidates, fallback)

        score, ticket, tag = max(opts, key=lambda row: row[0])
        if tag == "single":
            return [DayAction(legs=None, single=ticket, label="single")]
        return [DayAction(legs=ticket["legs"], single=None, label=tag)]

    return label, rule


def iter_strategy_rules() -> list[tuple[str, Callable]]:
    rules: list[tuple[str, Callable]] = []

    for base in BASE_RULES_TEST:
        rules.append((base, lambda c, b=base: day_actions_for_test(c, b)))

    for base in BASE_RULES_EXHAUSTIVE:
        rules.append((base, lambda c, b=base: day_actions_for_rule(c, b)))

    for threshold in MED60_THRESHOLDS:
        for method in PICK_METHODS:
            for leg_counts in LEG_SETS:
                rules.append(make_med60_rule(threshold, leg_counts, method))
            # force exact leg count (no score competition)
            for n in (2, 3, 4):
                rules.append(
                    make_med60_rule(threshold, (n,), method, fallback="no_low_parlay_223s")
                )

    # dedupe labels
    seen: set[str] = set()
    unique: list[tuple[str, Callable]] = []
    for label, fn in rules:
        if label in seen:
            continue
        seen.add(label)
        unique.append((label, fn))
    return unique


def stake_presets() -> dict[str, dict[int, float]]:
    presets: dict[str, dict[int, float]] = {
        "shipped_35_45_10": {1: 0.35, 2: 0.45, 3: 0.10, 4: 0.35},
        "aggressive_45_50_35": {1: 0.45, 2: 0.50, 3: 0.35, 4: 0.45},
        "moderate_25_30_20": {1: 0.25, 2: 0.30, 3: 0.20, 4: 0.25},
        "conservative_20_25_15": {1: 0.20, 2: 0.25, 3: 0.15, 4: 0.20},
        "equal_25_all": {1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25},
        "parlay_heavy_15_50_25": {1: 0.15, 2: 0.50, 3: 0.25, 4: 0.40},
    }
    for pct in (0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50):
        presets[f"flat_{int(pct * 100)}"] = {1: pct, 2: pct, 3: pct, 4: pct}
    return presets


def ticket_mix(snaps: list[dict]) -> dict[str, int]:
    mix: Counter[int] = Counter()
    for snap in snaps:
        bet = snap["bets"][0]
        mix[len(bet.get("legs") or [bet])] += 1
    return {str(k): mix[k] for k in sorted(mix)}


def balanced_score(hit_rate: float, end: float, start: float, min_bankroll: float) -> float:
    """Favor hit rate and compound return, penalize brutal drawdowns."""
    ret = end / start if start else 1.0
    floor = min_bankroll / start if start else 1.0
    return hit_rate * math.log1p(ret) * (0.5 + 0.5 * floor)


def main() -> None:
    today = date.today()
    season_start = season_start_for(today.year)
    prior = (season_start_for(today.year - 1), date(today.year - 1, 8, 17))
    ml, meta = load_moneyline_by_day(season_start, today, prior[0], prior[1])
    rows = walk_forward_history(
        load_or_fetch_games(season_start, today),
        load_team_abbreviations(),
        prior_games=load_or_fetch_games(prior[0], prior[1]),
    )
    ml = enrich_moneyline(ml, rows)

    rule_snaps: dict[str, list[dict]] = {}
    rule_stats: dict[str, dict] = {}
    for label, fn in iter_strategy_rules():
        snaps = []
        for day in sorted(ml):
            actions = fn(ml[day])
            if not actions:
                continue
            snaps.append({"date": day, "bets": [action_to_bet(a, day) for a in actions]})
        if not snaps:
            continue
        rule_snaps[label] = snaps
        wins = sum(1 for s in snaps if s["bets"][0].get("won"))
        days = len(snaps)
        rule_stats[label] = {
            "days": days,
            "wins": wins,
            "losses": days - wins,
            "record": f"{wins}-{days - wins}",
            "hit_rate": round(wins / days, 4) if days else 0.0,
            "mix": ticket_mix(snaps),
        }

    results: list[dict] = []
    for label, snaps in rule_snaps.items():
        base = rule_stats[label]
        for stake_name, stake_map in stake_presets().items():
            c = compound(snaps, START_BANKROLL, stake_map)
            hit = base["hit_rate"]
            results.append(
                {
                    "strategy": label,
                    "stakes": stake_name,
                    "record": base["record"],
                    "hit_rate": hit,
                    "mix": base["mix"],
                    "start": START_BANKROLL,
                    "end": c["end"],
                    "profit": c["profit"],
                    "return_pct": round(c["profit"] / START_BANKROLL, 4),
                    "min_bankroll": c["min_bankroll"],
                    "max_losing_streak": c["max_losing_streak"],
                    "flat_roi": c["flat_roi"],
                    "balanced_score": round(balanced_score(hit, c["end"], START_BANKROLL, c["min_bankroll"]), 4),
                    "is_live": label == LIVE_STRATEGY and stake_name == "shipped_35_45_10",
                }
            )

    by_profit = sorted(results, key=lambda r: r["profit"], reverse=True)
    by_hit = sorted(
        [r for r in results if rule_stats[r["strategy"]]["days"] >= 70],
        key=lambda r: (r["hit_rate"], r["profit"]),
        reverse=True,
    )
    by_balanced = sorted(results, key=lambda r: r["balanced_score"], reverse=True)

    live_row = next((r for r in results if r["is_live"]), None)
    live_rank_profit = next(i + 1 for i, r in enumerate(by_profit) if r["is_live"]) if live_row else None

    payload = {
        "generated_at": today.isoformat(),
        "season": f"{season_start} -> {today}",
        "bet_days": meta.get("game_days_with_odds"),
        "live_strategy": LIVE_STRATEGY,
        "live_stakes": "shipped_35_45_10",
        "start_bankroll": START_BANKROLL,
        "rules_tested": len(rule_snaps),
        "combos_tested": len(results),
        "live_current": live_row,
        "live_rank_by_compound_profit": live_rank_profit,
        "top_by_compound_profit": by_profit[:25],
        "top_by_hit_rate": by_hit[:25],
        "top_by_balanced_score": by_balanced[:25],
        "recommendation": _recommendation(by_profit, by_hit, by_balanced, live_row),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))

    print(f"Strategy explorer: {len(rule_snaps)} rules × {len(stake_presets())} stakes = {len(results)} combos")
    print(f"Live ({LIVE_STRATEGY} @ shipped): rank #{live_rank_profit} by compound profit")
    if live_row:
        print(f"  {live_row['record']} hit={live_row['hit_rate']:.1%} end=${live_row['end']:,.0f}")
    top = by_profit[0]
    print(f"\nBest compound: {top['strategy']} @ {top['stakes']}")
    print(f"  {top['record']} hit={top['hit_rate']:.1%} end=${top['end']:,.0f} min=${top['min_bankroll']:.2f}")
    print(f"\nWrote {OUTPUT_PATH}")


def _recommendation(by_profit, by_hit, by_balanced, live_row) -> dict:
    best_profit = by_profit[0]
    best_hit = by_hit[0]
    best_bal = by_balanced[0]
    ship = "shipped_35_45_10"
    # Prefer challengers that beat live on BOTH hit rate and profit at shipped stakes
    challengers = []
    if live_row:
        for r in by_profit:
            if r["stakes"] != ship:
                continue
            if r["strategy"] == live_row["strategy"]:
                continue
            if r["profit"] > live_row["profit"] and r["hit_rate"] >= live_row["hit_rate"]:
                challengers.append(r)
            elif r["profit"] > live_row["profit"] * 1.5:
                challengers.append(r)
        challengers = challengers[:5]

    return {
        "best_compound_profit": {
            "strategy": best_profit["strategy"],
            "stakes": best_profit["stakes"],
            "record": best_profit["record"],
            "end": best_profit["end"],
        },
        "best_hit_rate_min_70d": {
            "strategy": best_hit["strategy"],
            "stakes": best_hit["stakes"],
            "record": best_hit["record"],
            "hit_rate": best_hit["hit_rate"],
        },
        "best_balanced": {
            "strategy": best_bal["strategy"],
            "stakes": best_bal["stakes"],
            "record": best_bal["record"],
            "score": best_bal["balanced_score"],
        },
        "shipped_stake_challengers_vs_live": challengers,
        "note": "Ship only after user review. Compound backtest ≠ guaranteed live returns.",
    }


if __name__ == "__main__":
    main()
