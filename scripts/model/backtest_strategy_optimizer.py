"""Strict walk-forward strategy comparison — actual days only, no cyclic projection."""

from __future__ import annotations

import itertools
import json
from datetime import date
from pathlib import Path

from backtest_daily_recommendations import (
    STAKE,
    bet_from_moneyline,
    bet_from_parlay,
    build_single_candidates,
    pick_best_daily_ticket,
    pick_best_moneyline,
    pick_best_parlay,
)
from backtest_parlays import odds_backtest_range, settle_parlay
from daily_auto_model import walk_forward_history
from historical_odds import HistoricalOddsStore
from mlb_api import load_or_fetch_games, load_team_abbreviations

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "strategy-backtest-results.json"
STAKE_PCTS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
BANKROLLS = [0.35, 10.0, 10_000.0]


def leg_score(leg: dict) -> float:
    return leg["ev"] * leg["model_probability"]


def positive_ev_legs(candidates: list[dict]) -> list[dict]:
    return sorted(
        [c for c in candidates if c.get("is_model_pick", True) and c["ev"] > 0],
        key=lambda leg: (leg_score(leg), leg["ev"], leg["model_probability"]),
        reverse=True,
    )


def pick_forced_top_legs(candidates: list[dict], leg_count: int) -> dict | None:
    """Top N individual legs by score (one per game), positive EV."""
    legs: list[dict] = []
    seen_games: set[int] = set()
    for leg in positive_ev_legs(candidates):
        if leg["gamePk"] in seen_games:
            continue
        legs.append(leg)
        seen_games.add(leg["gamePk"])
        if len(legs) == leg_count:
            break
    if len(legs) < leg_count:
        return None
    settled = settle_parlay(legs)
    return {"legs": legs, "score": leg_score_for_parlay(legs), "strategy": f"forced_top_{leg_count}", **settled}


def leg_score_for_parlay(legs: list[dict]) -> float:
    settled = settle_parlay(legs)
    return settled["ev"] * settled["probability"]


def pick_best_combo(candidates: list[dict], leg_count: int, min_edge: float = 0.0, min_prob: float = 0.0) -> dict | None:
    """Best N-leg combo by parlay EV×prob from pool clearing thresholds."""
    pool = [
        c
        for c in candidates
        if c["ev"] > 0 and c["edge"] >= min_edge and c["model_probability"] >= min_prob
    ]
    pool.sort(key=leg_score, reverse=True)
    pool = pool[:8]
    if len(pool) < leg_count:
        return None

    best = None
    for combo in itertools.combinations(pool, leg_count):
        if len({leg["gamePk"] for leg in combo}) != leg_count:
            continue
        settled = settle_parlay(list(combo))
        if settled["ev"] <= 0:
            continue
        score = settled["ev"] * settled["probability"]
        ticket = {"legs": list(combo), "score": score, "strategy": f"best_combo_{leg_count}", **settled}
        if best is None or ticket["score"] > best["score"]:
            best = ticket
    return best


def pick_always_leg_count(candidates: list[dict], leg_count: int) -> dict | None:
    """Always bet N legs when possible: filtered combo first, else forced top N."""
    ticket = pick_best_parlay(candidates, leg_count)[0]
    if ticket is not None:
        return ticket
    return pick_forced_top_legs(candidates, leg_count)


def collect_day_ticket(candidates: list[dict], mode: str) -> dict | None:
    if mode == "single":
        pick, _ = pick_best_moneyline(candidates)
        return pick
    if mode == "best_ticket":
        pick, _ = pick_best_daily_ticket(candidates)
        return pick
    if mode in {"parlay_2", "parlay_3", "parlay_4"}:
        n = int(mode.split("_")[1])
        pick, _ = pick_best_parlay(candidates, n)
        return pick
    if mode in {"forced_top_2", "forced_top_3", "forced_top_4"}:
        n = int(mode.split("_")[-1])
        return pick_forced_top_legs(candidates, n)
    if mode in {"best_combo_2", "best_combo_3", "best_combo_4"}:
        n = int(mode.split("_")[-1])
        return pick_best_combo(candidates, n, min_edge=0.0, min_prob=0.0)
    if mode in {"always_2", "always_3", "always_4"}:
        n = int(mode[-1])
        return pick_always_leg_count(candidates, n)
    if mode == "max_score_any":
        options: list[tuple[float, dict]] = []
        single, _ = pick_best_moneyline(candidates)
        if single is not None:
            options.append((leg_score(single), single))
        for n in (2, 3, 4):
            for fn in (
                lambda c, n=n: pick_best_parlay(c, n)[0],
                lambda c, n=n: pick_best_combo(c, n),
                lambda c, n=n: pick_forced_top_legs(c, n),
            ):
                ticket = fn(candidates)
                if ticket is not None:
                    options.append((ticket.get("score", leg_score_for_parlay(ticket["legs"])), ticket))
        if not options:
            return None
        return max(options, key=lambda item: item[0])[1]
    raise ValueError(mode)


def build_bet_sequence(moneyline_by_day: dict[str, list[dict]], mode: str) -> list[dict]:
    bets: list[dict] = []
    for day in sorted(moneyline_by_day):
        candidates = moneyline_by_day[day]
        ticket = collect_day_ticket(candidates, mode)
        if ticket is None:
            continue
        if "legs" in ticket and ticket["legs"]:
            bets.append(bet_from_parlay(ticket, day, len(ticket["legs"]), True))
        else:
            bets.append(bet_from_moneyline({**ticket, "date": day}, True))
    return bets


