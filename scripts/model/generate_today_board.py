"""Daily board generator with automatic retrain-through-yesterday."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from daily_auto_model import MODEL_VERSION, PIPELINE_VERSION, ensure_trained_through
from mlb_api import fetch_upcoming_games, load_team_abbreviations
from odds_provider import fetch_moneyline_market, market_for_game
from trained_edge_model import final_public_probabilities

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


def projected_total_for(game, league) -> float:
    home = league.team(game.home_team_id)
    away = league.team(game.away_team_id)
    home_runs = (home.avg_runs_scored(10) + away.avg_runs_allowed(10)) / 2
    away_runs = (away.avg_runs_scored(10) + home.avg_runs_allowed(10)) / 2
    return round(max(5.5, min(13.5, home_runs + away_runs)), 2)


def main() -> None:
    today = date.today()
    yesterday = today - timedelta(days=1)
    bundle, retrained = ensure_trained_through(yesterday)
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
        market_probs = None
        if odds_available:
            total = market_snapshot.home_implied_probability + market_snapshot.away_implied_probability
            if total > 0:
                market_probs = (
                    market_snapshot.home_implied_probability / total,
                    market_snapshot.away_implied_probability / total,
                )

        home_probability, away_probability, pick_probability, live_confidence = final_public_probabilities(
            prediction,
            market_home=market_probs[0] if market_probs else None,
            market_away=market_probs[1] if market_probs else None,
        )
        predicted_home = home_probability >= away_probability
        notes = list(prediction.notes)
        notes.append(
            "Unified model output: GBM + Elo/form/stats (incl. starter & series features), "
            f"9% market blend when odds available, then calibration — confidence matches displayed %"
        )

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
        if not starter_certain:
            notes.append("Probable starter not confirmed on one side")
        if pitcher_changed:
            notes.append("Probable starter changed since last board refresh")

        pick_team_id = game.home_team_id if predicted_home else game.away_team_id
        opponent_id = game.away_team_id if predicted_home else game.home_team_id
        series_fade = bundle.league.pick_lost_last_two_in_series(pick_team_id, opponent_id, game.game_date)
        if series_fade:
            notes.append("Pick lost last 2 vs this opponent — excluded from parlays (series fade)")

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
                "seriesFade": series_fade,
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
        "model_version": MODEL_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "retrained_this_run": retrained,
        "predictions": board,
    }
    PUBLIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_PATH.write_text(json.dumps(payload, indent=2))

    from prediction_integrity import run_all

    board_errors = run_all(recompute=True, ticket=True, accuracy=True)
    if board_errors:
        raise RuntimeError("Prediction integrity failed after board generation:\n" + "\n".join(board_errors))

    print(f"generated_predictions={len(board)}")
    print(f"trained_through={bundle.trained_through.isoformat()}")
    print(f"retrained_this_run={retrained}")


if __name__ == "__main__":
    main()
