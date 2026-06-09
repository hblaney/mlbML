"""Daily board generator with automatic retrain-through-yesterday."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from daily_auto_model import ensure_trained_through
from mlb_api import fetch_upcoming_games, load_team_abbreviations
from odds_provider import fetch_moneyline_market, market_for_game

PUBLIC_PATH = Path(__file__).resolve().parents[2] / "public" / "predictions.json"


def projected_total_for(game, league) -> float:
    home = league.team(game.home_team_id)
    away = league.team(game.away_team_id)
    home_runs = (home.avg_runs_scored(10) + away.avg_runs_allowed(10)) / 2
    away_runs = (away.avg_runs_scored(10) + home.avg_runs_allowed(10)) / 2
    return round(max(5.5, min(13.5, home_runs + away_runs)), 2)


def main() -> None:
    today = date.today()
    yesterday = today - timedelta(days=1)
    bundle = ensure_trained_through(yesterday)
    today_games = fetch_upcoming_games(today, today)
    team_abbr = load_team_abbreviations()
    market = fetch_moneyline_market()

    board = []
    for game in today_games:
        prediction = bundle.predict(game)
        market_snapshot = market_for_game(game, market)
        odds_available = market_snapshot.source_count > 0 and market_snapshot.home_moneyline != 0 and market_snapshot.away_moneyline != 0
        home_abbr = team_abbr.get(game.home_team_id, str(game.home_team_id)).lower()
        away_abbr = team_abbr.get(game.away_team_id, str(game.away_team_id)).lower()
        predicted_team = home_abbr if prediction.predicted_home else away_abbr
        notes = list(prediction.notes)
        if odds_available:
            notes.append(f"Market prices from {market_snapshot.source_count} sportsbook source(s)")
        else:
            notes.append("No live sportsbook odds available; EV/best-bet calculations are disabled for this game")

        board.append(
            {
                "id": f"{away_abbr}-{home_abbr}-{game.game_date.isoformat()}-{game.game_pk}",
                "date": game.game_date.isoformat(),
                "startsAt": game.game_datetime_iso,
                "awayTeam": away_abbr,
                "homeTeam": home_abbr,
                "awayPitcher": "TBD",
                "homePitcher": "TBD",
                "predictedTeam": predicted_team,
                "pickProbability": round(prediction.pick_probability, 4),
                "modelHomeWinProbability": round(prediction.home_probability, 4),
                "modelAwayWinProbability": round(prediction.away_probability, 4),
                "homeMoneyline": market_snapshot.home_moneyline if odds_available else None,
                "awayMoneyline": market_snapshot.away_moneyline if odds_available else None,
                "homeRunline": market_snapshot.home_runline if odds_available and market_snapshot.home_runline_price else None,
                "awayRunline": market_snapshot.away_runline if odds_available and market_snapshot.away_runline_price else None,
                "homeRunlinePrice": market_snapshot.home_runline_price if odds_available and market_snapshot.home_runline_price else None,
                "awayRunlinePrice": market_snapshot.away_runline_price if odds_available and market_snapshot.away_runline_price else None,
                "marketTotal": market_snapshot.market_total if odds_available and market_snapshot.over_price and market_snapshot.under_price else None,
                "overPrice": market_snapshot.over_price if odds_available and market_snapshot.over_price else None,
                "underPrice": market_snapshot.under_price if odds_available and market_snapshot.under_price else None,
                "projectedTotal": projected_total_for(game, bundle.league),
                "oddsSource": "The Odds API" if odds_available else None,
                "confidence": prediction.confidence,
                "modelVersion": "daily-auto-v0.5",
                "explanation": notes,
            }
        )

    board.sort(key=lambda row: row["pickProbability"], reverse=True)
    payload = {
        "generated_at": today.isoformat(),
        "trained_through": bundle.trained_through.isoformat(),
        "predictions": board,
    }
    PUBLIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_PATH.write_text(json.dumps(payload, indent=2))
    print(f"generated_predictions={len(board)}")
    print(f"trained_through={bundle.trained_through.isoformat()}")


if __name__ == "__main__":
    main()
