"""Walk-forward backtest of live system tickets + recent ticket ledger."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from backtest_parlays import build_single_candidates, odds_backtest_range
from daily_auto_model import walk_forward_history
from exhaustive_strategy_search import action_to_bet
from feature_registry import FEATURES
from mlb_api import load_or_fetch_games, load_team_abbreviations
from strategy_next_tests import day_actions_for_test, enrich_moneyline

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "best-ticket-walkforward.json"
LIVE_STRATEGY = "trg59_top_prob_2"


def ticket_label(action, day: str) -> str:
    bet = action_to_bet(action, day)
    return bet.get("label") or bet.get("team") or "ticket"


def ticket_legs(action, day: str) -> list[dict]:
    bet = action_to_bet(action, day)
    if bet.get("legs"):
        return [
            {
                "team": leg["team"],
                "matchup": leg.get("matchup", ""),
                "odds": leg.get("odds"),
                "model_probability": round(float(leg.get("model_probability", 0.0)), 4),
                "confidence": leg.get("confidence", "Low"),
                "won": bool(leg.get("won")),
            }
            for leg in bet["legs"]
        ]
    return [
        {
            "team": bet.get("team"),
            "matchup": bet.get("matchup", ""),
            "odds": bet.get("odds"),
            "model_probability": round(float(bet.get("model_probability", 0.0)), 4),
            "confidence": bet.get("confidence", "Low"),
            "won": bool(bet.get("won")),
        }
    ]


def main() -> None:
    store_start = None
    from historical_odds import HistoricalOddsStore

    store = HistoricalOddsStore()
    start, end, odds_metadata = odds_backtest_range(store)
    team_abbr = load_team_abbreviations()
    prior_games = load_or_fetch_games(date(start.year - 1, 3, 20), date(start.year - 1, 10, 5))
    rows = walk_forward_history(load_or_fetch_games(start, end), team_abbr, prior_games=prior_games)
    moneyline_by_day = enrich_moneyline(build_single_candidates(rows, store), rows)

    tickets: list[dict] = []
    wins = losses = 0
    for day in sorted(moneyline_by_day):
        actions = day_actions_for_test(moneyline_by_day[day], LIVE_STRATEGY)
        if not actions:
            continue
        action = actions[0]
        bet = action_to_bet(action, day)
        won = bool(bet.get("won"))
        wins += int(won)
        losses += int(not won)
        tickets.append(
            {
                "date": day,
                "strategy": LIVE_STRATEGY,
                "ticket_type": action.label,
                "label": ticket_label(action, day),
                "leg_count": len(bet.get("legs") or [bet]),
                "legs": ticket_legs(action, day),
                "won": won,
                "result": "HIT" if won else "MISS",
                "flat_profit": round(float(bet.get("profit", 0.0)), 2),
            }
        )

    cutoff = end - timedelta(days=13)
    last_14 = [ticket for ticket in tickets if ticket["date"] >= cutoff.isoformat()]
    last_14_wins = sum(1 for ticket in last_14 if ticket["won"])

    payload = {
        "generated_at": date.today().isoformat(),
        "method": "strict_walk_forward_full_registry",
        "model_version": rows[0]["modelVersion"] if rows else "daily-auto-v3.0-full-registry",
        "feature_count": len(FEATURES),
        "strategy": LIVE_STRATEGY,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "odds_metadata": odds_metadata,
        "game_prediction_accuracy": {
            "games": len(rows),
            "correct": sum(int(row["correct"]) for row in rows),
            "accuracy": round(sum(int(row["correct"]) for row in rows) / len(rows), 4) if rows else 0.0,
        },
        "best_ticket_accuracy": {
            "bet_days": len(tickets),
            "wins": wins,
            "losses": losses,
            "hit_rate": round(wins / len(tickets), 4) if tickets else 0.0,
            "record": f"{wins}-{losses}",
        },
        "last_14_days": {
            "start": cutoff.isoformat(),
            "end": end.isoformat(),
            "bet_days": len(last_14),
            "wins": last_14_wins,
            "losses": len(last_14) - last_14_wins,
            "hit_rate": round(last_14_wins / len(last_14), 4) if last_14 else 0.0,
            "record": f"{last_14_wins}-{len(last_14) - last_14_wins}",
            "tickets": last_14,
        },
        "tickets": tickets,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"wrote={OUTPUT_PATH}")
    print(f"game_accuracy={payload['game_prediction_accuracy']['accuracy']}")
    print(f"ticket_record={payload['best_ticket_accuracy']['record']}")
    print(f"last_14_record={payload['last_14_days']['record']}")


if __name__ == "__main__":
    main()
