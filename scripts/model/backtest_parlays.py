"""Backtest single and parlay betting strategies using real historical odds."""

from __future__ import annotations

import itertools
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from daily_auto_model import walk_forward_history
from historical_odds import HistoricalOddsStore
from mlb_api import load_or_fetch_games, load_team_abbreviations
from odds_provider import implied_probability


OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "parlay-backtest.json"
STAKE = 100.0
SAFE_MIN_LEG_PROBABILITY = 0.60
SAFE_MIN_BOOK_PROBABILITY = 0.50
SAFE_MAX_LEGS = 3
RECOMMENDED_SINGLE_EDGE = 0.05
RECOMMENDED_SINGLE_PROBABILITY = 0.57
RECOMMENDED_SINGLE_MAX_ABS_ODDS = 160
ODDS_ALIASES = {
    "ATH": ["ATH", "OAK"],
    "OAK": ["OAK", "ATH"],
    "AZ": ["AZ", "ARI"],
    "ARI": ["ARI", "AZ"],
    "CWS": ["CWS", "CHW"],
    "CHW": ["CHW", "CWS"],
}


def decimal_odds(american: int) -> float:
    return 1 + american / 100 if american > 0 else 1 + 100 / abs(american)


def american_from_decimal(decimal: float) -> int:
    if decimal >= 2:
        return round((decimal - 1) * 100)
    return round(-100 / (decimal - 1))


def valid_bettable_moneyline(american: int) -> bool:
    return 100 <= abs(american) <= 2000


def expected_value(probability: float, american: int, stake: float = STAKE) -> float:
    profit = (decimal_odds(american) - 1) * stake
    return probability * profit - (1 - probability) * stake


def single_profit(american: int, won: bool) -> float:
    if won:
        return (decimal_odds(american) - 1) * STAKE
    return -STAKE


def odds_for(store: HistoricalOddsStore, game_date: str, away: str, home: str):
    away_options = ODDS_ALIASES.get(away, [away])
    home_options = ODDS_ALIASES.get(home, [home])
    for away_key in away_options:
        for home_key in home_options:
            market = store.for_game(game_date, away_key, home_key)
            if market.source_count > 0 and market.home_moneyline and market.away_moneyline:
                return market
    return None


def build_single_candidates(rows: list[dict], store: HistoricalOddsStore) -> dict[str, list[dict]]:
    by_day: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        market = odds_for(store, row["date"], row["away"], row["home"])
        if market is None:
            continue

        sides = [
            {
                "team": row["home"],
                "side": "home",
                "odds": market.home_moneyline,
                "model_probability": row["probability"],
                "won": row["actual"] == row["home"],
            },
            {
                "team": row["away"],
                "side": "away",
                "odds": market.away_moneyline,
                "model_probability": 1 - row["probability"],
                "won": row["actual"] == row["away"],
            },
        ]

        for side in sides:
            book_probability = implied_probability(side["odds"])
            ev = expected_value(side["model_probability"], side["odds"])
            edge = side["model_probability"] - book_probability
            if not valid_bettable_moneyline(side["odds"]) or edge <= 0 or ev <= 0:
                continue
            by_day[row["date"]].append(
                {
                    **side,
                    "gamePk": row["gamePk"],
                    "matchup": f'{row["away"]} @ {row["home"]}',
                    "book_probability": book_probability,
                    "edge": edge,
                    "ev": ev,
                }
            )

    for day in by_day:
        by_day[day].sort(key=lambda item: (item["ev"], item["edge"], item["model_probability"]), reverse=True)

    return by_day


def all_single_candidates(by_day: dict[str, list[dict]]) -> list[dict]:
    return [candidate for candidates in by_day.values() for candidate in candidates]


def evaluate_single_strategy(candidates: list[dict], min_edge: float, min_probability: float, max_abs_odds: int) -> dict:
    bets = [
        candidate
        for candidate in candidates
        if (
            candidate["edge"] >= min_edge
            and candidate["model_probability"] >= min_probability
            and abs(candidate["odds"]) <= max_abs_odds
        )
    ]
    profit = sum(single_profit(bet["odds"], bet["won"]) for bet in bets)
    wins = sum(1 for bet in bets if bet["won"])
    total_staked = len(bets) * STAKE
    return {
        "min_edge": min_edge,
        "min_probability": min_probability,
        "max_abs_odds": max_abs_odds,
        "bets": len(bets),
        "wins": wins,
        "losses": len(bets) - wins,
        "hit_rate": wins / len(bets) if bets else 0.0,
        "profit": profit,
        "roi": profit / total_staked if total_staked else 0.0,
        "avg_ev": sum(bet["ev"] for bet in bets) / len(bets) if bets else 0.0,
    }


