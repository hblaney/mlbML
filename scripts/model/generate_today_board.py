"""Daily board generator with automatic retrain-through-yesterday."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from daily_auto_model import MODEL_VERSION, PIPELINE_VERSION, ensure_trained_through
from game_sim_board import simulate_game_record
from gbm_confidence import assign_daily_confidence
from mlb_api import fetch_upcoming_games, load_team_abbreviations
from odds_provider import fetch_moneyline_market, get_last_odds_error, get_last_odds_source, market_for_game
from trained_edge_model import _safe_pitcher_stats

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
        ML_SANITY_LIMIT = 1500  # real MLB lines never exceed ±1500; beyond that is corrupted API data
        _raw_home_ml = market_snapshot.home_moneyline
        _raw_away_ml = market_snapshot.away_moneyline
        odds_available = (
            market_snapshot.source_count > 0
            and _raw_home_ml != 0
            and _raw_away_ml != 0
            and abs(_raw_home_ml) <= ML_SANITY_LIMIT
            and abs(_raw_away_ml) <= ML_SANITY_LIMIT
        )
        market_probs = None
        if odds_available:
            total = market_snapshot.home_implied_probability + market_snapshot.away_implied_probability
            if total > 0:
                market_probs = (
                    market_snapshot.home_implied_probability / total,
                    market_snapshot.away_implied_probability / total,
                )

        home_abbr = team_abbr.get(game.home_team_id, str(game.home_team_id)).lower()
        away_abbr = team_abbr.get(game.away_team_id, str(game.away_team_id)).lower()
        game_id = f"{away_abbr}-{home_abbr}-{game.game_date.isoformat()}-{game.game_pk}"
        away_pitcher = game.away_pitcher_name or "TBD"
        home_pitcher = game.home_pitcher_name or "TBD"
        starter_certain = _starter_certain(game)
        pitcher_changed = _pitcher_changed(previous_pitchers, game_id, away_pitcher, home_pitcher)

        # ERA / form diagnostics (directional vs the GBM pick).
        home_pit = _safe_pitcher_stats(game, game.home_pitcher_id)
        away_pit = _safe_pitcher_stats(game, game.away_pitcher_id)

        gbm_home = float(prediction.home_probability)
        gbm_away = float(prediction.away_probability)

        # Official pick = raw GBM (OOS ~61% May–Jul). Sim stays diagnostic.
        home_probability = gbm_home
        away_probability = gbm_away
        pick_probability = max(home_probability, away_probability)
        raw_pick = pick_probability
        prediction_source = "raw_gbm"
        sim = simulate_game_record(game, starter_certain=starter_certain, n_sims=2000)

        predicted_home = home_probability >= away_probability
        _pick_pit = home_pit if predicted_home else away_pit
        _opp_pit = away_pit if predicted_home else home_pit
        era_diff = round(_opp_pit["era"] - _pick_pit["era"], 6)
        _pick_team = bundle.league.team(game.home_team_id if predicted_home else game.away_team_id)
        _opp_team = bundle.league.team(game.away_team_id if predicted_home else game.home_team_id)
        form_edge = round(_pick_team.win_pct(10) - _opp_team.win_pct(10), 6)

        market_home = market_probs[0] if market_probs else None
        market_away = market_probs[1] if market_probs else None
        market_agrees = None
        model_edge = 0.0
        if market_home is not None and market_away is not None:
            market_pick_home = market_home >= market_away
            market_agrees = predicted_home == market_pick_home
            market_for_pick = market_home if predicted_home else market_away
            model_edge = pick_probability - market_for_pick

        notes = [
            f"Retrained through {bundle.trained_through.isoformat()}",
            "Published pick = raw GBM win% (Elo/form/starter/park). Not market-anchored.",
            "OOS May–Jul 2026: overall ≈61%. High/Elite require p/ERA/form/market gates — no daily High quota.",
        ]
        if sim.ok:
            notes.append(
                f"PA sim diagnostic: home {sim.home_win_prob:.1%} "
                f"(runs {sim.mean_away_runs:.1f}-{sim.mean_home_runs:.1f}, {sim.lineup_source})"
            )

        predicted_team = home_abbr if predicted_home else away_abbr
        if odds_available:
            source = get_last_odds_source() or "sportsbooks"
            notes.append(f"Market prices from {market_snapshot.source_count} sportsbook source(s) ({source})")
        else:
            odds_error = get_last_odds_error()
            if odds_error and "OUT_OF_USAGE_CREDITS" in odds_error:
                notes.append("The Odds API quota is exhausted and ESPN fallback also failed")
            elif odds_error:
                notes.append(f"Live sportsbook odds unavailable: {odds_error}")
            else:
                notes.append("No live sportsbook odds available; EV/best-bet calculations are disabled for this game")

        if not starter_certain:
            notes.append("Probable starter not confirmed on one side")
        if pitcher_changed:
            notes.append("Probable starter changed since last board refresh")

        pick_team_id = game.home_team_id if predicted_home else game.away_team_id
        opponent_id = game.away_team_id if predicted_home else game.home_team_id
        series_fade = bundle.league.pick_lost_last_two_in_series(pick_team_id, opponent_id, game.game_date)
        if series_fade:
            notes.append("Pick lost last 2 vs this opponent — excluded from parlays (series fade)")

        projected_total = (
            round(sim.mean_home_runs + sim.mean_away_runs, 2)
            if sim.ok
            else projected_total_for(game, bundle.league)
        )

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
                "rawPickProbability": round(raw_pick, 4),
                "modelHomeWinProbability": round(home_probability, 4),
                "modelAwayWinProbability": round(away_probability, 4),
                "simRawHomeWinProbability": round(sim.raw_home_win_prob, 4) if sim.ok else None,
                "simRawAwayWinProbability": round(sim.raw_away_win_prob, 4) if sim.ok else None,
                "simHomeWinProbability": round(sim.home_win_prob, 4) if sim.ok else None,
                "simAwayWinProbability": round(sim.away_win_prob, 4) if sim.ok else None,
                "gbmHomeWinProbability": round(gbm_home, 4),
                "gbmAwayWinProbability": round(gbm_away, 4),
                "nSims": sim.n_sims if sim.ok else 0,
                "lineupSource": sim.lineup_source if sim.ok else None,
                "predictionSource": prediction_source,
                "homeMoneyline": market_snapshot.home_moneyline if odds_available else None,
                "awayMoneyline": market_snapshot.away_moneyline if odds_available else None,
                "homeRunline": market_snapshot.home_runline if odds_available and market_snapshot.home_runline_price else None,
                "awayRunline": market_snapshot.away_runline if odds_available and market_snapshot.away_runline_price else None,
                "homeRunlinePrice": market_snapshot.home_runline_price if odds_available and market_snapshot.home_runline_price else None,
                "awayRunlinePrice": market_snapshot.away_runline_price if odds_available and market_snapshot.away_runline_price else None,
                "marketTotal": market_snapshot.market_total if odds_available and market_snapshot.over_price and market_snapshot.under_price else None,
                "overPrice": market_snapshot.over_price if odds_available and market_snapshot.over_price else None,
                "underPrice": market_snapshot.under_price if odds_available and market_snapshot.under_price else None,
                "projectedTotal": projected_total,
                "oddsSource": get_last_odds_source() if odds_available else None,
                "confidence": "Low",
                "marketAgrees": market_agrees,
                "modelEdge": round(model_edge, 4),
                "eraDiff": era_diff,
                "formEdge": form_edge,
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
    assign_daily_confidence(board)
    _CONF_RANK = {"Elite": 4, "High": 3, "Medium": 2, "Low": 1}
    board.sort(
        key=lambda row: (
            _CONF_RANK.get(str(row.get("confidence") or "Low"), 0),
            float(row.get("pickProbability") or 0),
        ),
        reverse=True,
    )
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

    # Off days (All-Star break, etc.) publish an empty board + skip ticket/recompute checks.
    # ticket=False: best-bets ticket check needs Node/tsx; lock_daily_ticket runs in CI after.
    board_errors = run_all(recompute=True, ticket=False, accuracy=True)
    if board_errors:
        raise RuntimeError("Prediction integrity failed after board generation:\n" + "\n".join(board_errors))

    if board:
        from generate_prop_leans import main as generate_prop_leans_main
        from prop_bet import build_all_starters, save_cards

        generate_prop_leans_main()
        cards = build_all_starters(today)
        save_cards(cards, today)
        from generate_prizepicks_slip import main as generate_prizepicks_slip_main
        generate_prizepicks_slip_main()
        print(f"prop_bet_cards_ok count={len(cards)}")

        # Full PrizePicks board is generated by callers (daily:core / refresh-board)
        # so we don't burn Odds API credits twice in one pipeline.
    else:
        print("prop_leans_skip off_day_empty_board")

    print(f"generated_predictions={len(board)}")
    print(f"trained_through={bundle.trained_through.isoformat()}")
    print(f"retrained_this_run={retrained}")
    if not board:
        print("off_day=True — no MLB regular-season games; board empty, pipeline continues")


if __name__ == "__main__":
    main()
