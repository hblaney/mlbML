"""Advanced strategy research — test filters and hybrids beyond the live plan."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from backtest_parlays import odds_backtest_range, season_start_for, settle_parlay
from exhaustive_strategy_search import (
    STAKE,
    DayAction,
    action_to_bet,
    build_daily_snapshots,
    day_actions_for_rule,
    flat_stats_for_snapshots,
    load_moneyline_by_day,
    pick_always_n,
    pick_filtered,
)
from backtest_strategy_optimizer import (
    leg_score_for_parlay,
    pick_forced_top_legs,
    positive_ev_legs,
)

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "strategy-research.json"
STAKE_TIERED = {1: 0.45, 2: 0.35, 3: 0.50}
DAILY_CAP = 0.50  # matches betting-plan.json / optimize_stake_sizing.py
CONF_OK = {"Medium", "High", "Elite"}


def filter_candidates(candidates: list[dict], min_conf: str | None = None, min_edge: float | None = None) -> list[dict]:
    out = candidates
    if min_conf == "no_low":
        out = [c for c in out if c.get("confidence") in CONF_OK]
    if min_edge is not None:
        out = [c for c in out if c.get("edge", 0) >= min_edge]
    return out


def pick_always_n_filtered(candidates: list[dict], leg_count: int, min_conf: str | None = None, min_edge: float | None = None) -> dict | None:
    pool = filter_candidates(candidates, min_conf, min_edge)
    return pick_always_n(pool, leg_count)


def pick_always_n_forced_no_low(candidates: list[dict], leg_count: int) -> dict | None:
    """Filtered parlay from full pool; forced fallback excludes Low-confidence legs."""
    filtered = pick_filtered(candidates, leg_count)
    if filtered:
        return filtered
    pool = filter_candidates(candidates, min_conf="no_low")
    return pick_forced_top_legs(pool, leg_count)


def pick_two_or_three_or_single_variant(
    candidates: list[dict],
    *,
    min_conf: str | None = None,
    min_edge: float | None = None,
    allow_forced: bool = True,
) -> list[DayAction]:
    pool = filter_candidates(candidates, min_conf, min_edge)

    def parlay_action(ticket: dict | None, tag: str) -> DayAction | None:
        if ticket is None or not ticket.get("legs"):
            return None
        return DayAction(legs=ticket["legs"], single=None, label=tag)

    def single_action() -> DayAction | None:
        from backtest_daily_recommendations import pick_best_moneyline

        single, _ = pick_best_moneyline(candidates)
        if single is None:
            return None
        return DayAction(legs=None, single=single, label="single")

    if allow_forced:
        p2 = pick_always_n(pool, 2)
    else:
        p2 = pick_filtered(pool, 2)

    p3 = pick_filtered(pool, 3)
    from backtest_daily_recommendations import pick_best_moneyline

    single_pick, _ = pick_best_moneyline(candidates)

    opts: list[tuple[float, dict, str, bool]] = []
    if p2:
        opts.append((p2["score"], p2, "p2", False))
    if p3:
        opts.append((p3["score"], p3, "p3", False))
    if single_pick:
        opts.append((single_pick["ev"] * single_pick["model_probability"], single_pick, "single", True))

    if not opts:
        return []

    _, ticket, tag, is_single = max(opts, key=lambda x: x[0])
    if is_single:
        return [DayAction(legs=None, single=ticket, label="single")]
    return [DayAction(legs=ticket["legs"], single=None, label=tag)]


def day_actions_advanced(candidates: list[dict], rule: str) -> list[DayAction]:
    if rule == "two_or_three_or_single":
        return day_actions_for_rule(candidates, rule)

    if rule == "no_low_parlay_223s":
        return pick_two_or_three_or_single_variant(candidates, min_conf="no_low")

    if rule == "no_forced_223s":
        return pick_two_or_three_or_single_variant(candidates, allow_forced=False)

    if rule == "no_low_no_forced_223s":
        return pick_two_or_three_or_single_variant(candidates, min_conf="no_low", allow_forced=False)

    if rule == "min_edge8_223s":
        return pick_two_or_three_or_single_variant(candidates, min_edge=0.08)

    if rule == "no_low_min_edge8_223s":
        return pick_two_or_three_or_single_variant(candidates, min_conf="no_low", min_edge=0.08)

    if rule == "filtered_223s_only":
        pool = candidates
        opts = []
        for n, tag in ((2, "f2"), (3, "f3")):
            t = pick_filtered(pool, n)
            if t:
                opts.append((t["score"], t, tag))
        single, _ = __import__("backtest_daily_recommendations", fromlist=["pick_best_moneyline"]).pick_best_moneyline(pool)
        if single:
            opts.append((single["ev"] * single["model_probability"], single, "single"))
        if not opts:
            return []
        _, ticket, tag = max(opts, key=lambda x: x[0])
        if tag == "single":
            return [DayAction(legs=None, single=ticket, label="single")]
        return [DayAction(legs=ticket["legs"], single=None, label=tag)]

    if rule == "high_elite_parlay_or_single":
        pool = [c for c in candidates if c.get("confidence") in {"High", "Elite"}]
        opts = []
        p2 = pick_always_n(pool, 2)
        p3 = pick_filtered(pool, 3)
        if p2:
            opts.append((p2["score"], p2, "p2"))
        if p3:
            opts.append((p3["score"], p3, "p3"))
        single, _ = __import__("backtest_daily_recommendations", fromlist=["pick_best_moneyline"]).pick_best_moneyline(candidates)
        if single:
            opts.append((single["ev"] * single["model_probability"], single, "single"))
        if not opts:
            return []
        _, ticket, tag = max(opts, key=lambda x: x[0])
        if tag == "single":
            return [DayAction(legs=None, single=ticket, label="single")]
        return [DayAction(legs=ticket["legs"], single=None, label=tag)]

    if rule == "no_low_forced_only_223s":
        pool = candidates
        p2 = pick_always_n_forced_no_low(pool, 2)
        p3 = pick_filtered(pool, 3)
        from backtest_daily_recommendations import pick_best_moneyline

        single_pick, _ = pick_best_moneyline(candidates)
        opts: list[tuple[float, dict, str, bool]] = []
        if p2:
            opts.append((p2["score"], p2, "p2", False))
        if p3:
            opts.append((p3["score"], p3, "p3", False))
        if single_pick:
            opts.append((single_pick["ev"] * single_pick["model_probability"], single_pick, "single", True))
        if not opts:
            return []
        _, ticket, tag, is_single = max(opts, key=lambda x: x[0])
        if is_single:
            return [DayAction(legs=None, single=ticket, label="single")]
        return [DayAction(legs=ticket["legs"], single=None, label=tag)]

    if rule == "no_low_never_skip_223s":
        acts = pick_two_or_three_or_single_variant(candidates, min_conf="no_low")
        if acts:
            return acts
        from backtest_daily_recommendations import pick_best_moneyline

        single_pick, _ = pick_best_moneyline(candidates)
        if single_pick:
            return [DayAction(legs=None, single=single_pick, label="single")]
        return []

    if rule == "medium_plus_223s":
        pool = [c for c in candidates if c.get("confidence") in {"Medium", "High", "Elite"}]
        return pick_two_or_three_or_single_variant(pool)

    if rule == "best_combo_score_day":
        opts = []
        for n in (2, 3):
            from backtest_strategy_optimizer import pick_best_combo

            c = pick_best_combo(candidates, n)
            if c:
                opts.append((c["score"], c, f"c{n}"))
        p2 = pick_always_n(candidates, 2)
        p3 = pick_filtered(candidates, 3)
        if p2:
            opts.append((p2["score"], p2, "p2"))
        if p3:
            opts.append((p3["score"], p3, "p3"))
        single, _ = __import__("backtest_daily_recommendations", fromlist=["pick_best_moneyline"]).pick_best_moneyline(candidates)
        if single:
            opts.append((single["ev"] * single["model_probability"], single, "single"))
        if not opts:
            return []
        _, ticket, tag = max(opts, key=lambda x: x[0])
        if tag == "single":
            return [DayAction(legs=None, single=ticket, label="single")]
        return [DayAction(legs=ticket["legs"], single=None, label=tag)]

    raise ValueError(rule)


def build_snapshots(ml: dict, rule: str) -> list[dict]:
    snaps = []
    for day in sorted(ml):
        if rule == "two_or_three_or_single":
            actions = day_actions_for_rule(ml[day], rule)
        else:
            actions = day_actions_advanced(ml[day], rule)
        if not actions:
            continue
        bets = [action_to_bet(a, day) for a in actions]
        snaps.append({"date": day, "bets": bets})
    return snaps


def compound(snaps: list[dict], start: float, stake_map: dict[int, float]) -> dict:
    bankroll = start
    min_br = start
    wins = losses = 0
    max_streak = cur = 0

    for snap in snaps:
        day_won = True
        raw = [stake_map.get(len(b.get("legs", [])) or 1, 0.25) for b in snap["bets"]]
        total = sum(raw)
        scale = DAILY_CAP / total if total > DAILY_CAP else 1.0
        for bet, pct in zip(snap["bets"], [r * scale for r in raw]):
            bankroll += bet["profit"] * (bankroll * pct / STAKE)
            if not bet["won"]:
                day_won = False
        min_br = min(min_br, bankroll)
        if day_won:
            if cur:
                max_streak = max(max_streak, cur)
            cur = 0
            wins += 1
        else:
            cur += 1
            max_streak = max(max_streak, cur)
            losses += 1

    flat = flat_stats_for_snapshots(snaps)
    return {
        "end": round(bankroll, 4),
        "profit": round(bankroll - start, 4),
        "min_bankroll": round(min_br, 4),
        "record": f"{wins}-{losses}",
        "days": wins + losses,
        "max_losing_streak": max_streak,
        **flat,
    }


def run_period(start: date, end: date, prior: tuple[date, date]) -> dict[str, dict]:
    ml, _ = load_moneyline_by_day(start, end, prior[0], prior[1])
    ml = {d: c for d, c in ml.items() if date.fromisoformat(d) <= end}
    results = {}
    rules = [
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
    for rule in rules:
        snaps = build_snapshots(ml, rule)
        results[rule] = {
            "c13": compound(snaps, 0.13, STAKE_TIERED),
            "c10": compound(snaps, 10.0, STAKE_TIERED),
            "c10k": compound(snaps, 10000.0, STAKE_TIERED),
        }
    return results


def main() -> None:
    odds_end_2025 = date(2025, 8, 17)
    r2026 = run_period(date(2026, 3, 20), date(2026, 6, 16), (season_start_for(2025), odds_end_2025))
    r2025 = run_period(season_start_for(2025), odds_end_2025, (season_start_for(2024), date(2024, 10, 1)))

    ranked = sorted(
        r2026.items(),
        key=lambda kv: kv[1]["c13"]["end"],
        reverse=True,
    )

    best = ranked[0][0]
    output = {
        "generated_at": date.today().isoformat(),
        "method": "advanced_strategy_research",
        "live_baseline": "two_or_three_or_single",
        "stake_tiered": STAKE_TIERED,
        "ranked_2026_by_13c_compound": [
            {"strategy": k, **v["c13"], "flat_roi_2025": r2025[k]["c13"]["flat_roi"]}
            for k, v in ranked
        ],
        "full_2026": r2026,
        "full_2025": {k: v["c13"] for k, v in r2025.items()},
        "recommendation": {
            "strategy": best,
            "reason": "Highest 2026 compound from $0.13 with tiered stakes among tested advanced rules.",
            "vs_baseline_2026": {
                "baseline_end_13c": r2026["two_or_three_or_single"]["c13"]["end"],
                "winner_end_13c": r2026[best]["c13"]["end"],
            },
            "oos_2025_flat_roi": r2025[best]["c13"]["flat_roi"],
            "baseline_2025_flat_roi": r2025["two_or_three_or_single"]["c13"]["flat_roi"],
        },
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print("2026 ranked ($0.13 compound, tiered 45/25/50):\n")
    for row in output["ranked_2026_by_13c_compound"]:
        print(
            f"  {row['strategy']:<28} end ${row['end']:>10.2f}  flat {row['flat_roi']:>6.1%}  "
            f"2025 flat {row['flat_roi_2025']:>6.1%}  streak {row['max_losing_streak']}  {row['record']}"
        )
    print(f"\nRecommended: {best}")
    print(f"OOS 2025 flat: {output['recommendation']['oos_2025_flat_roi']:.1%}")


if __name__ == "__main__":
    main()
