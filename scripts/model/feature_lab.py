"""Feature selection lab for the MLB model.

This script is for deciding which predictors deserve to be in the production
model. It does not assume that more features are better.

Workflow:
1. Build a strictly pre-game dataset in chronological order.
2. Rank individual features by correlation and univariate AUC.
3. Rank feature groups with time-series cross validation.
4. Greedily combine the best groups only when they improve validation accuracy.

An exhaustive search of every possible combination is mathematically impossible
for hundreds of features: 899 features implies 2^899 combinations. This lab
does the practical version: exhaustive group screening plus validated greedy
selection.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from itertools import combinations
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_selection import mutual_info_classif
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from context import FeatureContext
from feature_registry import FEATURES
from features import build_feature_vector
from mlb_api import GameRecord, fetch_pitcher_season_era, load_or_fetch_games
from park_factors import park_for_team
from team_tracker import LeagueState

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "feature-lab.json"
MIN_TRAIN_GAMES = 250
MAX_GREEDY_GROUPS = 12
TOP_FEATURE_SWEEPS = [5, 10, 25, 50, 100, 200, 400]
PAIRWISE_TOP_N = 40
TRIPLE_TOP_N = 20


@dataclass(frozen=True)
class Dataset:
    x: np.ndarray
    y: np.ndarray
    feature_names: list[str]


def _starter_eras(game: GameRecord) -> tuple[float, float]:
    season = game.game_date.year
    home_era = 4.35
    away_era = 4.35

    if game.home_pitcher_id:
        try:
            home_era = fetch_pitcher_season_era(game.home_pitcher_id, season)
        except Exception:
            pass
    if game.away_pitcher_id:
        try:
            away_era = fetch_pitcher_season_era(game.away_pitcher_id, season)
        except Exception:
            pass

    return home_era, away_era


def build_dataset(games: list[GameRecord]) -> Dataset:
    state = LeagueState()
    rows: list[list[float]] = []
    labels: list[int] = []

    for index, game in enumerate(games):
        home = state.team(game.home_team_id)
        away = state.team(game.away_team_id)
        home_era, away_era = _starter_eras(game)
        context = FeatureContext(park=park_for_team(game.home_team_id))

        if index >= MIN_TRAIN_GAMES:
            rows.append(
                build_feature_vector(
                    home,
                    away,
                    game.game_date,
                    home_era,
                    away_era,
                    context,
                )
            )
            labels.append(1 if game.home_won else 0)

        state.apply_result(
            game.game_date,
            game.home_team_id,
            game.away_team_id,
            game.home_score,
            game.away_score,
        )

    return Dataset(np.array(rows, dtype=float), np.array(labels, dtype=int), FEATURES)


def feature_group(feature_name: str) -> str:
    if "market" in feature_name or "line" in feature_name:
        return "market"
    if feature_name.startswith("weather") or feature_name in {"temperature", "wind_speed", "wind_out_to_center"}:
        return "weather"
    if feature_name.startswith("park"):
        return "park"
    if "starter" in feature_name:
        return "starter"
    if "bullpen" in feature_name:
        return "bullpen"
    if "elo" in feature_name:
        return "elo"
    if "wrc" in feature_name or any(token in feature_name for token in ["ops", "obp", "slg", "iso", "runs_scored"]):
        return "offense"
    if "runs_allowed" in feature_name or "defensive" in feature_name or "errors" in feature_name:
        return "run-prevention"
    if "rest" in feature_name or "travel" in feature_name or "home_field" in feature_name:
        return "schedule"
    return "other"


def safe_corr(x: np.ndarray, y: np.ndarray) -> float:
    if np.std(x) == 0:
        return 0.0
    corr = np.corrcoef(x, y)[0, 1]
    if math.isnan(corr):
        return 0.0
    return float(corr)


def rank_individual_features(dataset: Dataset, limit: int | None = None) -> list[dict[str, float | str]]:
    x = dataset.x
    y = dataset.y
    mutual_info = mutual_info_classif(x, y, discrete_features=False, random_state=42)
    ranked = []

    for index, name in enumerate(dataset.feature_names):
        column = x[:, index]
        corr = safe_corr(column, y)
        auc = 0.5
        if len(np.unique(column)) > 1:
            try:
                auc = roc_auc_score(y, column)
                auc = max(auc, 1 - auc)
            except ValueError:
                auc = 0.5
        ranked.append(
            {
                "feature": name,
                "group": feature_group(name),
                "abs_corr": abs(corr),
                "directional_corr": corr,
                "univariate_auc": float(auc),
                "mutual_information": float(mutual_info[index]),
            }
        )

    ranked.sort(
        key=lambda item: (
            float(item["univariate_auc"]),
            float(item["mutual_information"]),
            float(item["abs_corr"]),
        ),
        reverse=True,
    )
    return ranked if limit is None else ranked[:limit]


def evaluate_columns(dataset: Dataset, column_indices: list[int], model_type: str = "gbm") -> dict[str, float]:
    if not column_indices:
        return {"accuracy": 0.0, "auc": 0.5, "brier": 1.0}

    x = dataset.x[:, column_indices]
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    x = np.clip(x, -1_000_000, 1_000_000)
    y = dataset.y
    splitter = TimeSeriesSplit(n_splits=5)
    predictions: list[int] = []
    probabilities: list[float] = []
    actuals: list[int] = []

    for train_index, test_index in splitter.split(x):
        if model_type == "gbm":
            model = make_pipeline(
                StandardScaler(),
                HistGradientBoostingClassifier(
                    max_depth=4,
                    learning_rate=0.04,
                    max_iter=180,
                    random_state=42,
                ),
            )
        else:
            model = make_pipeline(
                StandardScaler(),
                LogisticRegression(max_iter=1000, C=0.5, solver="liblinear"),
            )

        model.fit(x[train_index], y[train_index])
        probability = model.predict_proba(x[test_index])[:, 1]
        probabilities.extend(probability.tolist())
        predictions.extend((probability >= 0.5).astype(int).tolist())
        actuals.extend(y[test_index].tolist())

    return {
        "accuracy": float(accuracy_score(actuals, predictions)),
        "auc": float(roc_auc_score(actuals, probabilities)),
        "brier": float(brier_score_loss(actuals, probabilities)),
    }


def group_indices(dataset: Dataset) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {}
    for index, name in enumerate(dataset.feature_names):
        groups.setdefault(feature_group(name), []).append(index)
    return groups


def evaluate_groups(dataset: Dataset) -> list[dict[str, float | str | int]]:
    results = []
    for group, indices in group_indices(dataset).items():
        metrics = evaluate_columns(dataset, indices)
        results.append({"group": group, "features": len(indices), **metrics})
    results.sort(key=lambda item: (float(item["accuracy"]), float(item["auc"])), reverse=True)
    return results


def top_feature_sweeps(dataset: Dataset, ranked_features: list[dict[str, float | str]]) -> list[dict[str, float | int | str]]:
    name_to_index = {name: index for index, name in enumerate(dataset.feature_names)}
    results: list[dict[str, float | int | str]] = []

    for count in TOP_FEATURE_SWEEPS:
        selected = ranked_features[: min(count, len(ranked_features))]
        indices = [name_to_index[str(item["feature"])] for item in selected]
        metrics = evaluate_columns(dataset, indices, model_type="gbm")
        results.append({"selection": f"top_{len(indices)}_individual_features", "features": len(indices), **metrics})

    all_indices = list(range(len(dataset.feature_names)))
    metrics = evaluate_columns(dataset, all_indices, model_type="gbm")
    results.append({"selection": "all_features", "features": len(all_indices), **metrics})
    return results


def evaluate_every_single_feature(dataset: Dataset) -> list[dict[str, float | str | int]]:
    """Cross-validate each feature in isolation."""
    results: list[dict[str, float | str | int]] = []
    total = len(dataset.feature_names)

    for index, name in enumerate(dataset.feature_names):
        metrics = evaluate_columns(dataset, [index], model_type="gbm")
        results.append({"feature": name, "group": feature_group(name), **metrics})
        if (index + 1) % 50 == 0 or index + 1 == total:
            print(f"single_feature_progress={index + 1}/{total}")

    results.sort(key=lambda item: (float(item["accuracy"]), float(item["auc"])), reverse=True)
    return results


def exhaustive_group_combinations(dataset: Dataset) -> list[dict[str, float | str | int | list[str]]]:
    """Test every possible combination of feature groups."""
    groups = group_indices(dataset)
    group_names = sorted(groups.keys())
    results: list[dict[str, float | str | int | list[str]]] = []
    total = 2 ** len(group_names) - 1

    for size in range(1, len(group_names) + 1):
        for combo in combinations(group_names, size):
            indices: list[int] = []
            for group in combo:
                indices.extend(groups[group])
            metrics = evaluate_columns(dataset, sorted(set(indices)), model_type="gbm")
            results.append(
                {
                    "groups": list(combo),
                    "group_count": len(combo),
                    "features": len(set(indices)),
                    **metrics,
                }
            )

    results.sort(key=lambda item: (float(item["accuracy"]), float(item["auc"])), reverse=True)
    print(f"group_combo_tests={total}")
    return results


def exhaustive_feature_pairs(dataset: Dataset, ranked_features: list[dict[str, float | str]]) -> list[dict]:
    """Test every pair among the top univariate features."""
    name_to_index = {name: index for index, name in enumerate(dataset.feature_names)}
    top = ranked_features[:PAIRWISE_TOP_N]
    results: list[dict] = []
    pairs = list(combinations(top, 2))
    total = len(pairs)

    for index, (left, right) in enumerate(pairs, start=1):
        indices = [name_to_index[str(left["feature"])], name_to_index[str(right["feature"])]]
        metrics = evaluate_columns(dataset, indices, model_type="gbm")
        results.append(
            {
                "features": [str(left["feature"]), str(right["feature"])],
                **metrics,
            }
        )
        if index % 100 == 0 or index == total:
            print(f"pair_progress={index}/{total}")

    results.sort(key=lambda item: (item["accuracy"], item["auc"]), reverse=True)
    return results


def exhaustive_feature_triples(dataset: Dataset, ranked_features: list[dict[str, float | str]]) -> list[dict]:
    """Test every triple among the top univariate features."""
    name_to_index = {name: index for index, name in enumerate(dataset.feature_names)}
    top = ranked_features[:TRIPLE_TOP_N]
    results: list[dict] = []
    triples = list(combinations(top, 3))
    total = len(triples)

    for index, combo in enumerate(triples, start=1):
        indices = [name_to_index[str(item["feature"])] for item in combo]
        metrics = evaluate_columns(dataset, indices, model_type="gbm")
        results.append(
            {
                "features": [str(item["feature"]) for item in combo],
                **metrics,
            }
        )
        if index % 100 == 0 or index == total:
            print(f"triple_progress={index}/{total}")

    results.sort(key=lambda item: (item["accuracy"], item["auc"]), reverse=True)
    return results


def group_ablation_tests(dataset: Dataset) -> list[dict[str, float | str | int]]:
    groups = group_indices(dataset)
    all_indices = set(range(len(dataset.feature_names)))
    results: list[dict[str, float | str | int]] = []

    baseline = evaluate_columns(dataset, sorted(all_indices), model_type="gbm")
    results.append({"removed_group": "none", "features": len(all_indices), **baseline})

    for group, indices in groups.items():
        remaining = sorted(all_indices - set(indices))
        metrics = evaluate_columns(dataset, remaining, model_type="gbm")
        results.append(
            {
                "removed_group": group,
                "features": len(remaining),
                "accuracy_delta_vs_all": metrics["accuracy"] - baseline["accuracy"],
                "auc_delta_vs_all": metrics["auc"] - baseline["auc"],
                **metrics,
            }
        )

    results.sort(key=lambda item: float(item.get("accuracy_delta_vs_all", 0.0)))
    return results


def greedy_group_search(dataset: Dataset, group_results: list[dict[str, float | str | int]]) -> list[dict]:
    groups = group_indices(dataset)
    selected: list[str] = []
    selected_indices: list[int] = []
    history: list[dict] = []
    best_accuracy = 0.0

    for _ in range(min(MAX_GREEDY_GROUPS, len(group_results))):
        candidates = []
        for result in group_results:
            group = str(result["group"])
            if group in selected:
                continue
            candidate_indices = sorted(set(selected_indices + groups[group]))
            metrics = evaluate_columns(dataset, candidate_indices, model_type="gbm")
            candidates.append({"group": group, "feature_count": len(candidate_indices), **metrics})

        if not candidates:
            break

        candidates.sort(key=lambda item: (item["accuracy"], item["auc"]), reverse=True)
        best_candidate = candidates[0]
        if best_candidate["accuracy"] <= best_accuracy:
            break

        selected.append(str(best_candidate["group"]))
        selected_indices = sorted(set(selected_indices + groups[str(best_candidate["group"])]))
        best_accuracy = float(best_candidate["accuracy"])
        history.append({"selected_groups": list(selected), **best_candidate})

    return history


def main() -> None:
    games = load_or_fetch_games(date(2024, 3, 20), date.today())
    dataset = build_dataset(games)
    print(f"games={dataset.y.shape[0]}")
    print(f"features={len(dataset.feature_names)}")

    print("stage=univariate_ranking")
    all_feature_scores = rank_individual_features(dataset, limit=None)

    print("stage=single_feature_cv")
    single_feature_cv = evaluate_every_single_feature(dataset)

    print("stage=group_singles")
    groups = evaluate_groups(dataset)

    print("stage=exhaustive_group_combos")
    group_combos = exhaustive_group_combinations(dataset)

    print("stage=top_feature_sweeps")
    sweeps = top_feature_sweeps(dataset, all_feature_scores)

    print("stage=pairwise_combos")
    pairs = exhaustive_feature_pairs(dataset, all_feature_scores)

    print("stage=triple_combos")
    triples = exhaustive_feature_triples(dataset, all_feature_scores)

    print("stage=group_ablation")
    ablations = group_ablation_tests(dataset)

    print("stage=greedy_group_search")
    greedy = greedy_group_search(dataset, groups)

    best_group_combo = group_combos[0] if group_combos else None
    best_pair = pairs[0] if pairs else None
    best_triple = triples[0] if triples else None
    best_single = single_feature_cv[0] if single_feature_cv else None

    output = {
        "generated_at": date.today().isoformat(),
        "games": int(dataset.y.shape[0]),
        "features": len(dataset.feature_names),
        "note": (
            "Every individual feature and every group combination was tested. "
            f"All {PAIRWISE_TOP_N}-choose-2 pairs and {TRIPLE_TOP_N}-choose-3 triples among top univariate features were tested. "
            "Full 2^899 feature subset search is not computationally possible."
        ),
        "all_feature_scores": all_feature_scores,
        "single_feature_cv": single_feature_cv,
        "best_single_feature": best_single,
        "top_features": all_feature_scores[:50],
        "top_feature_sweeps": sweeps,
        "group_results": groups,
        "exhaustive_group_combinations": group_combos[:25],
        "best_group_combination": best_group_combo,
        "exhaustive_pairwise_top": pairs[:25],
        "best_pairwise_combination": best_pair,
        "exhaustive_triple_top": triples[:25],
        "best_triple_combination": best_triple,
        "group_ablation_tests": ablations,
        "greedy_group_search": greedy,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print("stage=complete")
    if best_group_combo:
        print(f"best_group_combo_accuracy={best_group_combo['accuracy']:.4f}")
        print(f"best_group_combo={','.join(best_group_combo['groups'])}")
    if best_single:
        print(f"best_single_feature={best_single['feature']}")
        print(f"best_single_accuracy={best_single['accuracy']:.4f}")
    if greedy:
        print(f"greedy_accuracy={greedy[-1]['accuracy']:.4f}")


if __name__ == "__main__":
    main()
