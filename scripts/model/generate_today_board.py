"""Daily board generator with automatic retrain-through-yesterday."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from daily_auto_model import MODEL_VERSION, ensure_trained_through
from mlb_api import fetch_upcoming_games, load_team_abbreviations
from odds_provider import fetch_moneyline_market, market_for_game
from trained_edge_model import blend_with_market, cap_confidence, confidence_for, sharpen_public_probability

PUBLIC_PATH = Path(__file__).resolve().parents[2] / "public" / "predictions.json"


def _load_previous_pitchers() -> dict[str, tuple[str, str]]:
    if not PUBLIC_PATH.exists():
        return {}
    try:
        payload = json.loads(PUBLIC_PATH.read_text())
    except json.JSONDecodeError:
        return {}
    previous: dict[str, tuple[str, str]] = {}
    for row in payload.get("predictions", []):
        game_id = row.get("id")
        if not game_id:
            continue
        previous[game_id] = (row.get("awayPitcher") or "TBD", row.get("homePitcher") or "TBD")
    return previous


def _starter_certain(game) -> bool:
    away = (game.away_pitcher_name or "").strip()
    home = (game.home_pitcher_name or "").strip()
    return bool(
        game.away_pitcher_id
        and game.home_pitcher_id
        and away
        and home
        and away.upper() != "TBD"
        and home.upper() != "TBD"
    )


def _pitcher_changed(previous: dict[str, tuple[str, str]], game_id: str, away: str, home: str) -> bool:
    prior = previous.get(game_id)
    if not prior:
        return False
    prior_away, prior_home = prior
    return (away and prior_away and away != prior_away) or (home and prior_home and home != prior_home)


def _apply_live_confidence_guards(confidence: str, *, starter_certain: bool, pitcher_changed: bool) -> str:
    if not starter_certain:
        confidence = cap_confidence(confidence, "Medium")
    if pitcher_changed:
        confidence = cap_confidence(confidence, "Medium")
    return confidence


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
    previous_pitchers = _load_previous_pitchers()
    board_generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

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

        game_id = f"{away_abbr}-{home_abbr}-{game.game_date.isoformat()}-{game.game_pk}"
        away_pitcher = game.away_pitcher_name or "TBD"
        home_pitcher = game.home_pitcher_name or "TBD"
        starter_certain = _starter_certain(game)
        pitcher_changed = _pitcher_changed(previous_pitchers, game_id, away_pitcher, home_pitcher)
        raw_confidence = confidence_for(
            pick_probability,
            market_backed=odds_available,
            internal_pick_probability=prediction.pick_probability,
            internal_agrees=internal_agrees,
        )
        live_confidence = _apply_live_confidence_guards(
            raw_confidence,
            starter_certain=starter_certain,
            pitcher_changed=pitcher_changed,
        )
        if not starter_certain:
            notes.append("Probable starter missing on one side — confidence capped at Medium")
        if pitcher_changed:
            notes.append("Probable starter changed since last board refresh — confidence capped at Medium")

        board.append(
            {
                "id": game_id,
                "date": game.game_date.isoformat(),
                "startsAt": game.game_datetime_iso,
                "awayTeam": away_abbr,
                "homeTeam": home_abbr,
                "awayPitcher": away_pitcher,
                "homePitcher": home_pitcher,
                "starterCertain": starter_certain,
                "pitcherChanged": pitcher_changed,
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
                "confidence": live_confidence,
                "modelVersion": MODEL_VERSION,
                "explanation": notes,
            }
        )

    seen_ids: set[str] = set()
    deduped_board: list[dict] = []
    for row in board:
        game_id = row["id"]
        if game_id in seen_ids:
            continue
        seen_ids.add(game_id)
        deduped_board.append(row)
    board = deduped_board
    board.sort(key=lambda row: row["pickProbability"], reverse=True)
    payload = {
        "generated_at": today.isoformat(),
        "board_generated_at": board_generated_at,
        "trained_through": bundle.trained_through.isoformat(),
        "predictions": board,
    }
    PUBLIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_PATH.write_text(json.dumps(payload, indent=2))
    print(f"generated_predictions={len(board)}")
    print(f"trained_through={bundle.trained_through.isoformat()}")


if __name__ == "__main__":
    main()
