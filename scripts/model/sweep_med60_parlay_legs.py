"""Sweep med60 parlay rules: all leg-count and pick-method combinations."""

from __future__ import annotations

import itertools
import json
from collections import Counter
from datetime import date
from pathlib import Path

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
from strategy_next_tests import enrich_moneyline, no_low_pool

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "med60-parlay-sweep.json"
FLAT_USD = 5.0
MIN_PROB = 0.60
METHODS = ("always", "filtered", "top_prob", "forced")


def pool60(candidates: list[dict]) -> list[dict]:
    return [c for c in no_low_pool(candidates) if float(c.get("model_probability", 0)) >= MIN_PROB]


def top_n_by_prob(pool: list[dict], n: int) -> list[dict]:
    legs: list[dict] = []
    seen: set[int | str] = set()
    for candidate in sorted(pool, key=lambda row: float(row.get("model_probability", 0)), reverse=True):
        game_pk = candidate.get("gamePk")
        if game_pk in seen:
            continue
        legs.append(candidate)
        seen.add(game_pk)
        if len(legs) == n:
            break
    return legs


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


def make_rule(*, leg_counts: tuple[int, ...], method: str, allow_single: bool = False) -> callable:
    leg_counts = tuple(sorted(set(leg_counts)))

    def rule(candidates: list[dict]) -> list[DayAction]:
        pool = pool60(candidates)
        if len(pool) < 2:
            return day_actions_for_rule(candidates, "no_low_parlay_223s")

        opts: list[tuple[float, dict, str]] = []
        for n in leg_counts:
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

        score, ticket, tag = max(opts, key=lambda row: row[0])
        if tag == "single":
            return [DayAction(legs=None, single=ticket, label="single")]
        return [DayAction(legs=ticket["legs"], single=None, label=tag)]

    return rule


def make_mixed_method_rule(*, leg_counts: tuple[int, ...], methods_by_legs: dict[int, str]) -> callable:
    def rule(candidates: list[dict]) -> list[DayAction]:
        pool = pool60(candidates)
        if len(pool) < 2:
            return day_actions_for_rule(candidates, "no_low_parlay_223s")

        opts: list[tuple[float, dict, str]] = []
        for n in leg_counts:
            method = methods_by_legs.get(n, "always")
            ticket = ticket_for_method(pool, n, method)
            if ticket and ticket.get("legs"):
                opts.append((float(ticket["score"]), ticket, f"p{n}"))

        if not opts:
            return day_actions_for_rule(candidates, "no_low_parlay_223s")

        _, ticket, tag = max(opts, key=lambda row: row[0])
        return [DayAction(legs=ticket["legs"], single=None, label=tag)]

    return rule


def build_snapshots(ml: dict[str, list[dict]], rule_fn: callable) -> list[dict]:
    snaps: list[dict] = []
    for day in sorted(ml):
        actions = rule_fn(ml[day])
        if not actions:
            continue
        snaps.append({"date": day, "bets": [action_to_bet(a, day) for a in actions]})
    return snaps


def summarize(name: str, snaps: list[dict]) -> dict:
    profit = wins = 0.0
    mix: Counter[int] = Counter()
    mix_wins: Counter[int] = Counter()
    for snap in snaps:
        bet = snap["bets"][0]
        profit += bet["profit"] * (FLAT_USD / STAKE)
        won = bool(bet.get("won"))
        wins += int(won)
        leg_count = len(bet.get("legs") or [bet])
        mix[leg_count] += 1
        if won:
            mix_wins[leg_count] += 1

    days = len(snaps)
    losses = days - int(wins)
    return {
        "name": name,
        "days": days,
        "wins": int(wins),
        "losses": losses,
        "record": f"{int(wins)}-{losses}",
        "hit_rate": round(wins / days, 4) if days else 0.0,
        "flat_profit_usd": round(profit, 2),
        "flat_roi": round(profit / (days * FLAT_USD), 4) if days else 0.0,
        "mix": {str(k): mix[k] for k in sorted(mix)},
        "mix_records": {
            str(k): f"{mix_wins[k]}-{mix[k] - mix_wins[k]}" for k in sorted(mix)
        },
    }


def iter_rules() -> list[tuple[str, callable]]:
    rules: list[tuple[str, callable]] = [
        ("CURRENT no_low_parlay_223s", lambda c: day_actions_for_rule(c, "no_low_parlay_223s")),
    ]

    for method in METHODS:
        for r in range(1, 4):
            for leg_counts in itertools.combinations((2, 3, 4), r):
                label = f"med60≥2 | {method} | best of {leg_counts}"
                rules.append((label, make_rule(leg_counts=leg_counts, method=method)))

    # Mixed: always-2 competes with filtered/premium 3 and 4 (mirrors live naming)
    rules.append(
        (
            "med60≥2 | always-2 + filtered-3/4",
            make_mixed_method_rule(leg_counts=(2, 3, 4), methods_by_legs={2: "always", 3: "filtered", 4: "filtered"}),
        )
    )
    rules.append(
        (
            "med60≥2 | always-2/3/4 + allow single",
            make_rule(leg_counts=(2, 3, 4), method="always", allow_single=True),
        )
    )

    # Fixed leg count (no score competition) — top prob force
    for n in (2, 3, 4):

        def fixed_n(candidates: list[dict], leg_count: int = n) -> list[DayAction]:
            pool = pool60(candidates)
            if len(pool) < leg_count:
                return day_actions_for_rule(candidates, "no_low_parlay_223s")
            legs = top_n_by_prob(pool, leg_count)
            if len(legs) < leg_count:
                return day_actions_for_rule(candidates, "no_low_parlay_223s")
            return [DayAction(legs=legs, single=None, label=f"force{leg_count}")]

        rules.append((f"med60≥{n} | force top-{n} by prob", fixed_n))

    return rules


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

    results: list[dict] = []
    for name, rule_fn in iter_rules():
        stats = summarize(name, build_snapshots(ml, rule_fn))
        results.append(stats)

    baseline_profit = next(r["flat_profit_usd"] for r in results if r["name"].startswith("CURRENT"))
    for row in results:
        row["vs_current_usd"] = round(row["flat_profit_usd"] - baseline_profit, 2)

    results.sort(key=lambda row: row["flat_profit_usd"], reverse=True)

    payload = {
        "generated_at": today.isoformat(),
        "season_start": season_start.isoformat(),
        "season_end": today.isoformat(),
        "bet_days": meta.get("game_days_with_odds"),
        "flat_stake_usd": FLAT_USD,
        "min_prob_trigger": MIN_PROB,
        "baseline_profit_usd": baseline_profit,
        "rule_count": len(results),
        "ranked": results,
        "top_10": results[:10],
        "bottom_5": results[-5:],
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))

    print(f"Season {season_start} -> {today} | ${FLAT_USD} flat | {len(results)} rules\n")
    print(f"{'Rank':<5} {'Profit':>9} {'vs base':>9} {'Record':>8} {'Hit':>6} {'Mix':>22}  Rule")
    for i, row in enumerate(results[:20], 1):
        print(
            f"{i:<5} ${row['flat_profit_usd']:>+8.2f} ${row['vs_current_usd']:>+8.2f} "
            f"{row['record']:>8} {row['hit_rate']:>5.1%} {str(row['mix']):>22}  {row['name']}"
        )
    print(f"\n... {len(results)} total. Full results: {OUTPUT_PATH}")
    print(f"\nBaseline CURRENT: ${baseline_profit:+.2f}")


if __name__ == "__main__":
    main()
