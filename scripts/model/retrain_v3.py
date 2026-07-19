#!/usr/bin/env python3
"""Full v3 redesign retrain: HistGBM + market-residual α + best_ticket validation."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

from backtest_parlays import season_start_for
from daily_auto_model import MODEL_PATH, MODEL_VERSION, ensure_trained_through, walk_forward_history
from exhaustive_strategy_search import load_moneyline_by_day
from mlb_api import load_or_fetch_games, load_team_abbreviations
from strategy_next_tests import build_snapshots, compound, enrich_moneyline, summarize
from v3_market_residual import save_v3_params, tune_alpha

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = REPO_ROOT / "public" / "model-retrain-report.json"
STAKE = {1: 0.12, 2: 0.18, 3: 0.18, 4: 0.18}


def collect_alpha_samples(end: date) -> list[tuple[float, float, float, int]]:
    start = date(2026, 3, 20)
    prior = (season_start_for(2025), date(2025, 8, 17))
    from historical_odds import HistoricalOddsStore
    from team_tracker import LeagueState
    from trained_edge_model import (
        CURRENT_SEASON_SAMPLE_WEIGHT,
        PRIOR_SEASON_SAMPLE_WEIGHT,
        REFIT_EVERY,
        WARMUP_GAMES,
        TrainingExample,
        feature_row,
        fit_model,
        predict_with_model,
        recency_sample_weight,
    )
    from daily_auto_model import _ingest_game, no_vig_market_probabilities, prior_season_games

    games = load_or_fetch_games(start, end)
    team_abbr = load_team_abbreviations()
    odds = HistoricalOddsStore()
    league = LeagueState()
    examples: list[TrainingExample] = []
    weights: list[float] = []
    model = None
    last_fit = -REFIT_EVERY
    samples: list[tuple[float, float, float, int]] = []

    for prior_game in prior_season_games(end):
        _ingest_game(prior_game, league, examples, weights, PRIOR_SEASON_SAMPLE_WEIGHT)

    for index, game in enumerate(games):
        if len(examples) >= WARMUP_GAMES and (model is None or index - last_fit >= REFIT_EVERY):
            model = fit_model(examples, weights)
            last_fit = index

        if model is not None and len(examples) >= WARMUP_GAMES:
            pred = predict_with_model(game, league, model)
            home_abbr = team_abbr.get(game.home_team_id, "")
            away_abbr = team_abbr.get(game.away_team_id, "")
            market = odds.for_game(game.game_date.isoformat(), away_abbr, home_abbr)
            if market.source_count > 0 and market.home_moneyline and market.away_moneyline:
                probs = no_vig_market_probabilities(market.home_moneyline, market.away_moneyline)
                if probs:
                    samples.append((pred.home_probability, probs[0], probs[1], int(game.home_won)))

        features = feature_row(game, league)
        examples.append(TrainingExample(features=features, label=1 if game.home_won else 0))
        weights.append(recency_sample_weight(game.game_date, game.game_date, CURRENT_SEASON_SAMPLE_WEIGHT))
        league.apply_result(game.game_date, game.home_team_id, game.away_team_id, game.home_score, game.away_score)

    return samples


def main() -> None:
    end = date.today() - timedelta(days=1)
    print(f"=== V3 REDESIGN RETRAIN === model={MODEL_VERSION}")

    print("Tuning market-residual alpha...")
    samples = collect_alpha_samples(end)
    params = tune_alpha(samples)
    save_v3_params(params)
    print(f"  alpha={params.alpha:.3f} brier={params.holdout_brier:.4f} n={params.holdout_n}")

    if MODEL_PATH.exists():
        MODEL_PATH.unlink()
        print(f"Deleted stale {MODEL_PATH.name}")

    print("Training HistGBM through yesterday...")
    bundle, retrained = ensure_trained_through(end)
    print(f"  trained_through={bundle.trained_through} retrained={retrained}")

    print("Walk-forward + best_ticket validation...")
    start = date(2026, 3, 20)
    prior = (season_start_for(2025), date(2025, 8, 17))
    ml, _ = load_moneyline_by_day(start, end, prior[0], prior[1])
    ml = {d: c for d, c in ml.items() if date.fromisoformat(d) <= end}
    rows = walk_forward_history(
        load_or_fetch_games(start, end),
        load_team_abbreviations(),
        prior_games=load_or_fetch_games(*prior),
    )
    ml = enrich_moneyline(ml, rows)
    snaps = build_snapshots(ml, "best_ticket")
    holdout_start = (end - timedelta(days=20)).isoformat()
    holdout_snaps = [s for s in snaps if s["date"] >= holdout_start]
    wins = sum(1 for s in holdout_snaps if s.get("bets") and s["bets"][0].get("won"))
    losses = sum(1 for s in holdout_snaps if s.get("bets") and s["bets"][0].get("won") is False)
    total = wins + losses
    season = summarize("best_ticket", snaps)
    end10 = compound(snaps, 10.0, STAKE)["end"]

    recent_rows = [r for r in rows if r["date"] >= holdout_start]
    game_acc = sum(r["correct"] for r in recent_rows) / len(recent_rows) if recent_rows else 0.0

    report = {
        "generated_at": date.today().isoformat(),
        "architecture": "v3_market_residual",
        "model_version": MODEL_VERSION,
        "alpha": params.alpha,
        "alpha_brier": params.holdout_brier,
        "holdout_start": holdout_start,
        "holdout_end": end.isoformat(),
        "holdout_game_accuracy": round(game_acc, 4),
        "best_ticket_holdout": {
            "record": f"{wins}-{losses}",
            "hit_rate": round(wins / total, 4) if total else None,
            "bet_days": len(holdout_snaps),
        },
        "best_ticket_season": season,
        "compound_from_10": round(end10, 2),
        "live_strategy": "best_ticket",
        "changes": [
            "HistGBM replaces shallow GBM",
            "Market-anchored residual P = market + α(model − market)",
            "Edge-native confidence (no ERA/market-agree theater)",
            "Daily best_ticket — bet every qualified day",
        ],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2))

    print(f"\nHoldout tickets: {wins}-{losses} ({len(holdout_snaps)} days)")
    print(f"Holdout game accuracy: {game_acc:.1%}")
    print(f"Season best_ticket: {season['record']} ROI {season['flat_roi']:.1%}")
    print(f"$10 compound: ${end10:.2f}")
    print(f"Report -> {REPORT_PATH}")


if __name__ == "__main__":
    main()
