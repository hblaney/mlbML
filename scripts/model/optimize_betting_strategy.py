"""Sweep singles and 2-4 leg parlays for optimal compound stake sizing by bankroll."""

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
from backtest_parlays import odds_backtest_range
from daily_auto_model import walk_forward_history
from historical_odds import HistoricalOddsStore
from mlb_api import load_or_fetch_games, load_team_abbreviations

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "betting-strategy-optimizer.json"
GAMES_PER_SEASON = 162
STAKE_PCTS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
TIERED_STAKE_PCTS = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
STARTING_BANKROLLS = [0.10, 0.35, 1.0, 10.0, 100.0, 1000.0, 10000.0]


def leg_count_for(bet: dict) -> int:
    legs = bet.get("legs")
    return len(legs) if legs else 1


def compound_flat_pct(bets: list[dict], stake_pct: float, start: float) -> dict:
    bankroll = start
    min_bankroll = start
    for bet in bets:
        stake = bankroll * stake_pct
        bankroll += bet["profit"] * (stake / STAKE)
        min_bankroll = min(min_bankroll, bankroll)
    return {
        "end": round(bankroll, 4),
        "profit": round(bankroll - start, 4),
        "min_bankroll": round(min_bankroll, 4),
        "return_pct": round((bankroll / start - 1) * 100, 2) if start else 0.0,
    }


def compound_tiered(bets: list[dict], stake_map: dict[int, float], start: float) -> dict:
    bankroll = start
    min_bankroll = start
    for bet in bets:
        pct = stake_map.get(leg_count_for(bet), 0.25)
        stake = bankroll * pct
        bankroll += bet["profit"] * (stake / STAKE)
        min_bankroll = min(min_bankroll, bankroll)
    return {
        "end": round(bankroll, 4),
        "profit": round(bankroll - start, 4),
        "min_bankroll": round(min_bankroll, 4),
        "return_pct": round((bankroll / start - 1) * 100, 2) if start else 0.0,
    }


def project_season(bets: list[dict], stake_pct: float, start: float, games_played: float) -> float:
    if not bets or games_played <= 0:
        return start
    extra = int(round(len(bets) * max(GAMES_PER_SEASON - games_played, 0) / games_played))
    total = len(bets) + extra
    bankroll = start
    for index in range(total):
        bet = bets[index % len(bets)]
        bankroll += bet["profit"] * (bankroll * stake_pct / STAKE)
    return round(bankroll, 2)


def project_season_tiered(bets: list[dict], stake_map: dict[int, float], start: float, games_played: float) -> float:
    if not bets or games_played <= 0:
        return start
    extra = int(round(len(bets) * max(GAMES_PER_SEASON - games_played, 0) / games_played))
    total = len(bets) + extra
    bankroll = start
    for index in range(total):
        bet = bets[index % len(bets)]
        pct = stake_map.get(leg_count_for(bet), 0.25)
        bankroll += bet["profit"] * (bankroll * pct / STAKE)
    return round(bankroll, 2)


def best_flat_stake(bets: list[dict], start: float) -> dict:
    best = None
    for stake_pct in STAKE_PCTS:
        result = compound_flat_pct(bets, stake_pct, start)
        candidate = {"stake_pct": stake_pct, **result}
        if best is None or candidate["end"] > best["end"]:
            best = candidate
    return best or {"stake_pct": 0.25, "end": start, "profit": 0.0, "min_bankroll": start, "return_pct": 0.0}


def best_tiered_stake(bets: list[dict], start: float) -> dict:
    leg_counts = sorted({leg_count_for(bet) for bet in bets})
    if not leg_counts:
        return {"stake_map": {}, "end": start, "profit": 0.0, "min_bankroll": start, "return_pct": 0.0}

  # prune grid: use same pct set for each leg count present
    best = None
    for combo in itertools.product(TIERED_STAKE_PCTS, repeat=len(leg_counts)):
        stake_map = dict(zip(leg_counts, combo))
        result = compound_tiered(bets, stake_map, start)
        candidate = {
            "stake_map": {str(key): value for key, value in stake_map.items()},
            **result,
        }
        if best is None or candidate["end"] > best["end"]:
            best = candidate
    return best or {"stake_map": {}, "end": start, "profit": 0.0, "min_bankroll": start, "return_pct": 0.0}


def collect_strategy_bets(moneyline_by_day: dict[str, list[dict]], strategy: str) -> list[dict]:
    bets: list[dict] = []
    for day in sorted(moneyline_by_day):
        candidates = moneyline_by_day[day]
        if strategy == "single":
            pick, qualified = pick_best_moneyline(candidates)
            if pick is None:
                continue
            bets.append(bet_from_moneyline({**pick, "date": day}, qualified))
        elif strategy in {"parlay_2", "parlay_3", "parlay_4"}:
            leg_count = int(strategy.split("_")[1])
            pick, qualified = pick_best_parlay(candidates, leg_count)
            if pick is None:
                continue
            bet = bet_from_parlay(pick, day, leg_count, qualified)
            bets.append(bet)
        elif strategy == "best_ticket":
            pick, qualified = pick_best_daily_ticket(candidates)
            if pick is None:
                continue
            if pick.get("ticket_kind") == "single":
                bet = bet_from_moneyline({**pick, "date": day}, qualified)
            else:
                bet = bet_from_parlay(pick, day, len(pick["legs"]), qualified)
            bet["strategy_key"] = pick.get("ticket_kind", "single")
            bets.append(bet)
        elif strategy == "max_score":
            options: list[tuple[float, dict, bool]] = []
            single, sq = pick_best_moneyline(candidates)
            if single is not None:
                options.append((single["ev"] * single["model_probability"], single, sq))
            for leg_count in (2, 3, 4):
                parlay, pq = pick_best_parlay(candidates, leg_count)
                if parlay is not None:
                    options.append((parlay["score"], parlay, pq))
            if not options:
                continue
            _, ticket, qualified = max(options, key=lambda item: item[0])
            if len(ticket.get("legs", [])) == 0 or "legs" not in ticket:
                bets.append(bet_from_moneyline({**ticket, "date": day}, qualified))
            else:
                bets.append(bet_from_parlay(ticket, day, len(ticket["legs"]), qualified))
    return bets


