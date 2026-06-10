"""Replay daily recommended bets and build a paper-money performance ledger."""

from __future__ import annotations

import itertools
import json
import math
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from backtest_parlays import (
    STAKE,
    build_single_candidates,
    expected_value,
    odds_backtest_range,
    odds_for,
    settle_parlay,
    single_profit,
    valid_bettable_moneyline,
)
from daily_auto_model import walk_forward_history
from historical_odds import HistoricalOddsStore
from mlb_api import load_or_fetch_games, load_team_abbreviations
from odds_provider import implied_probability

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "recommendation-performance.json"
STARTING_BANKROLL = 10_000.0

QUALIFIED_MIN_EDGE = 0.04
QUALIFIED_MIN_PROBABILITY = 0.55
QUALIFIED_MAX_ABS_ODDS = 180
FALLBACK_MIN_EDGE = 0.01
FALLBACK_MAX_ABS_ODDS = 220
PARLAY_QUALIFIED_MIN_EDGE = 0.03
PARLAY_QUALIFIED_MIN_PROBABILITY = 0.55
PARLAY_QUALIFIED_MIN_BOOK = 0.48
PARLAY_TOP_N = 8
TOTAL_MIN_EDGE = 0.015


def sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-value))


def total_probability(projected_total: float, market_total: float) -> float:
    return sigmoid((projected_total - market_total) / 2.1)


def projected_total_for_row(row: dict, market_total: float) -> float:
    home_probability = float(row.get("internalHomeProbability", row.get("probability", 0.5)))
    return market_total + (home_probability - 0.5) * 2.0


def week_key(day: str) -> str:
    parsed = date.fromisoformat(day)
    year, week, _ = parsed.isocalendar()
    return f"{year}-W{week:02d}"


def month_key(day: str) -> str:
    return day[:7]


def summarize_bets(bets: list[dict]) -> dict:
    wins = sum(1 for bet in bets if bet.get("won"))
    losses = len(bets) - wins
    profit = sum(bet.get("profit", 0.0) for bet in bets)
    staked = len(bets) * STAKE
    return {
        "bets": len(bets),
        "wins": wins,
        "losses": losses,
        "staked": round(staked, 2),
        "profit": round(profit, 2),
        "roi": round(profit / staked, 4) if staked else 0.0,
        "hit_rate": round(wins / len(bets), 4) if bets else 0.0,
    }


def serialize_leg(leg: dict) -> dict:
    return {
        "team": leg["team"],
        "matchup": leg["matchup"],
        "odds": leg["odds"],
        "model_probability": round(leg["model_probability"], 4),
        "book_probability": round(leg.get("book_probability", 0.0), 4),
        "edge": round(leg.get("edge", 0.0), 4),
        "won": bool(leg["won"]),
    }


def pick_best_moneyline(candidates: list[dict]) -> tuple[dict | None, bool]:
    qualified = [
        candidate
        for candidate in candidates
        if (
            candidate["edge"] >= QUALIFIED_MIN_EDGE
            and candidate["model_probability"] >= QUALIFIED_MIN_PROBABILITY
            and abs(candidate["odds"]) <= QUALIFIED_MAX_ABS_ODDS
            and candidate["ev"] > 0
        )
    ]
    if qualified:
        return qualified[0], True

    fallback = [
        candidate
        for candidate in candidates
        if candidate["edge"] >= FALLBACK_MIN_EDGE and abs(candidate["odds"]) <= FALLBACK_MAX_ABS_ODDS
    ]
    fallback.sort(key=lambda item: (item["ev"], item["edge"], item["model_probability"]), reverse=True)
    if fallback:
        return fallback[0], False

    if candidates:
        return max(candidates, key=lambda item: (item["ev"], item["edge"])), False
    return None, False


def build_total_candidates(
    rows: list[dict],
    store: HistoricalOddsStore,
    scores_by_pk: dict[int, tuple[int, int]],
) -> dict[str, list[dict]]:
    by_day: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        market = odds_for(store, row["date"], row["away"], row["home"])
        scores = scores_by_pk.get(row["gamePk"])
        if market is None or scores is None:
            continue
        if (
            not market.over_price
            or not market.under_price
            or not market.market_total
            or not valid_bettable_moneyline(market.over_price)
            or not valid_bettable_moneyline(market.under_price)
        ):
            continue

        home_score, away_score = scores
        actual_total = home_score + away_score
        market_total = float(market.market_total)
        projected_total = projected_total_for_row(row, market_total)
        over_model = total_probability(projected_total, market_total)
        under_model = 1 - over_model
        over_book = implied_probability(market.over_price)
        under_book = implied_probability(market.under_price)
        book_total = over_book + under_book
        over_no_vig = over_book / book_total
        under_no_vig = under_book / book_total
        matchup = f'{row["away"]} @ {row["home"]}'

        sides = [
            {
                "team": f"Over {market_total:g}",
                "side": "Total Runs",
                "label": f"Over {market_total:g}",
                "odds": market.over_price,
                "model_probability": over_model,
                "book_probability": over_no_vig,
                "edge": over_model - over_no_vig,
                "ev": expected_value(over_model, market.over_price),
                "won": actual_total > market_total,
                "gamePk": row["gamePk"],
                "matchup": matchup,
            },
            {
                "team": f"Under {market_total:g}",
                "side": "Total Runs",
                "label": f"Under {market_total:g}",
                "odds": market.under_price,
                "model_probability": under_model,
                "book_probability": under_no_vig,
                "edge": under_model - under_no_vig,
                "ev": expected_value(under_model, market.under_price),
                "won": actual_total < market_total,
                "gamePk": row["gamePk"],
                "matchup": matchup,
            },
        ]

        for side in sides:
            if side["edge"] >= TOTAL_MIN_EDGE and side["ev"] > 0:
                by_day[row["date"]].append(side)

    for day in by_day:
        by_day[day].sort(key=lambda item: (item["ev"], item["edge"], item["model_probability"]), reverse=True)

    return by_day


