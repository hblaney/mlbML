"""Daily board generator with automatic retrain-through-yesterday."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from daily_auto_model import MODEL_VERSION, ensure_trained_through
from mlb_api import fetch_upcoming_games, load_team_abbreviations
from odds_provider import fetch_moneyline_market, market_for_game
from trained_edge_model import blend_with_market, confidence_for, sharpen_public_probability

PUBLIC_PATH = Path(__file__).resolve().parents[2] / "public" / "predictions.json"


def projected_total_for(game, league) -> float:
    home = league.team(game.home_team_id)
    away = league.team(game.away_team_id)
    home_runs = (home.avg_runs_scored(10) + away.avg_runs_allowed(10)) / 2
    away_runs = (away.avg_runs_scored(10) + home.avg_runs_allowed(10)) / 2
    return round(max(5.5, min(13.5, home_runs + away_runs)), 2)


def no_vig_market_probabilities(market_snapshot) -> tuple[float, float] | None:
    total = market_snapshot.home_implied_probability + market_snapshot.away_implied_probability
    if total <= 0:
        return None
    return market_snapshot.home_implied_probability / total, market_snapshot.away_implied_probability / total


def market_aware_probabilities(prediction, market_snapshot, odds_available: bool) -> tuple[float, float, list[str]]:
    notes = list(prediction.notes)
    if not odds_available:
        home_probability = sharpen_public_probability(prediction.home_probability)
        notes.append("Public probability uses the validated gradient-boosting distribution without extra sharpening")
        return home_probability, 1.0 - home_probability, notes

    market_probs = no_vig_market_probabilities(market_snapshot)
    if market_probs is None:
        home_probability = sharpen_public_probability(prediction.home_probability)
        notes.append("Public probability uses the validated gradient-boosting distribution without extra sharpening")
        return home_probability, 1.0 - home_probability, notes

    market_home, market_away = market_probs
    home_probability = blend_with_market(prediction.home_probability, market_home)
    away_probability = blend_with_market(prediction.away_probability, market_away)
    total = home_probability + away_probability
    home_probability /= total
    away_probability /= total
    home_probability = sharpen_public_probability(home_probability)
    away_probability = 1.0 - home_probability
    notes.append("Final probability is anchored to no-vig sportsbook consensus plus the internal model signal")
    notes.append("Public probability uses the validated gradient-boosting distribution without extra sharpening")
    return home_probability, away_probability, notes


def main() -> None:
    today = date.today()
    yesterday = today - timedelta(days=1)
    bundle = ensure_trained_through(yesterday)
    today_games = fetch_upcoming_games(today, today)
    team_abbr = load_team_abbreviations()
    market = fetch_moneyline_market(force_refresh=True)

    board = []
    for game in today_games:
        prediction = bundle.predict(game)
        market_snapshot = market_for_game(game, market)
        odds_available = market_snapshot.source_count > 0 and market_snapshot.home_moneyline != 0 and market_snapshot.away_moneyline != 0
        home_probability, away_probability, notes = market_aware_probabilities(prediction, market_snapshot, odds_available)
        predicted_home = home_probability >= away_probability
        pick_probability = max(home_probability, away_probability)
        internal_agrees = prediction.predicted_home == predicted_home
        home_abbr = team_abbr.get(game.home_team_id, str(game.home_team_id)).lower()
        away_abbr = team_abbr.get(game.away_team_id, str(game.away_team_id)).lower()
        predicted_team = home_abbr if predicted_home else away_abbr
        if odds_available:
            notes.append(f"Market prices from {market_snapshot.source_count} sportsbook source(s)")
        else:
            from odds_provider import get_last_odds_error

            odds_error = get_last_odds_error()
            if odds_error and "OUT_OF_USAGE_CREDITS" in odds_error:
                notes.append("The Odds API quota is exhausted; moneylines will stay empty until credits reset or the plan is upgraded")
            elif odds_error:
                notes.append(f"Live sportsbook odds unavailable: {odds_error}")
            else:
                notes.append("No live sportsbook odds available; EV/best-bet calculations are disabled for this game")

        board.append(
            {
                "id": f"{away_abbr}-{home_abbr}-{game.game_date.isoformat()}-{game.game_pk}",
                "date": game.game_date.isoformat(),
                "startsAt": game.game_datetime_iso,
                "awayTeam": away_abbr,
                "homeTeam": home_abbr,
                "awayPitcher": game.away_pitcher_name or "TBD",
                "homePitcher": game.home_pitcher_name or "TBD",
                "predictedTeam": predicted_team,
                "pickProbability": round(pick_probability, 4),
                "modelHomeWinProbability": round(home_probability, 4),
                "modelAwayWinProbability": round(away_probability, 4),
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
                "confidence": confidence_for(
                    pick_probability,
                    market_backed=odds_available,
                    internal_pick_probability=prediction.pick_probability,
                    internal_agrees=internal_agrees,
                ),
                "modelVersion": MODEL_VERSION,
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