def main() -> None:
    store = HistoricalOddsStore()
    start, end, odds_metadata = odds_backtest_range(store)
    games = load_or_fetch_games(start, end)
    rows = walk_forward_history(games, load_team_abbreviations())
    moneyline_by_day = build_single_candidates(rows, store)

    season_open = date(start.year, 3, 26)
    season_close = date(start.year, 9, 27)
    season_days = (season_close - season_open).days + 1
    elapsed_days = (end - start).days + 1
    games_played = GAMES_PER_SEASON * elapsed_days / season_days

    strategies = ["single", "parlay_2", "parlay_3", "parlay_4", "best_ticket", "max_score"]
    strategy_bets: dict[str, list[dict]] = {
        name: collect_strategy_bets(moneyline_by_day, name) for name in strategies
    }

    flat_summaries = {}
    for name, bets in strategy_bets.items():
        wins = sum(1 for bet in bets if bet["won"])
        flat_profit = sum(bet["profit"] for bet in bets)
        flat_summaries[name] = {
            "bets": len(bets),
            "wins": wins,
            "losses": len(bets) - wins,
            "flat_profit_per_100": round(flat_profit, 2),
            "flat_roi": round(flat_profit / (len(bets) * STAKE), 4) if bets else 0.0,
            "mix": {},
        }
        mix: dict[str, int] = {}
        for bet in bets:
            key = str(leg_count_for(bet))
            mix[key] = mix.get(key, 0) + 1
        flat_summaries[name]["mix"] = mix

    optimal_by_bankroll: dict[str, dict] = {}
    for bankroll in STARTING_BANKROLLS:
        strategy_results = []
        for name, bets in strategy_bets.items():
            if not bets:
                continue
            best = best_flat_stake(bets, bankroll)
            strategy_results.append(
                {
                    "strategy": name,
                    "optimal_stake_pct": best["stake_pct"],
                    "to_date_end": best["end"],
                    "to_date_profit": best["profit"],
                    "min_bankroll": best["min_bankroll"],
                    "full_season_projection": project_season(bets, best["stake_pct"], bankroll, games_played),
                }
            )
        strategy_results.sort(key=lambda item: item["to_date_end"], reverse=True)
        winner = strategy_results[0] if strategy_results else None

        max_score_bets = strategy_bets["max_score"]
        tiered = best_tiered_stake(max_score_bets, bankroll) if max_score_bets else None
        tiered_projection = None
        if tiered and tiered.get("stake_map"):
            stake_map_int = {int(k): v for k, v in tiered["stake_map"].items()}
            tiered_projection = project_season_tiered(max_score_bets, stake_map_int, bankroll, games_played)

        optimal_by_bankroll[str(bankroll)] = {
            "best_pure_strategy": winner,
            "all_strategies_ranked": strategy_results,
            "best_tiered_max_score": {
                **tiered,
                "full_season_projection": tiered_projection,
            }
            if tiered
            else None,
        }

    global_winner = max(
        (
            (bankroll, data["best_pure_strategy"])
            for bankroll, data in optimal_by_bankroll.items()
            if data.get("best_pure_strategy")
        ),
        key=lambda item: item[1]["to_date_end"] / float(item[0]) if float(item[0]) else 0,
    )

    output = {
        "generated_at": date.today().isoformat(),
        "method": "walk_forward_time_series",
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "odds_metadata": odds_metadata,
        "season_progress_pct": round(games_played / GAMES_PER_SEASON * 100, 1),
        "stake_pct_grid": STAKE_PCTS,
        "starting_bankrolls": STARTING_BANKROLLS,
        "strategies_tested": strategies,
        "flat_summaries": flat_summaries,
        "optimal_by_bankroll": optimal_by_bankroll,
        "recommendation": {
            "primary_strategy": "max_score",
            "description": "Each day bet the highest EV×probability ticket among singles and 2-4 leg premium parlays.",
            "tiered_staking": "Size by leg count using per-bankroll tiered stakes in optimal_by_bankroll.best_tiered_max_score.",
            "notes": [
                "Pure 2-leg only wins for some mid bankrolls but max_score with tiered stakes maximizes most paths.",
                "4-leg tickets are rare and strict; they appear only on premium-confidence slates.",
                "Full-season numbers replay the walk-forward sequence cyclically.",
            ],
        },
    }

    # set recommendation from $10 and $10k winners
    for key in ("10.0", "10000.0"):
        tiered = optimal_by_bankroll.get(key, {}).get("best_tiered_max_score")
        if tiered:
            output["recommendation"][f"tiered_stakes_for_${key.split('.')[0]}"] = tiered.get("stake_map")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print("Strategy flat summaries:")
    for name, summary in flat_summaries.items():
        print(f"  {name}: {summary['bets']} bets {summary['wins']}-{summary['losses']} flat_roi={summary['flat_roi']:.3f}")

    print("\nBest pure strategy by bankroll (to date):")
    for bankroll in STARTING_BANKROLLS:
        best = optimal_by_bankroll[str(bankroll)]["best_pure_strategy"]
        if best:
            print(
                f"  ${bankroll}: {best['strategy']} @ {best['optimal_stake_pct']*100:.0f}% "
                f"-> ${best['to_date_end']:.2f}"
            )


if __name__ == "__main__":
    main()
