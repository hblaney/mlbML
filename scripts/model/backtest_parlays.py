"""Backtest single and parlay betting strategies using real historical odds."""

from __future__ import annotations

import itertools
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from daily_auto_model import walk_forward_history
from historical_odds import HistoricalOddsStore
from mlb_api import load_or_fetch_games, load_team_abbreviations
from odds_provider import implied_probability


OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "parlay-backtest.json"
STAKE = 100.0
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


def expected_value(probability: float, american: int, stake: float = STAKE) -> float:
    profit = (decimal_odds(american) - 1) * stake
    return probability * profit - (1 - probability) * stake


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
            if edge <= 0 or ev <= 0:
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
            if item["edge"] >= min_edge and item["model_probability"] >= min_probability
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
            score = settled["ev"] * (settled["probability"] ** 0.5)
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


def main() -> None:
    start = date(2025, 3, 20)
    end = date(2025, 8, 17)
    games = load_or_fetch_games(start, end)
    team_abbr = load_team_abbreviations()
    rows = walk_forward_history(games, team_abbr)
    store = HistoricalOddsStore()
    by_day = build_single_candidates(rows, store)

    strategies = []
    for leg_count in range(1, 9):
        for min_edge in (0.01, 0.02, 0.03, 0.04, 0.05):
            for min_probability in (0.52, 0.54, 0.56, 0.58, 0.60):
                for top_n in (4, 6, 8, 10, 12):
                    if leg_count > top_n:
                        continue
                    strategies.append(evaluate_strategy(by_day, leg_count, min_edge, min_probability, top_n))

    qualified = [row for row in strategies if row["bets"] >= 8]
    qualified.sort(key=lambda item: (item["roi"], item["profit"], item["bets"]), reverse=True)

    best_by_leg = []
    for leg_count in range(1, 9):
        leg_rows = [row for row in qualified if row["leg_count"] == leg_count]
        if leg_rows:
            best_by_leg.append(leg_rows[0])

    recommended_by_leg = [
        row for row in best_by_leg
        if row["roi"] > 0 and row["bets"] >= 20
    ]

    output = {
        "generated_at": date.today().isoformat(),
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "stake": STAKE,
        "historical_games": len(games),
        "model_prediction_rows": len(rows),
        "days_with_candidates": len(by_day),
        "best_overall": qualified[:20],
        "best_by_leg_count": best_by_leg,
        "recommended_by_leg_count": recommended_by_leg,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print(f"historical_games={len(games)}")
    print(f"model_prediction_rows={len(rows)}")
    print(f"days_with_candidates={len(by_day)}")
    for row in best_by_leg:
        print(
            f"legs={row['leg_count']} bets={row['bets']} record={row['wins']}-{row['losses']} "
            f"roi={row['roi']:.4f} profit={row['profit']:.2f} min_edge={row['min_edge']} "
            f"min_prob={row['min_probability']} top_n={row['top_n']}"
        )


if __name__ == "__main__":
    main()