def settle_parlay(legs: list[dict]) -> dict:
    probability = 1.0
    parlay_decimal = 1.0
    won = True

    for leg in legs:
        probability *= leg["model_probability"]
        parlay_decimal *= decimal_odds(leg["odds"])
        won = won and leg["won"]

    payout_profit = (parlay_decimal - 1) * STAKE
    profit = payout_profit if won else -STAKE
    ev = probability * payout_profit - (1 - probability) * STAKE

    return {
        "probability": probability,
        "american_odds": american_from_decimal(parlay_decimal),
        "payout_profit": payout_profit,
        "ev": ev,
        "won": won,
        "profit": profit,
    }


def evaluate_strategy(by_day: dict[str, list[dict]], leg_count: int, min_edge: float, min_probability: float, top_n: int) -> dict:
    bets = []

    for day, candidates in by_day.items():
        filtered = [
            item
            for item in candidates
            if (
                item["edge"] >= min_edge
                and item["model_probability"] >= min_probability
                and item["book_probability"] >= SAFE_MIN_BOOK_PROBABILITY
            )
        ][:top_n]
        if len(filtered) < leg_count:
            continue

        best_ticket = None
        for combo in itertools.combinations(filtered, leg_count):
            if len({leg["gamePk"] for leg in combo}) != leg_count:
                continue
            settled = settle_parlay(list(combo))
            if settled["ev"] <= 0:
                continue
            score = settled["ev"] * settled["probability"]
            candidate = {"date": day, "legs": list(combo), "score": score, **settled}
            if best_ticket is None or candidate["score"] > best_ticket["score"]:
                best_ticket = candidate

        if best_ticket is not None:
            bets.append(best_ticket)

    total_staked = len(bets) * STAKE
    profit = sum(bet["profit"] for bet in bets)
    wins = sum(1 for bet in bets if bet["won"])

    return {
        "leg_count": leg_count,
        "min_edge": min_edge,
        "min_probability": min_probability,
        "top_n": top_n,
        "bets": len(bets),
        "wins": wins,
        "losses": len(bets) - wins,
        "hit_rate": wins / len(bets) if bets else 0.0,
        "profit": profit,
        "roi": profit / total_staked if total_staked else 0.0,
        "avg_model_probability": sum(bet["probability"] for bet in bets) / len(bets) if bets else 0.0,
        "avg_ev": sum(bet["ev"] for bet in bets) / len(bets) if bets else 0.0,
        "sample_tickets": [
            {
                "date": bet["date"],
                "won": bet["won"],
                "profit": round(bet["profit"], 2),
                "probability": round(bet["probability"], 4),
                "american_odds": bet["american_odds"],
                "legs": [
                    {
                        "team": leg["team"],
                        "matchup": leg["matchup"],
                        "odds": leg["odds"],
                        "model_probability": round(leg["model_probability"], 4),
                        "edge": round(leg["edge"], 4),
                    }
                    for leg in bet["legs"]
                ],
            }
            for bet in bets[-8:]
        ],
    }


def season_start_for(year: int) -> date:
    return date(year, 3, 20)


def odds_backtest_range(store: HistoricalOddsStore) -> tuple[date, date, dict]:
    odds_start, odds_end = store.date_range()
    yesterday = date.today() - timedelta(days=1)
    if odds_start is None or odds_end is None:
        end = yesterday
        start = season_start_for(end.year)
        return start, end, {
            "odds_data_start": None,
            "odds_data_end": None,
            "odds_data_stale": True,
            "limited_by": "missing historical odds file",
        }

    latest_odds_date = date.fromisoformat(odds_end)
    end = min(latest_odds_date, yesterday)
    # Use the latest odds-backed season. Older seasons can be imported, but the
    # displayed ROI should represent the most recent available betting market.
    start = season_start_for(end.year)
    return start, end, {
        "odds_data_start": odds_start,
        "odds_data_end": odds_end,
        "odds_data_stale": latest_odds_date < yesterday,
        "limited_by": "historical odds availability" if latest_odds_date < yesterday else "yesterday's final scores",
    }