def compound_actual(bets: list[dict], stake_pct: float, start: float) -> dict:
    bankroll = start
    min_bankroll = start
    curve: list[dict] = []
    for bet in bets:
        stake = bankroll * stake_pct
        pnl = bet["profit"] * (stake / STAKE)
        bankroll += pnl
        min_bankroll = min(min_bankroll, bankroll)
        curve.append(
            {
                "date": bet["date"],
                "bankroll": round(bankroll, 4),
                "won": bet["won"],
                "label": bet.get("label", bet.get("team", "")),
            }
        )
    return {
        "start": start,
        "end": round(bankroll, 4),
        "profit": round(bankroll - start, 4),
        "return_pct": round((bankroll / start - 1) * 100, 2) if start else 0.0,
        "min_bankroll": round(min_bankroll, 4),
        "bets": len(bets),
        "wins": sum(1 for b in bets if b["won"]),
        "losses": sum(1 for b in bets if not b["won"]),
        "curve": curve,
    }


def best_stake_for_bets(bets: list[dict], start: float) -> dict:
    best = None
    for pct in STAKE_PCTS:
        result = compound_actual(bets, pct, start)
        row = {"stake_pct": pct, **result}
        if best is None or row["end"] > best["end"]:
            best = row
    return best or compound_actual(bets, 0.25, start)


def flat_summary(bets: list[dict]) -> dict:
    if not bets:
        return {"bets": 0, "wins": 0, "losses": 0, "flat_profit": 0.0, "flat_roi": 0.0}
    wins = sum(1 for b in bets if b["won"])
    profit = sum(b["profit"] for b in bets)
    return {
        "bets": len(bets),
        "wins": wins,
        "losses": len(bets) - wins,
        "flat_profit": round(profit, 2),
        "flat_roi": round(profit / (len(bets) * STAKE), 4),
        "hit_rate": round(wins / len(bets), 4),
    }


def main() -> None:
    store = HistoricalOddsStore()
    start, end, odds_metadata = odds_backtest_range(store)
    rows = walk_forward_history(load_or_fetch_games(start, end), load_team_abbreviations())
    moneyline_by_day = build_single_candidates(rows, store)

    modes = [
        "single",
        "best_ticket",
        "parlay_2",
        "parlay_3",
        "parlay_4",
        "forced_top_2",
        "forced_top_3",
        "forced_top_4",
        "best_combo_2",
        "best_combo_3",
        "best_combo_4",
        "always_2",
        "always_3",
        "always_4",
        "max_score_any",
    ]

    sequences = {mode: build_bet_sequence(moneyline_by_day, mode) for mode in modes}
    flat = {mode: flat_summary(bets) for mode, bets in sequences.items()}

    compound_results: dict[str, dict] = {}
    winners_by_bankroll: dict[str, dict] = {}

    for bankroll in BANKROLLS:
        ranked = []
        for mode, bets in sequences.items():
            if not bets:
                continue
            best = best_stake_for_bets(bets, bankroll)
            compound_results[f"{mode}@{bankroll}"] = best
            ranked.append(
                {
                    "mode": mode,
                    "optimal_stake_pct": best["stake_pct"],
                    "end_bankroll": best["end"],
                    "profit": best["profit"],
                    "min_bankroll": best["min_bankroll"],
                    "bets": best["bets"],
                    "record": f"{best['wins']}-{best['losses']}",
                }
            )
        ranked.sort(key=lambda row: row["end_bankroll"], reverse=True)
        winners_by_bankroll[str(bankroll)] = ranked

    # Global winner at $10k (primary reference)
    winner = winners_by_bankroll["10000.0"][0]
    winner_mode = winner["mode"]
    winner_bets = sequences[winner_mode]

    # Is current best_ticket profitable?
    bt = flat["best_ticket"]
    bt_compound = compound_results["best_ticket@10000.0"]

    output = {
        "generated_at": date.today().isoformat(),
        "method": "strict_walk_forward_time_series",
        "note": "Only actual days backtested. No cyclic full-season projection.",
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "odds_metadata": odds_metadata,
        "game_days_with_odds": len(moneyline_by_day),
        "flat_by_mode": flat,
        "winners_by_bankroll": winners_by_bankroll,
        "best_ticket_validation": {
            "profitable_flat": bt["flat_profit"] > 0,
            "flat_roi": bt["flat_roi"],
            "record": f"{bt['wins']}-{bt['losses']}",
            "compound_10k_at_30pct": compound_actual(sequences["best_ticket"], 0.30, 10_000),
            "compound_10k_optimal": bt_compound,
        },
        "recommended_mode": winner_mode,
        "recommended_stake_pct": winner["optimal_stake_pct"],
        "recommended_summary": winner,
        "winner_ledger_sample": winner_bets[-10:],
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print("STRICT WALK-FORWARD ONLY", start, "to", end)
    print(f"Best Ticket: flat ${bt['flat_profit']:.0f} ROI {bt['flat_roi']*100:.1f}% | compound $10k -> ${bt_compound['end']:,.0f} @ {bt_compound['stake_pct']*100:.0f}%")
    print("\nTop 5 strategies @ $10,000 (actual backtest compound):")
    for row in winners_by_bankroll["10000.0"][:5]:
        print(
            f"  {row['mode']:<16} {row['record']} {row['bets']} bets @ {row['optimal_stake_pct']*100:.0f}% "
            f"-> ${row['end_bankroll']:,.0f} (min ${row['min_bankroll']:,.0f})"
        )
    print(f"\nRECOMMENDED: {winner_mode} @ {winner['optimal_stake_pct']*100:.0f}%")


if __name__ == "__main__":
    main()
