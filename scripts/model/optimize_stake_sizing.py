"""Optimize stake % by bankroll size and bet type (single / 2-leg / 3-leg) on 2026 walk-forward."""

from __future__ import annotations

import itertools
import json
from datetime import date
from pathlib import Path

from backtest_daily_recommendations import STAKE
from backtest_parlays import odds_backtest_range, season_start_for
from exhaustive_strategy_search import (
    action_to_bet,
    build_daily_snapshots,
    day_actions_for_rule,
    flat_stats_for_snapshots,
    load_moneyline_by_day,
)

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "stake-sizing-optimizer.json"

STRATEGY = "two_or_three_or_single"
FLAT_STAKE_GRID = [round(x * 0.05, 2) for x in range(1, 11)]  # 5% .. 50%
TIERED_STAKE_GRID = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
BANKROLLS = [0.35, 10.0, 100.0, 1000.0, 10_000.0]
MAX_DAILY_EXPOSURE = 0.50  # hard cap per calendar day (sum of bet stakes)


def leg_count(bet: dict) -> int:
    legs = bet.get("legs")
    return len(legs) if legs else 1


def bet_score(bet: dict) -> float:
    if bet.get("legs"):
        prob = 1.0
        for leg in bet["legs"]:
            prob *= leg.get("model_probability", 0.5)
        return bet.get("ev", 0) * prob
    return bet.get("ev", 0) * bet.get("model_probability", 0.5)


def compound_bets(
    bets: list[dict],
    stake_fn,
    start: float,
    daily_cap: float | None = MAX_DAILY_EXPOSURE,
) -> dict:
    bankroll = start
    min_bankroll = start
    by_day: dict[str, list[dict]] = {}
    for bet in bets:
        by_day.setdefault(bet["date"], []).append(bet)

    for day in sorted(by_day):
        day_bets = by_day[day]
        raw_pcts = [min(stake_fn(bet), daily_cap or 1.0) for bet in day_bets]
        total = sum(raw_pcts)
        if daily_cap and total > daily_cap:
            scale = daily_cap / total
            pcts = [p * scale for p in raw_pcts]
        else:
            pcts = raw_pcts

        for bet, pct in zip(day_bets, pcts):
            stake = bankroll * pct
            bankroll += bet["profit"] * (stake / STAKE)
            min_bankroll = min(min_bankroll, bankroll)

    flat = flat_stats_for_snapshots([{"bets": bets}])
    return {
        "end": round(bankroll, 4),
        "profit": round(bankroll - start, 4),
        "min_bankroll": round(min_bankroll, 4),
        "min_pct_of_start": round(min_bankroll / start, 4) if start else 0.0,
        "bets": len(bets),
        **flat,
    }


def collect_bets(moneyline_by_day: dict[str, list[dict]], rule: str) -> list[dict]:
    bets: list[dict] = []
    for day in sorted(moneyline_by_day):
        for action in day_actions_for_rule(moneyline_by_day[day], rule):
            bets.append(action_to_bet(action, day))
    return bets


def best_flat(bets: list[dict], start: float) -> dict:
    rows = []
    best = None
    for pct in FLAT_STAKE_GRID:
        result = compound_bets(bets, lambda _b, p=pct: p, start)
        row = {"stake_pct": pct, **result}
        rows.append(row)
        if best is None or row["end"] > best["end"]:
            best = row
    return {"best": best, "grid": rows}


def best_flat_safe(bets: list[dict], start: float, min_floor_ratio: float = 0.5) -> dict | None:
    rows = []
    for pct in FLAT_STAKE_GRID:
        result = compound_bets(bets, lambda _b, p=pct: p, start)
        if result["min_pct_of_start"] >= min_floor_ratio:
            rows.append({"stake_pct": pct, **result})
    if not rows:
        return None
    return max(rows, key=lambda r: r["end"])


