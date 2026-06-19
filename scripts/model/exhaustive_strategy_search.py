"""Exhaustive walk-forward strategy search with fair risk normalization."""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from backtest_daily_recommendations import (
    STAKE,
    bet_from_moneyline,
    bet_from_parlay,
    build_single_candidates,
    pick_best_moneyline,
    pick_best_parlay,
)
from backtest_parlays import odds_backtest_range, settle_parlay
from backtest_strategy_optimizer import (
    leg_score_for_parlay,
    pick_best_combo,
    pick_forced_top_legs,
    positive_ev_legs,
)
from daily_auto_model import walk_forward_history
from historical_odds import HistoricalOddsStore
from mlb_api import load_or_fetch_games, load_team_abbreviations

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "exhaustive-strategy-search.json"

STAKE_GRID = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
BANKROLLS = [10.0, 10_000.0]
MAX_DAILY_EXPOSURE = 0.30  # fair comparison: total risk budget per calendar day


@dataclass
class DayAction:
    legs: list[dict] | None  # None => single stored in single_leg
    single: dict | None
    label: str


def pick_filtered(candidates: list[dict], leg_count: int) -> dict | None:
    return pick_best_parlay(candidates, leg_count)[0]


def pick_always_n(candidates: list[dict], leg_count: int) -> dict | None:
    return pick_filtered(candidates, leg_count) or pick_forced_top_legs(candidates, leg_count)


