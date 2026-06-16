"""Walk-forward 2-leg parlay ledger with compound bankroll projections."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from backtest_daily_recommendations import (
    STAKE,
    bet_from_parlay,
    build_single_candidates,
    pick_best_parlay,
)
from backtest_parlays import odds_backtest_range
from daily_auto_model import walk_forward_history
from historical_odds import HistoricalOddsStore
from mlb_api import load_or_fetch_games, load_team_abbreviations

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "parlay2-compound-backtest.json"
GAMES_PER_SEASON = 162
RECOMMENDED_STAKE_PCT = 0.30
COMPOUND_STARTS = (10.0, 10_000.0)


def compound_bankroll(bets: list[dict], stake_pct: float, start: float) -> dict:
    bankroll = start
    min_bankroll = start
    peak = start
    curve: list[dict] = []

    for bet in bets:
        stake = bankroll * stake_pct
        if stake <= 0:
            continue
        pnl = bet["profit"] * (stake / STAKE)
        bankroll += pnl
        min_bankroll = min(min_bankroll, bankroll)
        peak = max(peak, bankroll)
        curve.append(
            {
                "date": bet["date"],
                "stake": round(stake, 4),
                "pnl": round(pnl, 4),
                "bankroll": round(bankroll, 4),
                "won": bet["won"],
            }
        )

    return {
        "start": start,
        "end": round(bankroll, 2),
        "profit": round(bankroll - start, 2),
        "return_pct": round((bankroll / start - 1) * 100, 1) if start else 0.0,
        "min_bankroll": round(min_bankroll, 2),
        "peak_bankroll": round(peak, 2),
        "curve": curve,
    }


def project_full_season(bets: list[dict], stake_pct: float, start: float, games_played: float) -> dict:
    if not bets or games_played <= 0:
        return {"estimated_total_bets": len(bets), "end": start, "note": "No bets to project."}

    games_remaining = max(GAMES_PER_SEASON - games_played, 0)
    extra_bets = int(round(len(bets) * (games_remaining / games_played)))
    total_bets = len(bets) + extra_bets

    bankroll = start
    for index in range(total_bets):
        bet = bets[index % len(bets)]
        stake = bankroll * stake_pct
        bankroll += bet["profit"] * (stake / STAKE)

    return {
        "estimated_total_bets": total_bets,
        "estimated_season_progress_pct": round(games_played / GAMES_PER_SEASON * 100, 1),
        "end": round(bankroll, 2),
        "profit": round(bankroll - start, 2),
        "return_pct": round((bankroll / start - 1) * 100, 1) if start else 0.0,
        "note": "Projection replays the same walk-forward bet sequence cyclically through an estimated full season.",
    }


def main() -> None:
    store = HistoricalOddsStore()
    start, end, odds_metadata = odds_backtest_range(store)
    games = load_or_fetch_games(start, end)
    rows = walk_forward_history(games, load_team_abbreviations())
    moneyline_by_day = build_single_candidates(rows, store)

    bets: list[dict] = []
    for day in sorted(moneyline_by_day):
        pick, qualified = pick_best_parlay(moneyline_by_day[day], 2)
        if pick is None:
            continue
        bets.append(bet_from_parlay(pick, day, 2, qualified))

    flat_profit = sum(bet["profit"] for bet in bets)
    wins = sum(1 for bet in bets if bet["won"])
    season_open = date(start.year, 3, 26)
    season_close = date(start.year, 9, 27)
    season_days = (season_close - season_open).days + 1
    elapsed_days = (end - start).days + 1
    games_played = GAMES_PER_SEASON * elapsed_days / season_days

    by_strategy: dict[str, dict] = {}
    for strategy in {"edge", "anchor"}:
        subset = [bet for bet in bets if bet.get("strategy") == strategy]
        if not subset:
            continue
        subset_wins = sum(1 for bet in subset if bet["won"])
        by_strategy[strategy] = {
            "bets": len(subset),
            "wins": subset_wins,
            "losses": len(subset) - subset_wins,
            "flat_profit": round(sum(bet["profit"] for bet in subset), 2),
        }

    compound_scenarios = []
    for stake_pct in (0.25, 0.30, 0.40):
        for bankroll_start in COMPOUND_STARTS:
            actual = compound_bankroll(bets, stake_pct, bankroll_start)
            projected = project_full_season(bets, stake_pct, bankroll_start, games_played)
            compound_scenarios.append(
                {
                    "stake_pct": stake_pct,
                    "starting_bankroll": bankroll_start,
                    "to_date": {
                        "bets": len(bets),
                        "end": actual["end"],
                        "profit": actual["profit"],
                        "return_pct": actual["return_pct"],
                        "min_bankroll": actual["min_bankroll"],
                    },
                    "full_season_projection": projected,
                }
            )

    output = {
        "generated_at": date.today().isoformat(),
        "method": "walk_forward_time_series",
        "strategy": "best_2_leg_parlay_per_qualifying_day",
        "recommended_stake_pct": RECOMMENDED_STAKE_PCT,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "odds_metadata": odds_metadata,
        "criteria": {
            "edge_leg_min_edge": 0.05,
            "edge_leg_min_model_probability": 0.65,
            "edge_leg_min_book_probability": 0.50,
            "edge_leg_positive_ev": True,
            "anchor_leg_confidence": ["High", "Elite"],
            "anchor_leg_min_model_probability": 0.645,
            "anchor_leg_min_book_probability": 0.50,
            "anchor_leg_min_ev": -2.0,
            "ticket_must_have_positive_ev": True,
            "legs_must_be_different_games": True,
            "selection_score": "expected_value * model_probability",
        },
        "coverage": {
            "game_days_with_candidates": len(moneyline_by_day),
            "qualifying_parlay_days": len(bets),
            "qualifying_rate": round(len(bets) / len(moneyline_by_day), 4) if moneyline_by_day else 0.0,
            "estimated_season_games_played": round(games_played, 1),
            "estimated_season_progress_pct": round(games_played / GAMES_PER_SEASON * 100, 1),
        },
        "flat_stake": STAKE,
        "flat_summary": {
            "bets": len(bets),
            "wins": wins,
            "losses": len(bets) - wins,
            "profit": round(flat_profit, 2),
            "roi": round(flat_profit / (len(bets) * STAKE), 4) if bets else 0.0,
            "hit_rate": round(wins / len(bets), 4) if bets else 0.0,
        },
        "by_strategy": by_strategy,
        "compound_scenarios": compound_scenarios,
        "bets": bets,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print(f"parlay2_days={len(bets)} flat_profit={flat_profit:.2f}")
    for scenario in compound_scenarios:
        if scenario["starting_bankroll"] == 10 and scenario["stake_pct"] == RECOMMENDED_STAKE_PCT:
            print(
                f"$10 compound to_date={scenario['to_date']['end']:.2f} "
                f"projected={scenario['full_season_projection']['end']:.2f}"
            )


if __name__ == "__main__":
    main()