def main() -> None:
    store = HistoricalOddsStore()
    start, end, odds_metadata = odds_backtest_range(store)
    games = load_or_fetch_games(start, end)
    team_abbr = load_team_abbreviations()
    rows = walk_forward_history(games, team_abbr)
    by_day = build_single_candidates(rows, store)
    single_candidates = all_single_candidates(by_day)

    single_strategies = []
    for min_edge in (0.03, 0.04, 0.05, 0.06, 0.08):
        for min_probability in (0.55, 0.57, 0.60, 0.62, 0.65):
            for max_abs_odds in (140, 160, 180, 220):
                single_strategies.append(
                    evaluate_single_strategy(single_candidates, min_edge, min_probability, max_abs_odds)
                )

    qualified_singles = [row for row in single_strategies if row["bets"] >= 40 and row["roi"] > 0]
    qualified_singles.sort(key=lambda item: (item["roi"], item["profit"], item["bets"]), reverse=True)
    recommended_single = evaluate_single_strategy(
        single_candidates,
        RECOMMENDED_SINGLE_EDGE,
        RECOMMENDED_SINGLE_PROBABILITY,
        RECOMMENDED_SINGLE_MAX_ABS_ODDS,
    )

    strategies = []
    for leg_count in range(2, SAFE_MAX_LEGS + 1):
        for min_edge in (0.01, 0.02, 0.03, 0.04, 0.05):
            for min_probability in (SAFE_MIN_LEG_PROBABILITY, 0.62, 0.65):
                for top_n in (4, 6, 8):
                    if leg_count > top_n:
                        continue
                    strategies.append(evaluate_strategy(by_day, leg_count, min_edge, min_probability, top_n))

    qualified = [row for row in strategies if row["bets"] >= 8]
    qualified.sort(key=lambda item: (item["roi"], item["profit"], item["bets"]), reverse=True)

    best_by_leg = []
    for leg_count in range(2, SAFE_MAX_LEGS + 1):
        leg_rows = [row for row in qualified if row["leg_count"] == leg_count]
        if leg_rows:
            best_by_leg.append(leg_rows[0])

    recommended_by_leg = [
        row for row in best_by_leg
        if row["roi"] > 0 and row["profit"] > 0 and row["avg_ev"] > 0 and row["bets"] >= 12
    ]

    output = {
        "generated_at": date.today().isoformat(),
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "odds_metadata": odds_metadata,
        "stake": STAKE,
        "historical_games": len(games),
        "model_prediction_rows": len(rows),
        "days_with_candidates": len(by_day),
        "best_single_strategies": qualified_singles[:20],
        "recommended_single_strategy": recommended_single,
        "best_overall": qualified[:20],
        "best_by_leg_count": best_by_leg,
        "recommended_by_leg_count": recommended_by_leg,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print(f"historical_games={len(games)}")
    print(f"date_range={start.isoformat()}..{end.isoformat()}")
    print(f"odds_data_end={odds_metadata['odds_data_end']} stale={odds_metadata['odds_data_stale']}")
    print(f"model_prediction_rows={len(rows)}")
    print(f"days_with_candidates={len(by_day)}")
    print(
        f"single bets={recommended_single['bets']} record={recommended_single['wins']}-{recommended_single['losses']} "
        f"roi={recommended_single['roi']:.4f} profit={recommended_single['profit']:.2f} "
        f"min_edge={recommended_single['min_edge']} min_prob={recommended_single['min_probability']} "
        f"max_abs_odds={recommended_single['max_abs_odds']}"
    )
    for row in best_by_leg:
        print(
            f"legs={row['leg_count']} bets={row['bets']} record={row['wins']}-{row['losses']} "
            f"roi={row['roi']:.4f} profit={row['profit']:.2f} min_edge={row['min_edge']} "
            f"min_prob={row['min_probability']} top_n={row['top_n']}"
        )


if __name__ == "__main__":
    main()