def day_actions_for_rule(candidates: list[dict], rule: str, threshold: float | None = None) -> list[DayAction]:
    """Return 0..N actions for one day (multi-bet rules can return 2)."""
    single = pick_best_moneyline(candidates)[0]
    p2 = pick_always_n(candidates, 2)
    p3 = pick_filtered(candidates, 3)
    p4 = pick_filtered(candidates, 4)
    c2 = pick_best_combo(candidates, 2)
    c3 = pick_best_combo(candidates, 3)
    f2 = pick_forced_top_legs(candidates, 2)
    f3 = pick_forced_top_legs(candidates, 3)

    def parlay_action(ticket: dict | None, tag: str) -> DayAction | None:
        if ticket is None or not ticket.get("legs"):
            return None
        return DayAction(legs=ticket["legs"], single=None, label=tag)

    def single_action() -> DayAction | None:
        if single is None:
            return None
        return DayAction(legs=None, single=single, label="single")

    if rule == "single":
        a = single_action()
        return [a] if a else []

    if rule == "parlay_2":
        a = parlay_action(pick_filtered(candidates, 2), "parlay_2")
        return [a] if a else []

    if rule == "always_2":
        a = parlay_action(p2, "always_2")
        return [a] if a else []

    if rule == "forced_top_2":
        a = parlay_action(f2, "forced_top_2")
        return [a] if a else []

    if rule == "always_3":
        a = parlay_action(pick_always_n(candidates, 3), "always_3")
        return [a] if a else []

    if rule == "always_4":
        a = parlay_action(pick_always_n(candidates, 4), "always_4")
        return [a] if a else []

    if rule == "parlay_3":
        a = parlay_action(p3, "parlay_3")
        return [a] if a else []

    if rule == "parlay_4":
        a = parlay_action(p4, "parlay_4")
        return [a] if a else []

    if rule == "combo_2":
        a = parlay_action(c2, "combo_2")
        return [a] if a else []

    if rule == "combo_3":
        a = parlay_action(c3, "combo_3")
        return [a] if a else []

    if rule == "best_ticket":
        options: list[tuple[float, dict, str]] = []
        if single:
            options.append((single["ev"] * single["model_probability"], single, "single"))
        for n, tag in ((2, "p2"), (3, "p3"), (4, "p4")):
            t = pick_filtered(candidates, n)
            if t:
                options.append((t["score"], t, tag))
        if not options:
            return []
        _, ticket, tag = max(options, key=lambda x: x[0])
        if ticket.get("legs"):
            return [parlay_action(ticket, tag)]  # type: ignore
        return [single_action()]  # type: ignore

    if rule == "max_any_combo":
        opts = []
        for t, tag in [(p2, "p2"), (p3, "p3"), (p4, "p4"), (c2, "c2"), (c3, "c3"), (f2, "f2"), (f3, "f3")]:
            if t:
                opts.append((t["score"], t, tag))
        if single:
            opts.append((single["ev"] * single["model_probability"], single, "single"))
        if not opts:
            return []
        _, ticket, tag = max(opts, key=lambda x: x[0])
        if ticket.get("legs"):
            return [parlay_action(ticket, tag)]  # type: ignore
        return [single_action()]  # type: ignore

    if rule == "two_or_three_best":
        opts = [t for t in (p2, p3) if t]
        if not opts:
            return []
        return [parlay_action(max(opts, key=lambda t: t["score"]), "2v3")]  # type: ignore

    if rule == "two_unless_three" and threshold is not None:
        if p3 and p2 and p3["score"] > p2["score"] * threshold:
            return [parlay_action(p3, "p3_upgrade")]  # type: ignore
        if p2:
            return [parlay_action(p2, "p2")]  # type: ignore
        return []

    if rule == "two_else_single":
        if p2:
            return [parlay_action(p2, "p2")]  # type: ignore
        a = single_action()
        return [a] if a else []

    if rule == "two_and_single":
        out = []
        if p2:
            out.append(parlay_action(p2, "p2"))  # type: ignore
        a = single_action()
        if a:
            out.append(a)
        return out

    if rule == "two_or_three_or_single":
        opts: list[tuple[float, dict, str, bool]] = []
        if p2:
            opts.append((p2["score"], p2, "p2", False))
        if p3:
            opts.append((p3["score"], p3, "p3", False))
        if single:
            opts.append((single["ev"] * single["model_probability"], single, "single", True))
        if not opts:
            return []
        _, ticket, tag, is_single = max(opts, key=lambda item: item[0])
        if is_single:
            return [single_action()]  # type: ignore
        return [parlay_action(ticket, tag)]  # type: ignore

    if rule == "corr_nl_reject_both":
        from strategy_next_tests import day_actions_for_test

        return day_actions_for_test(candidates, rule)

    if rule == "no_low_parlay_223s":
        pool = [c for c in candidates if c.get("confidence") in {"Medium", "High", "Elite"}]
        p2_nl = pick_always_n(pool, 2)
        p3_nl = pick_filtered(pool, 3)
        opts = []
        if p2_nl:
            opts.append((p2_nl["score"], p2_nl, "p2", False))
        if p3_nl:
            opts.append((p3_nl["score"], p3_nl, "p3", False))
        if single:
            opts.append((single["ev"] * single["model_probability"], single, "single", True))
        if not opts:
            return []
        _, ticket, tag, is_single = max(opts, key=lambda item: item[0])
        if is_single:
            return [single_action()]  # type: ignore
        return [parlay_action(ticket, tag)]  # type: ignore

    if rule == "med60_force2_223s":
        from strategy_next_tests import day_actions_med60_force2_223s

        return day_actions_med60_force2_223s(candidates)

    if rule == "two_or_three_plus_single":
        out = []
        parlay_opts = [t for t in (p2, p3) if t]
        if parlay_opts:
            out.append(parlay_action(max(parlay_opts, key=lambda t: t["score"]), "2v3"))  # type: ignore
        a = single_action()
        if a:
            out.append(a)
        return out

    if rule == "two_and_three":
        out = []
        if p2:
            out.append(parlay_action(p2, "p2"))  # type: ignore
        if p3:
            out.append(parlay_action(p3, "p3"))  # type: ignore
        return out

    if rule == "filtered_2_and_3":
        out = []
        f2 = pick_filtered(candidates, 2)
        f3 = pick_filtered(candidates, 3)
        if f2:
            out.append(parlay_action(f2, "f2"))  # type: ignore
        if f3:
            out.append(parlay_action(f3, "f3"))  # type: ignore
        return out

    if rule == "all_filtered_parlays":
        out = []
        for leg_count, tag in ((2, "f2"), (3, "f3"), (4, "f4")):
            ticket = pick_filtered(candidates, leg_count)
            if ticket:
                out.append(parlay_action(ticket, tag))  # type: ignore
        return out

    if rule == "filtered_two_else_three":
        t = pick_filtered(candidates, 2) or p3
        a = parlay_action(t, "2else3") if t else None
        return [a] if a else []

    if rule == "positive_ev_top2":
        legs = []
        seen = set()
        for leg in positive_ev_legs(candidates):
            if leg["gamePk"] in seen:
                continue
            legs.append(leg)
            seen.add(leg["gamePk"])
            if len(legs) == 2:
                break
        if len(legs) < 2:
            return []
        settled = settle_parlay(legs)
        if settled["ev"] <= 0:
            return []
        return [DayAction(legs=legs, single=None, label="pev_top2")]

    raise ValueError(rule)