def best_tiered_by_legs(bets: list[dict], start: float) -> dict:
    leg_counts = sorted({leg_count(b) for b in bets})
    rows = []
    best = None
    for combo in itertools.product(TIERED_STAKE_GRID, repeat=len(leg_counts)):
        stake_map = dict(zip(leg_counts, combo))
        result = compound_bets(bets, lambda b, m=stake_map: m.get(leg_count(b), 0.25), start)
        row = {
            "stake_by_legs": {str(k): v for k, v in stake_map.items()},
            **result,
        }
        rows.append(row)
        if best is None or row["end"] > best["end"]:
            best = row
    return {"best": best, "leg_counts_present": leg_counts}


def best_tiered_safe(bets: list[dict], start: float, min_floor_ratio: float = 0.5) -> dict | None:
    leg_counts = sorted({leg_count(b) for b in bets})
    safe = []
    for combo in itertools.product(TIERED_STAKE_GRID, repeat=len(leg_counts)):
        stake_map = dict(zip(leg_counts, combo))
        result = compound_bets(bets, lambda b, m=stake_map: m.get(leg_count(b), 0.25), start)
        if result["min_pct_of_start"] >= min_floor_ratio:
            safe.append({"stake_by_legs": {str(k): v for k, v in stake_map.items()}, **result})
    if not safe:
        return None
    return max(safe, key=lambda r: r["end"])


