"""Find strategies with strong records, low losing streaks, and flexible leg counts."""

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
    day_actions_for_test,
    enrich_moneyline,
    no_low_pool,
    top_n_by_prob,
)
from strategy_research import compound

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "low-streak-strategy-search.json"
LIVE_STRATEGY = "med60_force2_223s"
START = 25.0
STAKES = {1: 0.35, 2: 0.45, 3: 0.10, 4: 0.35}
FLAT = 5.0

THRESHOLDS = (0.58, 0.59, 0.60, 0.61, 0.62, 0.63, 0.65)
LEG_SETS = ((2,), (3,), (4,), (2, 3), (2, 4), (3, 4), (2, 3, 4))
METHODS = ("top_prob", "always", "forced", "filtered")
FALLBACKS = ("no_low_parlay_223s", "always_2", "best_ticket")
FALLBACK_EXHAUSTIVE = {"always_2", "two_or_three_or_single", "two_or_three_best", "positive_ev_top2"}


def apply_fallback(candidates: list[dict], fallback: str) -> list[DayAction]:
    if fallback in FALLBACK_EXHAUSTIVE:
        return day_actions_for_rule(candidates, fallback)
    return day_actions_for_test(candidates, fallback)


def pool_at(candidates: list[dict], threshold: float) -> list[dict]:
    return [c for c in no_low_pool(candidates) if float(c.get("model_probability", 0)) >= threshold]


def ticket_for_method(pool: list[dict], n: int, method: str) -> dict | None:
    if len(pool) < n:
        return None
    if method == "top_prob":
        legs = top_n_by_prob(pool, n)
        if len(legs) < n:
            return None
        ticket = settle_parlay(legs)
        ticket["legs"] = legs
        ticket["score"] = leg_score_for_parlay(legs)
        return ticket
    if method == "always":
        return pick_always_n(pool, n)
    if method == "forced":
        return pick_forced_top_legs(pool, n)
    if method == "filtered":
        return pick_filtered(pool, n)
    raise ValueError(method)


def make_trigger_rule(
    threshold: float,
    leg_counts: tuple[int, ...],
    method: str,
    fallback: str,
    *,
    min_pool: int | None = None,
    allow_single: bool = False,
) -> tuple[str, Callable]:
    leg_counts = tuple(sorted(set(leg_counts)))
    min_need = min_pool if min_pool is not None else min(leg_counts)
    tag = f"trg{int(threshold*100)}_{method}_{'-'.join(map(str, leg_counts))}_fb{fallback}"
    if allow_single:
        tag += "_+s"

    def rule(candidates: list[dict]) -> list[DayAction]:
        pool = pool_at(candidates, threshold)
        if len(pool) < min_need:
            return apply_fallback(candidates, fallback)

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
            return day_actions_for_rule(candidates, "no_low_parlay_223s")

        _, ticket, label = max(opts, key=lambda row: row[0])
        if label == "single":
            return [DayAction(legs=None, single=ticket, label="single")]
        return [DayAction(legs=ticket["legs"], single=None, label=label)]

    return tag, rule


def iter_rules() -> list[tuple[str, Callable]]:
    rules: list[tuple[str, Callable]] = []

    # Shipped + challengers
    EXHAUSTIVE = {"always_2", "always_3", "two_or_three_or_single", "two_or_three_best", "positive_ev_top2"}

    for base in (
        "med60_force2_223s",
        "no_low_parlay_223s",
        "best_ticket",
        "always_2",
        "always_3",
        "two_or_three_or_single",
        "two_or_three_best",
        "corr_nl_reject_both",
        "no_low_skip_forced",
        "positive_ev_top2",
    ):
        if base in EXHAUSTIVE:
            rules.append((base, lambda c, b=base: day_actions_for_rule(c, b)))
        else:
            rules.append((base, lambda c, b=base: day_actions_for_test(c, b)))

    # med59 force-2 explicit
    def med59_force2(c: list[dict]) -> list[DayAction]:
        legs = top_n_by_prob(pool_at(c, 0.59), 2)
        if len(legs) >= 2:
            return [DayAction(legs=legs, single=None, label="p2")]
        return day_actions_for_rule(c, "no_low_parlay_223s")

    rules.append(("med59_top_prob_2", med59_force2))

    # Trigger grids: when N+ picks at threshold, pick best of leg set
    for threshold in THRESHOLDS:
        for method in METHODS:
            for leg_counts in LEG_SETS:
                for fallback in FALLBACKS:
                    rules.append(make_trigger_rule(threshold, leg_counts, method, fallback))

            # Force exact leg count (no competition)
            for n in (2, 3, 4):
                for fallback in FALLBACKS:
                    rules.append(make_trigger_rule(threshold, (n,), method, fallback, min_pool=n))

            # Require 3+ or 4+ picks at threshold before allowing 3/4 leg
            rules.append(make_trigger_rule(threshold, (2, 3), method, "no_low_parlay_223s", min_pool=3))
            rules.append(make_trigger_rule(threshold, (2, 3, 4), method, "no_low_parlay_223s", min_pool=4))

    # Dedupe
    seen: set[str] = set()
    out: list[tuple[str, Callable]] = []
    for label, fn in rules:
        if label in seen:
            continue
        seen.add(label)
        out.append((label, fn))
    return out


def build_snaps(ml: dict, fn: Callable) -> list[dict]:
    snaps = []
    for day in sorted(ml):
        acts = fn(ml[day])
        if not acts:
            continue
        snaps.append({"date": day, "bets": [action_to_bet(a, day) for a in acts]})
    return snaps