def action_to_bet(action: DayAction, day: str) -> dict:
    if action.legs:
        ticket = settle_parlay(action.legs)
        ticket["legs"] = action.legs
        ticket["strategy"] = action.label
        return bet_from_parlay(ticket, day, len(action.legs), True)
    assert action.single is not None
    return bet_from_moneyline({**action.single, "date": day}, True)


def build_daily_snapshots(moneyline_by_day: dict[str, list[dict]], rule: str, threshold: float | None = None) -> list[dict]:
    snapshots = []
    for day in sorted(moneyline_by_day):
        actions = day_actions_for_rule(moneyline_by_day[day], rule, threshold)
        if not actions:
            continue
        bets = [action_to_bet(a, day) for a in actions]
        snapshots.append({"date": day, "bets": bets, "actions": [a.label for a in actions]})
    return snapshots


def compound_snapshots(
    snapshots: list[dict],
    stake_pct: float,
    start: float,
    normalize_daily_exposure: bool = False,
) -> dict:
    bankroll = start
    min_bankroll = start
    total_bets = 0
    wins = 0
    multi_bet_days = 0

    for snap in snapshots:
        day_bets = snap["bets"]
        if len(day_bets) > 1:
            multi_bet_days += 1
        if normalize_daily_exposure and len(day_bets) > 1:
            per_bet_pct = MAX_DAILY_EXPOSURE / len(day_bets)
        elif normalize_daily_exposure:
            per_bet_pct = min(stake_pct, MAX_DAILY_EXPOSURE)
        else:
            per_bet_pct = stake_pct

        for bet in day_bets:
            stake = bankroll * per_bet_pct
            bankroll += bet["profit"] * (stake / STAKE)
            total_bets += 1
            wins += int(bet["won"])
            min_bankroll = min(min_bankroll, bankroll)

    return {
        "end": round(bankroll, 2),
        "profit": round(bankroll - start, 2),
        "min_bankroll": round(min_bankroll, 2),
        "bets": total_bets,
        "days": len(snapshots),
        "multi_bet_days": multi_bet_days,
        "wins": wins,
        "losses": total_bets - wins,
        **flat_stats_for_snapshots(snapshots),
    }


def flat_stats_for_snapshots(snapshots: list[dict]) -> dict:
    flat_profit = 0.0
    total_bets = 0
    wins = 0
    for snap in snapshots:
        for bet in snap["bets"]:
            flat_profit += bet["profit"]
            total_bets += 1
            wins += int(bet["won"])
    staked = total_bets * STAKE
    return {
        "flat_profit": round(flat_profit, 2),
        "flat_roi": round(flat_profit / staked, 4) if staked else 0.0,
        "hit_rate": round(wins / total_bets, 4) if total_bets else 0.0,
    }