def best_score_tiered(bets: list[dict], start: float) -> dict:
    """High / mid / low score terciles get different stake %."""
    scores = [bet_score(b) for b in bets]
    if not scores:
        return {"best": None}
    sorted_scores = sorted(scores)
    t1 = sorted_scores[len(sorted_scores) // 3]
    t2 = sorted_scores[(2 * len(sorted_scores)) // 3]

    def tier(bet: dict) -> str:
        s = bet_score(bet)
        if s >= t2:
            return "high"
        if s >= t1:
            return "mid"
        return "low"

    tier_keys = ("low", "mid", "high")
    best = None
    for combo in itertools.product(TIERED_STAKE_GRID, repeat=3):
        stake_map = dict(zip(tier_keys, combo))
        result = compound_bets(bets, lambda b, m=stake_map: m[tier(b)], start)
        row = {"stake_by_score_tier": stake_map, "score_cutoffs": {"t1": round(t1, 2), "t2": round(t2, 2)}, **result}
        if best is None or row["end"] > best["end"]:
            best = row
    return {"best": best}


def summarize_by_type(bets: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for n in (1, 2, 3):
        subset = [b for b in bets if leg_count(b) == n]
        if not subset:
            continue
        flat = flat_stats_for_snapshots([{"bets": subset}])
        out[str(n)] = {
            "bets": len(subset),
            "wins": sum(int(b["won"]) for b in subset),
            "losses": sum(int(not b["won"]) for b in subset),
            **flat,
        }
    return out


def main() -> None:
    odds_end_2025 = date(2025, 8, 17)
    start_2026, end_2026, odds_meta = odds_backtest_range(__import__("historical_odds").HistoricalOddsStore())
    moneyline_by_day, walk_meta = load_moneyline_by_day(
        start_2026, end_2026, season_start_for(2025), odds_end_2025
    )
    bets = collect_bets(moneyline_by_day, STRATEGY)
    by_type = summarize_by_type(bets)

    per_bankroll: dict[str, dict] = {}
    for bankroll in BANKROLLS:
        key = str(bankroll)
        flat = best_flat(bets, bankroll)
        tiered = best_tiered_by_legs(bets, bankroll)
        per_bankroll[key] = {
            "bankroll": bankroll,
            "flat_best": flat["best"],
            "flat_safe_50pct_floor": best_flat_safe(bets, bankroll, 0.5),
            "tiered_by_legs_best": tiered["best"],
            "tiered_by_legs_safe_50pct_floor": best_tiered_safe(bets, bankroll, 0.5),
            "score_tiered_best": best_score_tiered(bets, bankroll)["best"],
        }

    # Pick global recommendation for $10 and $10k
    rec_10 = per_bankroll["10.0"]
    rec_10k = per_bankroll["10000.0"]

    output = {
        "generated_at": date.today().isoformat(),
        "method": "stake_sizing_sweep_2026",
        "strategy": STRATEGY,
        "date_range": {"start": start_2026.isoformat(), "end": end_2026.isoformat()},
        "daily_exposure_cap": MAX_DAILY_EXPOSURE,
        "flat_stake_grid": FLAT_STAKE_GRID,
        "tiered_stake_grid": TIERED_STAKE_GRID,
        "bet_type_breakdown": by_type,
        "per_bankroll": per_bankroll,
        "recommendation": {
            "summary": (
                "Tiered stakes by leg count usually beat one flat % when singles and parlays mix. "
                "Aggressive flat 40-50% maximizes backtest end but often breaches 50% min-bankroll floor. "
                "Use tiered safe rows for live betting."
            ),
            "for_10_dollars": {
                "aggressive_flat": rec_10["flat_best"],
                "safe_flat": rec_10["flat_safe_50pct_floor"],
                "aggressive_tiered": rec_10["tiered_by_legs_best"],
                "safe_tiered": rec_10["tiered_by_legs_safe_50pct_floor"],
            },
            "for_10k": {
                "aggressive_flat": rec_10k["flat_best"],
                "safe_flat": rec_10k["flat_safe_50pct_floor"],
                "aggressive_tiered": rec_10k["tiered_by_legs_best"],
                "safe_tiered": rec_10k["tiered_by_legs_safe_50pct_floor"],
            },
        },
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    plan_path = Path(__file__).resolve().parents[2] / "public" / "betting-plan.json"
    safe_tiered = rec_10["tiered_by_legs_safe_50pct_floor"] or rec_10["tiered_by_legs_best"]
    plan_path.write_text(
        json.dumps(
            {
                "generated_at": date.today().isoformat(),
                "strategy": STRATEGY,
                "strategy_rules": [
                    "Always-2 parlay (filtered edge/anchor, else top-2 positive-EV legs on different games)",
                    "Premium filtered 3-leg when it scores higher than the always-2 ticket",
                    "Qualified single moneyline when it scores higher than both parlay options",
                    "One bet per day — highest score wins",
                ],
                "stake_by_leg_count": safe_tiered["stake_by_legs"] if safe_tiered else {"1": 0.45, "2": 0.25, "3": 0.5},
                "flat_stake_fallback": rec_10["flat_best"]["stake_pct"] if rec_10.get("flat_best") else 0.35,
                "daily_exposure_cap": MAX_DAILY_EXPOSURE,
                "backtest_period": {"start": start_2026.isoformat(), "end": end_2026.isoformat()},
                "retuned_from": "optimize_stake_sizing.py walk-forward on current season",
            },
            indent=2,
        )
    )

    print(f"Strategy: {STRATEGY} | {len(bets)} bets | types: {by_type}")
    for label, br in [("$10", 10.0), ("$10k", 10000.0)]:
        row = per_bankroll[str(br)]
        fb = row["flat_best"]
        tb = row["tiered_by_legs_best"]
        ts = row["tiered_by_legs_safe_50pct_floor"]
        print(f"\n{label} aggressive flat: {fb['stake_pct']*100:.0f}% -> ${fb['end']:,.2f} (min {fb['min_pct_of_start']*100:.0f}% of start)")
        print(f"{label} tiered best: {tb['stake_by_legs']} -> ${tb['end']:,.2f} (min {tb['min_pct_of_start']*100:.0f}%)")
        if ts:
            print(f"{label} tiered SAFE: {ts['stake_by_legs']} -> ${ts['end']:,.2f} (min {ts['min_pct_of_start']*100:.0f}%)")


if __name__ == "__main__":
    main()
