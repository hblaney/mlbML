"""Ablation: test v3 components against v2.1 baseline (walk-forward, same season)."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, HistGradientBoostingClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import trained_edge_model as v21
from full_registry_model import FullRegistryFeatureBuilder
from historical_odds import HistoricalOddsStore
from injuries_provider import injury_counts_for_game
from mlb_api import GameRecord, load_or_fetch_games, load_team_abbreviations
from odds_provider import implied_probability
from robust_blend import robust_home_probability
from team_tracker import LeagueState

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "model-ablation-results.json"


@dataclass(frozen=True)
class Ablation:
    name: str
    mode: str  # v21 | registry
    model: str  # shallow | histgbm | histgbm_scaled
    robust: bool = False
    injuries: bool = False
    statcast: bool = False


ABLATIONS_FULL = [
    Ablation("v2.1_baseline", "v21", "shallow"),
    Ablation("v2.1_robust_blend", "v21", "shallow", robust=True),
    Ablation("v2.1_histgbm", "v21", "histgbm"),
    Ablation("v2.1_histgbm_scaled", "v21", "histgbm_scaled"),
    Ablation("v2.1_injuries", "v21", "shallow", injuries=True),
    Ablation("v2.1_robust_injuries", "v21", "shallow", robust=True, injuries=True),
    Ablation("v2.1_statcast", "v21", "shallow", statcast=True),
    Ablation("registry_shallow_gbm", "registry", "shallow"),
    Ablation("registry_shallow_robust", "registry", "shallow", robust=True),
    Ablation("registry_histgbm", "registry", "histgbm_scaled"),
]

ABLATIONS_QUICK = [
    Ablation("v2.1_baseline", "v21", "shallow"),
    Ablation("v2.1_robust_blend", "v21", "shallow", robust=True),
    Ablation("v2.1_histgbm", "v21", "histgbm"),
    Ablation("v2.1_histgbm_scaled", "v21", "histgbm_scaled"),
    Ablation("v2.1_injuries", "v21", "shallow", injuries=True),
    Ablation("v2.1_robust_injuries", "v21", "shallow", robust=True, injuries=True),
]


def build_model(model: str) -> Pipeline:
    if model == "shallow":
        return v21.build_model()
    if model == "histgbm":
        return Pipeline(
            [
                (
                    "model",
                    HistGradientBoostingClassifier(
                        max_depth=5,
                        learning_rate=0.04,
                        max_iter=180,
                        random_state=42,
                    ),
                )
            ]
        )
    if model == "histgbm_scaled":
        return Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "model",
                    HistGradientBoostingClassifier(
                        max_depth=5,
                        learning_rate=0.04,
                        max_iter=180,
                        random_state=42,
                    ),
                ),
            ]
        )
    raise ValueError(model)


def injury_vector(game: GameRecord) -> list[float]:
    home_inj, away_inj = injury_counts_for_game(
        game.home_team_id,
        game.away_team_id,
        snapshot_date=game.game_date,
    )
    return [
        float(home_inj),
        float(away_inj),
        float(away_inj - home_inj),
        float(home_inj) / 10.0,
        float(away_inj) / 10.0,
    ]


def _preload_statcast_for_spec(
    spec: Ablation,
    games: list[GameRecord],
    prior_games: list[GameRecord] | None,
    registry_builder: FullRegistryFeatureBuilder | None,
) -> None:
    years = {game.game_date.year for game in games}
    if prior_games:
        years.update(game.game_date.year for game in prior_games)
    if spec.statcast:
        print("  preloading Statcast for v2.1 feature row...", flush=True)
        v21.preload_statcast_years(years)
    if spec.mode == "registry" and registry_builder is not None:
        for year in sorted(years):
            if year >= 2015:
                print(f"  preloading Statcast {year} (registry)...", flush=True)
                registry_builder.ensure_statcast_year(year)


def robust_map(
    game: GameRecord,
    league: LeagueState,
    *,
    home_abbr: str,
    away_abbr: str,
    odds_store: HistoricalOddsStore,
    injuries: bool,
) -> dict[str, float]:
    home = league.team(game.home_team_id)
    away = league.team(game.away_team_id)
    market = odds_store.for_game(game.game_date.isoformat(), away_abbr, home_abbr)
    home_market = implied_probability(market.home_moneyline) if market.home_moneyline else 0.5
    away_market = implied_probability(market.away_moneyline) if market.away_moneyline else 0.5
    home_inj, away_inj = injury_counts_for_game(
        game.home_team_id,
        game.away_team_id,
        snapshot_date=game.game_date,
    )
    return {
        "elo_difference": home.elo - away.elo,
        "home_win_pct": home.win_pct(),
        "away_win_pct": away.win_pct(),
        "season_win_pct_diff": home.win_pct() - away.win_pct(),
        "diff_win_pct_15": home.win_pct(15) - away.win_pct(15),
        "diff_run_diff_15": home.run_differential(15) - away.run_differential(15),
        "home_run_differential": home.run_differential(),
        "away_run_differential": away.run_differential(),
        "rest_days_delta": home.rest_days(game.game_date) - away.rest_days(game.game_date),
        "market_home_implied_probability": home_market,
        "market_away_implied_probability": away_market,
        "market_prob_delta": home_market - away_market,
        "injury_count_delta": float(away_inj - home_inj) if injuries else 0.0,
    }


def make_features(
    spec: Ablation,
    game: GameRecord,
    league: LeagueState,
    *,
    team_abbr: dict[int, str],
    registry_builder: FullRegistryFeatureBuilder | None,
    include_statcast: bool,
) -> list[float]:
    if spec.mode == "registry":
        assert registry_builder is not None
        return registry_builder.feature_row(game, league, include_statcast=include_statcast)

    features = list(v21.feature_row(game, league, include_statcast=spec.statcast))
    if spec.injuries:
        features.extend(injury_vector(game))
    return features


def walk_forward(
    spec: Ablation,
    games: list[GameRecord],
    team_abbr: dict[int, str],
    prior_games: list[GameRecord] | None,
) -> dict:
    league = LeagueState()
    examples: list[v21.TrainingExample] = []
    weights: list[float] = []
    model: Pipeline | None = None
    last_fit_index = -v21.REFIT_EVERY
    correct = 0
    total = 0
    odds = HistoricalOddsStore()
    registry_builder = FullRegistryFeatureBuilder(team_abbr) if spec.mode == "registry" else None
    use_statcast = spec.statcast or spec.mode == "registry"
    _preload_statcast_for_spec(spec, games, prior_games, registry_builder)

    def ingest(game: GameRecord, weight: float) -> None:
        examples.append(
            v21.TrainingExample(
                features=make_features(
                    spec,
                    game,
                    league,
                    team_abbr=team_abbr,
                    registry_builder=registry_builder,
                    include_statcast=use_statcast,
                ),
                label=1 if game.home_won else 0,
            )
        )
        weights.append(weight)
        league.apply_result(
            game.game_date,
            game.home_team_id,
            game.away_team_id,
            game.home_score,
            game.away_score,
        )

    for game in prior_games or []:
        ingest(game, v21.PRIOR_SEASON_SAMPLE_WEIGHT)

    for index, game in enumerate(games):
        if len(examples) >= v21.WARMUP_GAMES and (model is None or index - last_fit_index >= v21.REFIT_EVERY):
            x = v21._clean_matrix(np.array([example.features for example in examples], dtype=float))
            y = np.array([example.label for example in examples], dtype=int)
            if len(set(y.tolist())) >= 2:
                model = build_model(spec.model)
                if spec.model == "shallow":
                    model.fit(x, y, model__sample_weight=np.array(weights, dtype=float))
                else:
                    model.fit(x, y, model__sample_weight=np.array(weights, dtype=float))
            last_fit_index = index

        if len(examples) >= v21.WARMUP_GAMES and model is not None:
            home_abbr = team_abbr.get(game.home_team_id, str(game.home_team_id))
            away_abbr = team_abbr.get(game.away_team_id, str(game.away_team_id))
            x = v21._clean_matrix(
                np.array(
                    [
                        make_features(
                            spec,
                            game,
                            league,
                            team_abbr=team_abbr,
                            registry_builder=registry_builder,
                            include_statcast=use_statcast,
                        )
                    ],
                    dtype=float,
                )
            )
            home_probability = float(model.predict_proba(x)[0, 1])

            if spec.robust:
                fmap = robust_map(
                    game,
                    league,
                    home_abbr=home_abbr,
                    away_abbr=away_abbr,
                    odds_store=odds,
                    injuries=spec.injuries,
                )
                if spec.mode == "registry" and registry_builder is not None:
                    fmap = registry_builder.feature_map(game, league, include_statcast=use_statcast)
                home_probability = robust_home_probability(home_probability, fmap)

            market = odds.for_game(game.game_date.isoformat(), away_abbr, home_abbr)
            odds_available = market.source_count > 0 and market.home_moneyline != 0 and market.away_moneyline != 0
            if odds_available:
                market_probs = _no_vig(market.home_moneyline, market.away_moneyline)
                if market_probs is not None:
                    home_probability = v21.blend_with_market(home_probability, market_probs[0])
            home_probability = v21.sharpen_public_probability(home_probability)
            predicted_home = home_probability >= 0.5
            if predicted_home == game.home_won:
                correct += 1
            total += 1

        ingest(game, v21.CURRENT_SEASON_SAMPLE_WEIGHT)

    accuracy = correct / total if total else 0.0
    return {
        "name": spec.name,
        "mode": spec.mode,
        "model": spec.model,
        "robust": spec.robust,
        "injuries": spec.injuries,
        "statcast": spec.statcast,
        "games": total,
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "record": f"{correct}-{total - correct}",
    }


def _no_vig(home_moneyline: int, away_moneyline: int) -> tuple[float, float] | None:
    home = implied_probability(home_moneyline)
    away = implied_probability(away_moneyline)
    total = home + away
    if total <= 0:
        return None
    return home / total, away / total


def main() -> None:
    from backtest_parlays import odds_backtest_range

    quick = "--quick" in sys.argv or ("--full" not in sys.argv and "--statcast-retest" not in sys.argv)
    statcast_retest = "--statcast-retest" in sys.argv
    if statcast_retest:
        ablations = [
            Ablation("v2.1_baseline", "v21", "shallow"),
            Ablation("v2.1_statcast", "v21", "shallow", statcast=True),
        ]
    else:
        ablations = ABLATIONS_QUICK if quick else ABLATIONS_FULL
    mode_label = "statcast-retest" if statcast_retest else ("quick" if quick else "full")
    print(f"Running {mode_label} ablation ({len(ablations)} configs)...", flush=True)

    store = HistoricalOddsStore()
    start, end, odds_metadata = odds_backtest_range(store)
    team_abbr = load_team_abbreviations()
    prior = load_or_fetch_games(date(start.year - 1, 3, 20), date(start.year - 1, 10, 5))
    games = load_or_fetch_games(start, end)

    results: list[dict] = []
    baseline_accuracy = None

    for index, spec in enumerate(ablations):
        print(f"[{index + 1}/{len(ablations)}] {spec.name}...", flush=True)
        row = walk_forward(spec, games, team_abbr, prior)
        if spec.name == "v2.1_baseline":
            baseline_accuracy = row["accuracy"]
        if baseline_accuracy is not None:
            row["delta_vs_baseline"] = round(row["accuracy"] - baseline_accuracy, 4)
        results.append(row)
        print(f"  {row['record']} = {row['accuracy']*100:.2f}%", flush=True)

    results.sort(key=lambda item: item["accuracy"], reverse=True)
    winners = [row for row in results if row.get("delta_vs_baseline", 0) > 0]

    payload = {
        "generated_at": date.today().isoformat(),
        "run_mode": mode_label,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "baseline": "v2.1_baseline",
        "baseline_accuracy": baseline_accuracy,
        "odds_metadata": odds_metadata,
        "ranked": results,
        "beats_baseline": winners,
        "recommendation": winners[0]["name"] if winners else "v2.1_baseline",
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    print("\nRanked by game-pick accuracy:")
    for row in results:
        delta = row.get("delta_vs_baseline", 0)
        sign = f"{delta*100:+.2f}pts" if delta else "baseline"
        print(f"  {row['name']}: {row['accuracy']*100:.2f}% ({sign})")
    print(f"\nwrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