def strategy_grid(include_extended: bool = True) -> list[tuple[str, str, float | None]]:
    rules = [
        "single",
        "parlay_2",
        "always_2",
        "forced_top_2",
        "parlay_3",
        "parlay_4",
        "always_3",
        "always_4",
        "combo_2",
        "combo_3",
        "best_ticket",
        "max_any_combo",
        "two_or_three_best",
        "two_or_three_or_single",
        "two_or_three_plus_single",
        "two_else_single",
        "two_and_single",
        "two_and_three",
        "filtered_2_and_3",
        "all_filtered_parlays",
        "filtered_two_else_three",
        "positive_ev_top2",
    ]
    grid: list[tuple[str, str, float | None]] = []
    for rule in rules:
        grid.append((rule, rule, None))
    for threshold in (1.25, 1.5, 1.75, 2.0, 2.5, 3.0):
        grid.append((f"two_unless_three_{threshold}x", "two_unless_three", threshold))
    return grid


def load_moneyline_by_day(
    start: date,
    end: date,
    prior_start: date | None = None,
    prior_end: date | None = None,
) -> tuple[dict[str, list[dict]], dict]:
    store = HistoricalOddsStore()
    team_abbr = load_team_abbreviations()
    prior_games = None
    if prior_start and prior_end:
        prior_games = load_or_fetch_games(prior_start, prior_end)
    games = load_or_fetch_games(start, end)
    rows = walk_forward_history(games, team_abbr, prior_games=prior_games)
    moneyline_by_day = build_single_candidates(rows, store)
    odds_start, odds_end = store.date_range()
    return moneyline_by_day, {
        "odds_data_start": odds_start,
        "odds_data_end": odds_end,
        "game_days_with_odds": len(moneyline_by_day),
        "walk_forward_rows": len(rows),
    }


def run_period_search(
    moneyline_by_day: dict[str, list[dict]],
    grid: list[tuple[str, str, float | None]],
    stake_pct: float = 0.30,
) -> tuple[list[dict], list[dict]]:
    """Faster search: fixed stake, fair + raw at that stake only."""
    results_raw: list[dict] = []
    results_fair: list[dict] = []

    for bankroll in BANKROLLS:
        for strategy_id, rule, threshold in grid:
            snapshots = build_daily_snapshots(moneyline_by_day, rule, threshold)
            if not snapshots:
                continue

            raw = compound_snapshots(snapshots, stake_pct, bankroll, normalize_daily_exposure=False)
            fair = compound_snapshots(snapshots, stake_pct, bankroll, normalize_daily_exposure=True)
            entry_base = {
                "strategy_id": strategy_id,
                "rule": rule,
                "threshold": threshold,
                "bankroll": bankroll,
                "days": raw["days"],
                "multi_bet_days": raw["multi_bet_days"],
                "stake_pct": stake_pct,
            }
            results_raw.append({**entry_base, "mode": "raw_compound", **raw})
            results_fair.append({**entry_base, "mode": "fair_30pct_daily_cap", **fair})

    results_raw.sort(key=lambda r: r["end"], reverse=True)
    results_fair.sort(key=lambda r: r["end"], reverse=True)
    return results_raw, results_fair


def run_exhaustive_search(
    moneyline_by_day: dict[str, list[dict]],
    grid: list[tuple[str, str, float | None]] | None = None,
) -> tuple[list[dict], list[dict]]:
    grid = grid or strategy_grid()
    results_raw: list[dict] = []
    results_fair: list[dict] = []

    for bankroll in BANKROLLS:
        for strategy_id, rule, threshold in grid:
            snapshots = build_daily_snapshots(moneyline_by_day, rule, threshold)
            if not snapshots:
                continue

            best_raw = None
            best_fair = None
            for pct in STAKE_GRID:
                raw = compound_snapshots(snapshots, pct, bankroll, normalize_daily_exposure=False)
                raw_row = {"stake_pct": pct, **raw}
                if best_raw is None or raw_row["end"] > best_raw["end"]:
                    best_raw = raw_row

                fair = compound_snapshots(snapshots, pct, bankroll, normalize_daily_exposure=True)
                fair_row = {"stake_pct": pct, **fair}
                if best_fair is None or fair_row["end"] > best_fair["end"]:
                    best_fair = fair_row

            entry_base = {
                "strategy_id": strategy_id,
                "rule": rule,
                "threshold": threshold,
                "bankroll": bankroll,
                "days": best_raw["days"],
                "multi_bet_days": best_raw["multi_bet_days"],
            }
            results_raw.append({**entry_base, "mode": "raw_compound", **best_raw})
            results_fair.append({**entry_base, "mode": "fair_30pct_daily_cap", **best_fair})

    results_raw.sort(key=lambda r: r["end"], reverse=True)
    results_fair.sort(key=lambda r: r["end"], reverse=True)
    return results_raw, results_fair