def streak_stats(snaps: list[dict]) -> dict:
    wins = losses = 0
    cur_loss = max_loss = 0
    loss_streaks: list[int] = []
    mix: Counter[int] = Counter()

    for snap in snaps:
        bet = snap["bets"][0]
        won = bool(bet.get("won"))
        mix[len(bet.get("legs") or [bet])] += 1
        if won:
            if cur_loss:
                loss_streaks.append(cur_loss)
            cur_loss = 0
            wins += 1
        else:
            cur_loss += 1
            max_loss = max(max_loss, cur_loss)
            losses += 1
    if cur_loss:
        loss_streaks.append(cur_loss)

    days = wins + losses
    flat = sum(s["bets"][0]["profit"] * FLAT / STAKE for s in snaps)
    c = compound(snaps, START, STAKES)

    return {
        "days": days,
        "wins": wins,
        "losses": losses,
        "record": f"{wins}-{losses}",
        "hit_rate": round(wins / days, 4) if days else 0.0,
        "max_losing_streak": max_loss,
        "avg_loss_streak": round(sum(loss_streaks) / len(loss_streaks), 2) if loss_streaks else 0.0,
        "loss_streaks_3plus": sum(1 for s in loss_streaks if s >= 3),
        "mix": {str(k): mix[k] for k in sorted(mix)},
        "flat_profit_5": round(flat, 2),
        "compound_end": c["end"],
        "compound_profit": c["profit"],
        "min_bankroll": c["min_bankroll"],
    }


def quality_score(row: dict) -> float:
    """Higher = better: hit rate, profit, penalize streaks and drawdown."""
    hit = row["hit_rate"]
    streak_pen = 1.0 / (1.0 + row["max_losing_streak"] * 0.35)
    floor = row["min_bankroll"] / START
    ret = math.log1p(row["compound_end"] / START)
    return hit * streak_pen * (0.4 + 0.6 * floor) * ret


def main() -> None:
    today = date.today()
    ss = season_start_for(today.year)
    prior = (season_start_for(today.year - 1), date(today.year - 1, 8, 17))
    ml, meta = load_moneyline_by_day(ss, today, prior[0], prior[1])
    rows = walk_forward_history(
        load_or_fetch_games(ss, today),
        load_team_abbreviations(),
        prior_games=load_or_fetch_games(prior[0], prior[1]),
    )
    ml = enrich_moneyline(ml, rows)

    results: list[dict] = []
    for label, fn in iter_rules():
        snaps = build_snaps(ml, fn)
        if len(snaps) < 60:
            continue
        stats = streak_stats(snaps)
        row = {"strategy": label, **stats, "is_live": label == LIVE_STRATEGY}
        row["quality_score"] = round(quality_score(row), 4)
        results.append(row)

    by_quality = sorted(results, key=lambda r: r["quality_score"], reverse=True)
    low_streak = sorted(
        [r for r in results if r["max_losing_streak"] <= 4 and r["hit_rate"] >= 0.55],
        key=lambda r: (-r["hit_rate"], -r["compound_profit"]),
    )
    best_hit_low_streak = sorted(
        [r for r in results if r["max_losing_streak"] <= 5],
        key=lambda r: (-r["hit_rate"], -r["flat_profit_5"]),
    )
    with_3leg = sorted(
        [r for r in results if int(r["mix"].get("3", 0)) >= 5 and r["max_losing_streak"] <= 5],
        key=lambda r: (-r["hit_rate"], -r["compound_profit"]),
    )

    live = next((r for r in results if r["is_live"]), None)

    payload = {
        "generated_at": today.isoformat(),
        "season": f"{ss} -> {today}",
        "rules_tested": len(results),
        "live": live,
        "top_by_quality_score": by_quality[:30],
        "best_hit_max_streak_4": [r for r in low_streak if r["max_losing_streak"] <= 4][:20],
        "best_hit_max_streak_5": best_hit_low_streak[:20],
        "best_with_3leg_min5_days": with_3leg[:20],
        "filters": {
            "quality_score": "hit_rate × streak_penalty × drawdown × log(compound return)",
            "low_streak_pool": "max_losing_streak <= 4 or 5, hit_rate >= 55% where noted",
        },
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))

    print(f"Low-streak search: {len(results)} rules | {ss} -> {today}\n")
    if live:
        print(f"LIVE {live['strategy']}: {live['record']} hit={live['hit_rate']:.1%} max_streak={live['max_losing_streak']} mix={live['mix']}\n")

    print("TOP 10 — quality (hit + low streak + compound, shipped stakes):\n")
    print(f"{'Strategy':<42} {'Rec':>7} {'Hit':>6} {'MaxL':>5} {'Mix':>16} {'$5':>8} {'End$25':>12}")
    for r in by_quality[:10]:
        print(
            f"{r['strategy'][:42]:<42} {r['record']:>7} {r['hit_rate']:>5.1%} {r['max_losing_streak']:>5} "
            f"{str(r['mix']):>16} ${r['flat_profit_5']:>+6.0f} ${r['compound_end']:>10,.0f}"
        )

    print("\nBEST max losing streak ≤ 4, hit ≥ 55%:\n")
    for r in payload["best_hit_max_streak_4"][:8]:
        print(
            f"  {r['strategy'][:45]:<45} {r['record']} hit={r['hit_rate']:.1%} "
            f"streak={r['max_losing_streak']} mix={r['mix']} ${r['compound_end']:,.0f}"
        )

    print("\nBEST using 3-leg (≥5 days), max streak ≤ 5:\n")
    for r in payload["best_with_3leg_min5_days"][:8]:
        print(
            f"  {r['strategy'][:45]:<45} {r['record']} hit={r['hit_rate']:.1%} "
            f"streak={r['max_losing_streak']} mix={r['mix']}"
        )
    print(f"\nFull results: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