def pick_best_total(candidates: list[dict]) -> tuple[dict | None, bool]:
    if not candidates:
        return None, False
    return candidates[0], candidates[0]["edge"] >= TOTAL_MIN_EDGE and candidates[0]["ev"] > 0


def pick_best_parlay(candidates: list[dict], leg_count: int) -> tuple[dict | None, bool]:
    qualified = [
        candidate
        for candidate in candidates
        if (
            candidate["edge"] >= PARLAY_QUALIFIED_MIN_EDGE
            and candidate["model_probability"] >= PARLAY_QUALIFIED_MIN_PROBABILITY
            and candidate["book_probability"] >= PARLAY_QUALIFIED_MIN_BOOK
            and candidate["ev"] > 0
        )
    ][:PARLAY_TOP_N]

    pools = [qualified]
    if len(qualified) < leg_count:
        fallback = [
            candidate
            for candidate in candidates
            if candidate["ev"] > 0 and candidate["edge"] >= FALLBACK_MIN_EDGE
        ][:PARLAY_TOP_N]
        pools.append(fallback)

    for index, pool in enumerate(pools):
        if len(pool) < leg_count:
            continue

        best_ticket = None
        for combo in itertools.combinations(pool, leg_count):
            if len({leg["gamePk"] for leg in combo}) != leg_count:
                continue
            settled = settle_parlay(list(combo))
            score = settled["ev"] * settled["probability"]
            ticket = {"legs": list(combo), "score": score, **settled}
            if best_ticket is None or ticket["score"] > best_ticket["score"]:
                best_ticket = ticket

        if best_ticket is not None:
            return best_ticket, index == 0

    return None, False


def bet_from_moneyline(candidate: dict, qualified: bool) -> dict:
    profit = single_profit(candidate["odds"], candidate["won"])
    return {
        "category": "moneyline",
        "date": candidate.get("date"),
        "gamePk": candidate["gamePk"],
        "matchup": candidate["matchup"],
        "team": candidate["team"],
        "side": "Moneyline",
        "label": f'{candidate["team"]} ML',
        "odds": candidate["odds"],
        "model_probability": round(candidate["model_probability"], 4),
        "book_probability": round(candidate["book_probability"], 4),
        "edge": round(candidate["edge"], 4),
        "ev": round(candidate["ev"], 2),
        "stake": STAKE,
        "qualified": qualified,
        "won": bool(candidate["won"]),
        "profit": round(profit, 2),
    }


def bet_from_total(candidate: dict, day: str, qualified: bool) -> dict:
    profit = single_profit(candidate["odds"], candidate["won"])
    return {
        "category": "advanced",
        "date": day,
        "gamePk": candidate["gamePk"],
        "matchup": candidate["matchup"],
        "team": candidate["team"],
        "side": candidate["side"],
        "label": candidate["label"],
        "odds": candidate["odds"],
        "model_probability": round(candidate["model_probability"], 4),
        "book_probability": round(candidate["book_probability"], 4),
        "edge": round(candidate["edge"], 4),
        "ev": round(candidate["ev"], 2),
        "stake": STAKE,
        "qualified": qualified,
        "won": bool(candidate["won"]),
        "profit": round(profit, 2),
    }


def bet_from_parlay(ticket: dict, day: str, leg_count: int, qualified: bool) -> dict:
    return {
        "category": f"parlay_{leg_count}",
        "date": day,
        "matchup": " + ".join(leg["matchup"] for leg in ticket["legs"]),
        "team": f"{leg_count}-leg Parlay",
        "side": "Parlay",
        "label": " + ".join(f'{leg["team"]} ML' for leg in ticket["legs"]),
        "odds": ticket["american_odds"],
        "model_probability": round(ticket["probability"], 4),
        "book_probability": None,
        "edge": None,
        "ev": round(ticket["ev"], 2),
        "stake": STAKE,
        "qualified": qualified,
        "won": bool(ticket["won"]),
        "profit": round(ticket["profit"], 2),
        "legs": [serialize_leg(leg) for leg in ticket["legs"]],
    }