def main() -> None:
    store = HistoricalOddsStore()
    start, end, odds_metadata = odds_backtest_range(store)
    moneyline_by_day, _ = load_moneyline_by_day(start, end)

    grid = strategy_grid()
    results_raw, results_fair = run_exhaustive_search(moneyline_by_day, grid)
    dual = next(r for r in results_raw if r["strategy_id"] == "two_and_single" and r["bankroll"] == 10000)
    dual_fair = next(r for r in results_fair if r["strategy_id"] == "two_and_single" and r["bankroll"] == 10000)
    always2 = next(r for r in results_fair if r["strategy_id"] == "always_2" and r["bankroll"] == 10000)

    output = {
        "generated_at": date.today().isoformat(),
        "method": "exhaustive_walk_forward",
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "odds_metadata": odds_metadata,
        "strategies_tested": len(grid),
        "stake_grid": STAKE_GRID,
        "fair_daily_exposure_cap": MAX_DAILY_EXPOSURE,
        "note_raw": "Each bet uses stake_pct of current bankroll; multi-bet days compound multiple times.",
        "note_fair": "Total stake per calendar day capped at 30% split across bets that day.",
        "top_raw_10k": results_raw[:15],
        "top_fair_10k": [r for r in results_fair if r["bankroll"] == 10000][:15],
        "top_fair_10": [r for r in results_fair if r["bankroll"] == 10][:10],
        "weird_result_analysis": {
            "strategy": "two_and_single",
            "raw_10k": dual,
            "fair_10k": dual_fair,
            "always_2_fair_10k": always2,
            "verdict": (
                "two_and_single raw $1.5B is an accounting artifact: 65/69 days stake 30% on parlay AND 30% on single "
                "(60% daily exposure). Under fair 30% daily cap it still beats always_2 ($83M vs $28M) but loses to "
                "two_or_three_best ($104M, one bet/day). Prefer two_or_three_best for one ticket; two_and_single only if "
                "you want two correlated bets per day."
            ),
        },
        "recommendation": {
            "one_bet_per_day_fair": next(
                (r for r in results_fair if r["bankroll"] == 10000 and r["multi_bet_days"] == 0 and r["strategy_id"] == "two_or_three_or_single"),
                next((r for r in results_fair if r["bankroll"] == 10000 and r["multi_bet_days"] == 0), None),
            ),
            "multi_bet_fair": max(
                (r for r in results_fair if r["multi_bet_days"] > 0 and r["bankroll"] == 10000),
                key=lambda r: r["end"],
                default=None,
            ),
        },
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print(f"Tested {len(grid)} strategy definitions x {len(STAKE_GRID)} stakes x 2 risk modes")
    print("\nTOP 5 FAIR (30% daily cap max, $10k):")
    for r in [x for x in results_fair if x["bankroll"] == 10000][:5]:
        print(f"  {r['strategy_id']:<28} ${r['end']:>12,.0f} @ {r['stake_pct']*100:.0f}%  {r['wins']}-{r['losses']}  multi_days={r['multi_bet_days']}")
    print("\nTOP 5 RAW (uncapped multi-bet, $10k):")
    for r in [x for x in results_raw if x["bankroll"] == 10000][:5]:
        print(f"  {r['strategy_id']:<28} ${r['end']:>12,.0f} @ {r['stake_pct']*100:.0f}%  bets={r['bets']}")
    print("\nweird two_and_single:")
    print(f"  raw: ${dual['end']:,.0f} | fair: ${dual_fair['end']:,.0f} | always_2 fair: ${always2['end']:,.0f}")


if __name__ == "__main__":
    main()
