"""Walk-forward: raw GBM vs blend/sharpen vs old post-hoc 'processed' live board."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import trained_edge_model as m
from backtest_parlays import odds_backtest_range
from daily_auto_model import no_vig_market_probabilities
from fast_edge_model import FastPrediction
from historical_odds import HistoricalOddsStore
from mlb_api import GameRecord, load_or_fetch_games, load_team_abbreviations
from team_tracker import LeagueState
from trained_edge_model import (
    TrainingExample,
    _safe_pitcher_stats,
    blend_with_market,
    final_public_probabilities,
    fit_model,
    predict_with_model,
    sharpen_public_probability,
)

OUTPUT = Path(__file__).resolve().parents[2] / "data" / "model" / "pipeline-comparison.json"

# Old live-board post-hoc constants (removed from production — test only).
SERIES_PICK_LOST_TWO_SHIFT = 0.10
SERIES_OPPONENT_WON_LAST_SHIFT = 0.06
VETERAN_STARTER_ERA_EDGE = 0.75
VETERAN_STARTER_NUDGE = 0.10
ELITE_STARTER_ERA_EDGE = 1.50
ELITE_STARTER_EXTRA_NUDGE = 0.05


def apply_live_context_adjustments(
    game: GameRecord,
    league: LeagueState,
    home_probability: float,
) -> float:
    """Old gameday nudge layer — walk-forward test only."""
    home_probability = float(np.clip(home_probability, 0.30, 0.70))
    predicted_home = home_probability >= 0.5
    pick_id = game.home_team_id if predicted_home else game.away_team_id
    opponent_id = game.away_team_id if predicted_home else game.home_team_id

    home_pitcher = _safe_pitcher_stats(game, game.home_pitcher_id)
    away_pitcher = _safe_pitcher_stats(game, game.away_pitcher_id)
    if (
        away_pitcher["innings_pitched"] >= m.VETERAN_STARTER_IP_MIN
        and home_pitcher["innings_pitched"] <= m.ROOKIE_STARTER_IP_MAX
        and away_pitcher["era"] + VETERAN_STARTER_ERA_EDGE < home_pitcher["era"]
    ):
        shift = VETERAN_STARTER_NUDGE
        if away_pitcher["era"] + ELITE_STARTER_ERA_EDGE < home_pitcher["era"]:
            shift += ELITE_STARTER_EXTRA_NUDGE
        home_probability = float(np.clip(home_probability - shift, 0.30, 0.70))
        predicted_home = home_probability >= 0.5
        pick_id = game.home_team_id if predicted_home else game.away_team_id
        opponent_id = game.away_team_id if predicted_home else game.home_team_id
    elif (
        home_pitcher["innings_pitched"] >= m.VETERAN_STARTER_IP_MIN
        and away_pitcher["innings_pitched"] <= m.ROOKIE_STARTER_IP_MAX
        and home_pitcher["era"] + VETERAN_STARTER_ERA_EDGE < away_pitcher["era"]
    ):
        shift = VETERAN_STARTER_NUDGE
        if home_pitcher["era"] + ELITE_STARTER_ERA_EDGE < away_pitcher["era"]:
            shift += ELITE_STARTER_EXTRA_NUDGE
        home_probability = float(np.clip(home_probability + shift, 0.30, 0.70))
        predicted_home = home_probability >= 0.5
        pick_id = game.home_team_id if predicted_home else game.away_team_id
        opponent_id = game.away_team_id if predicted_home else game.home_team_id

    recent = league.recent_head_to_head(pick_id, opponent_id, game.game_date, max_games=3)
    if len(recent) >= 2 and league.pick_lost_last_two_in_series(pick_id, opponent_id, game.game_date):
        if predicted_home:
            home_probability -= SERIES_PICK_LOST_TWO_SHIFT
        else:
            home_probability += SERIES_PICK_LOST_TWO_SHIFT
        home_probability = float(np.clip(home_probability, 0.30, 0.70))
    elif recent:
        last = recent[-1]
        days_since = (game.game_date - last.game_date).days
        opponent_won_last = league.team_won_in_h2h(opponent_id, last)
        if days_since <= 4 and opponent_won_last:
            if predicted_home:
                home_probability -= SERIES_OPPONENT_WON_LAST_SHIFT
            else:
                home_probability += SERIES_OPPONENT_WON_LAST_SHIFT
            home_probability = float(np.clip(home_probability, 0.30, 0.70))

    return home_probability


@dataclass(frozen=True)
class Pipeline:
    name: str
    mode: str  # raw | blend | blend_sharpen | blend_sharpen_context


def pick_from_home_prob(home_probability: float, home_abbr: str, away_abbr: str, actual_home_won: bool) -> dict:
    predicted_home = home_probability >= 0.5
    predicted = home_abbr if predicted_home else away_abbr
    actual = home_abbr if actual_home_won else away_abbr
    return {
        "predicted": predicted,
        "correct": int(predicted == actual),
        "pick_probability": max(home_probability, 1.0 - home_probability),
    }


def resolve_probabilities(
    pipeline: Pipeline,
    prediction: FastPrediction,
    game: GameRecord,
    league: LeagueState,
    market_home: float | None,
    market_away: float | None,
) -> float:
    if pipeline.mode == "raw":
        return prediction.home_probability

    if pipeline.mode == "blend":
        hp = prediction.home_probability
        if market_home is not None and market_away is not None:
            hp = blend_with_market(hp, market_home)
            ap = blend_with_market(prediction.away_probability, market_away)
            total = hp + ap
            hp /= total
        return hp

    if pipeline.mode == "blend_sharpen":
        return final_public_probabilities(
            prediction,
            market_home=market_home,
            market_away=market_away,
        ).home_probability

    if pipeline.mode == "blend_sharpen_context":
        hp = prediction.home_probability
        if market_home is not None and market_away is not None:
            hp = blend_with_market(hp, market_home)
            ap = blend_with_market(prediction.away_probability, market_away)
            total = hp + ap
            hp /= total
        hp = sharpen_public_probability(hp)
        hp = apply_live_context_adjustments(game, league, hp)
        return hp

    raise ValueError(pipeline.mode)


def walk_forward_pipeline(
    pipeline: Pipeline,
    games: list,
    team_abbr: dict[int, str],
    prior_games: list | None,
) -> dict:
    from daily_auto_model import _ingest_game
    from trained_edge_model import feature_row

    league = LeagueState()
    examples: list[TrainingExample] = []
    weights: list[float] = []
    model = None
    last_fit_index = -m.REFIT_EVERY
    correct = 0
    total = 0
    odds = HistoricalOddsStore()

    for game in prior_games or []:
        _ingest_game(game, league, examples, weights, m.PRIOR_SEASON_SAMPLE_WEIGHT)

    for index, game in enumerate(games):
        if len(examples) >= m.WARMUP_GAMES and (model is None or index - last_fit_index >= m.REFIT_EVERY):
            model = fit_model(examples, weights)
            last_fit_index = index

        if len(examples) >= m.WARMUP_GAMES and model is not None:
            prediction = predict_with_model(game, league, model)
            home_abbr = team_abbr.get(game.home_team_id, str(game.home_team_id))
            away_abbr = team_abbr.get(game.away_team_id, str(game.away_team_id))
            market = odds.for_game(game.game_date.isoformat(), away_abbr, home_abbr)
            odds_available = market.source_count > 0 and market.home_moneyline != 0 and market.away_moneyline != 0
            market_probs = (
                no_vig_market_probabilities(market.home_moneyline, market.away_moneyline)
                if odds_available
                else None
            )
            if not odds_available:
                examples.append(TrainingExample(features=feature_row(game, league), label=1 if game.home_won else 0))
                weights.append(m.CURRENT_SEASON_SAMPLE_WEIGHT)
                league.apply_result(
                    game.game_date,
                    game.home_team_id,
                    game.away_team_id,
                    game.home_score,
                    game.away_score,
                )
                continue

            home_probability = resolve_probabilities(
                pipeline,
                prediction,
                game,
                league,
                market_probs[0] if market_probs else None,
                market_probs[1] if market_probs else None,
            )
            row = pick_from_home_prob(home_probability, home_abbr, away_abbr, game.home_won)
            correct += row["correct"]
            total += 1

        examples.append(TrainingExample(features=feature_row(game, league), label=1 if game.home_won else 0))
        weights.append(m.CURRENT_SEASON_SAMPLE_WEIGHT)
        league.apply_result(
            game.game_date,
            game.home_team_id,
            game.away_team_id,
            game.home_score,
            game.away_score,
        )

    accuracy = correct / total if total else 0.0
    return {
        "pipeline": pipeline.name,
        "mode": pipeline.mode,
        "games": total,
        "correct": correct,
        "accuracy": round(accuracy, 4),
    }


def main() -> None:
    store = HistoricalOddsStore()
    start, end, _ = odds_backtest_range(store)
    prior = load_or_fetch_games(__import__("datetime").date(start.year - 1, 3, 20), __import__("datetime").date(start.year - 1, 10, 5))
    games = load_or_fetch_games(start, end)
    abbr = load_team_abbreviations()

    pipelines = [
        Pipeline("1_raw_gbm", "raw"),
        Pipeline("2_blend_only", "blend"),
        Pipeline("3_blend_sharpen_unified", "blend_sharpen"),
        Pipeline("4_blend_sharpen_posthoc_context", "blend_sharpen_context"),
    ]

    results = []
    for pipe in pipelines:
        print(f"testing {pipe.name}...", flush=True)
        row = walk_forward_pipeline(pipe, games, abbr, prior)
        print(f"  {row['accuracy']*100:.2f}% ({row['correct']}/{row['games']})", flush=True)
        results.append(row)

    best = max(results, key=lambda r: r["accuracy"])
    payload = {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "best": best,
        "results": sorted(results, key=lambda r: r["accuracy"], reverse=True),
        "note": "Market-backed games only. Post-hoc context = old live-board veteran/series nudges after blend+sharpen.",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