def main() -> None:
    store = HistoricalOddsStore()
    start, end, odds_metadata = odds_backtest_range(store)
    games = load_or_fetch_games(start, end)
    team_abbr = load_team_abbreviations()
    rows = walk_forward_history(games, team_abbr)
    scores_by_pk = {
        game.game_pk: (game.home_score, game.away_score)
        for game in games
        if game.home_score is not None and game.away_score is not None
    }

    moneyline_by_day = build_single_candidates(rows, store)
    totals_by_day = build_total_candidates(rows, store, scores_by_pk)
    all_days = sorted(set(moneyline_by_day) | set(totals_by_day))

    daily_snapshots: list[dict] = []
    category_bets: dict[str, list[dict]] = defaultdict(list)

    for day in all_days:
        day_bets: list[dict] = []

        moneyline_candidates = moneyline_by_day.get(day, [])
        moneyline_pick, moneyline_qualified = pick_best_moneyline(moneyline_candidates)
        if moneyline_pick is not None:
            moneyline_pick = {**moneyline_pick, "date": day}
            bet = bet_from_moneyline(moneyline_pick, moneyline_qualified)
            day_bets.append(bet)
            category_bets["moneyline"].append(bet)

        total_candidates = totals_by_day.get(day, [])
        total_pick, total_qualified = pick_best_total(total_candidates)
        if total_pick is not None:
            bet = bet_from_total(total_pick, day, total_qualified)
            day_bets.append(bet)
            category_bets["advanced"].append(bet)

        for leg_count in (3, 4):
            parlay_pick, parlay_qualified = pick_best_parlay(moneyline_candidates, leg_count)
            if parlay_pick is not None:
                bet = bet_from_parlay(parlay_pick, day, leg_count, parlay_qualified)
                day_bets.append(bet)
                category_bets[f"parlay_{leg_count}"].append(bet)

        if day_bets:
            daily_snapshots.append(
                {
                    "date": day,
                    "bets": day_bets,
                    "summary": summarize_bets(day_bets),
                }
            )

    all_bets = [bet for snapshot in daily_snapshots for bet in snapshot["bets"]]
    weekly: dict[str, dict] = {}
    monthly: dict[str, dict] = {}

    for bet in all_bets:
        week = week_key(bet["date"])
        month = month_key(bet["date"])
        weekly.setdefault(week, []).append(bet)
        monthly.setdefault(month, []).append(bet)

    weekly_summary = {key: summarize_bets(value) for key, value in sorted(weekly.items())}
    monthly_summary = {key: summarize_bets(value) for key, value in sorted(monthly.items())}

    running_balance = STARTING_BANKROLL
    checkpoints: list[dict] = []
    for snapshot in daily_snapshots:
        day_profit = sum(bet["profit"] for bet in snapshot["bets"])
        running_balance += day_profit
        checkpoints.append(
            {
                "date": snapshot["date"],
                "profit": round(day_profit, 2),
                "balance": round(running_balance, 2),
                "return_pct": round((running_balance - STARTING_BANKROLL) / STARTING_BANKROLL, 4),
            }
        )

    cumulative_profit = sum(bet["profit"] for bet in all_bets)
    cumulative_staked = len(all_bets) * STAKE

    output = {
        "generated_at": date.today().isoformat(),
        "stake": STAKE,
        "starting_bankroll": STARTING_BANKROLL,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "odds_metadata": odds_metadata,
        "strategy": {
            "moneyline": {
                "qualified_min_edge": QUALIFIED_MIN_EDGE,
                "qualified_min_probability": QUALIFIED_MIN_PROBABILITY,
                "qualified_max_abs_odds": QUALIFIED_MAX_ABS_ODDS,
                "fallback_min_edge": FALLBACK_MIN_EDGE,
            },
            "advanced": {"market": "totals", "min_edge": TOTAL_MIN_EDGE},
            "parlay": {
                "leg_counts": [3, 4],
                "qualified_min_edge": PARLAY_QUALIFIED_MIN_EDGE,
                "qualified_min_probability": PARLAY_QUALIFIED_MIN_PROBABILITY,
                "qualified_min_book_probability": PARLAY_QUALIFIED_MIN_BOOK,
                "top_n": PARLAY_TOP_N,
            },
        },
        "by_category": {
            key: summarize_bets(value)
            for key, value in sorted(category_bets.items())
        },
        "weekly": weekly_summary,
        "monthly": monthly_summary,
        "cumulative": {
            "bets": len(all_bets),
            "profit": round(cumulative_profit, 2),
            "roi": round(cumulative_profit / cumulative_staked, 4) if cumulative_staked else 0.0,
            "balance": round(STARTING_BANKROLL + cumulative_profit, 2),
            "return_pct": round(cumulative_profit / STARTING_BANKROLL, 4) if STARTING_BANKROLL else 0.0,
        },
        "checkpoints": checkpoints[-60:],
        "daily": daily_snapshots,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print(f"daily_snapshots={len(daily_snapshots)}")
    print(f"total_bets={len(all_bets)} cumulative_profit={cumulative_profit:.2f}")
    for category, summary in output["by_category"].items():
        print(
            f"{category} bets={summary['bets']} record={summary['wins']}-{summary['losses']} "
            f"roi={summary['roi']:.4f} profit={summary['profit']:.2f}"
        )


if __name__ == "__main__":
    main()
