"""Advanced MLB model using a dynamic real-source feature matrix."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.feature_selection import mutual_info_classif
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

from advanced_matrix import AdvancedMatrixBuilder
from mlb_api import load_or_fetch_games
from team_tracker import LeagueState

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "advanced-algo.json"
WARMUP_GAMES = 200


def vectorize(rows: list[dict[str, float]], selected: list[str] | None = None) -> tuple[np.ndarray, list[str]]:
    names = selected or sorted({key for row in rows for key in row.keys()})
    matrix = np.array([[float(row.get(name, 0.0)) for name in names] for row in rows], dtype=float)
    matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)
    matrix = np.clip(matrix, -1_000_000, 1_000_000)
    return matrix, names


def build_dataset(start: date, end: date, include_weather: bool) -> tuple[np.ndarray, np.ndarray, list[str]]:
    games = load_or_fetch_games(start, end)
    state = LeagueState()
    builder = AdvancedMatrixBuilder(include_weather=include_weather)
    rows: list[dict[str, float]] = []
    labels: list[int] = []

    for index, game in enumerate(games):
        if index >= WARMUP_GAMES:
            rows.append(builder.build_row(game, state))
            labels.append(1 if game.home_won else 0)

        state.apply_result(
            game.game_date,
            game.home_team_id,
            game.away_team_id,
            game.home_score,
            game.away_score,
        )

    x, names = vectorize(rows)
    return x, np.array(labels, dtype=int), names


def rank_features(x: np.ndarray, y: np.ndarray, names: list[str]) -> list[dict]:
    mi = mutual_info_classif(x, y, discrete_features=False, random_state=42)
    ranked = []
    for index, name in enumerate(names):
        column = x[:, index]
        if np.std(column) == 0:
            corr = 0.0
            auc = 0.5
        else:
            corr = float(np.corrcoef(column, y)[0, 1])
            if corr != corr:
                corr = 0.0
            try:
                auc = float(roc_auc_score(y, column))
                auc = max(auc, 1 - auc)
            except ValueError:
                auc = 0.5

        ranked.append(
            {
                "feature": name,
                "abs_corr": abs(corr),
                "directional_corr": corr,
                "univariate_auc": auc,
                "mutual_information": float(mi[index]),
            }
        )

    ranked.sort(key=lambda item: (item["univariate_auc"], item["mutual_information"], item["abs_corr"]), reverse=True)
    return ranked


def evaluate_model(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    splitter = TimeSeriesSplit(n_splits=5)
    probs: list[float] = []
    actuals: list[int] = []

    for train_idx, test_idx in splitter.split(x):
        model = VotingClassifier(
            estimators=[
                (
                    "gbm",
                    HistGradientBoostingClassifier(
                        max_depth=5,
                        learning_rate=0.035,
                        max_iter=250,
                        l2_regularization=0.04,
                        random_state=42,
                    ),
                ),
                (
                    "rf",
                    RandomForestClassifier(
                        n_estimators=260,
                        max_depth=9,
                        min_samples_leaf=14,
                        random_state=43,
                        n_jobs=-1,
                    ),
                ),
                (
                    "extra",
                    ExtraTreesClassifier(
                        n_estimators=260,
                        max_depth=9,
                        min_samples_leaf=14,
                        random_state=44,
                        n_jobs=-1,
                    ),
                ),
            ],
            voting="soft",
            weights=[3, 1, 1],
        )
        model.fit(x[train_idx], y[train_idx])
        fold_probs = model.predict_proba(x[test_idx])[:, 1]
        probs.extend(fold_probs.tolist())
        actuals.extend(y[test_idx].tolist())

    preds = [1 if p >= 0.5 else 0 for p in probs]
    return {
        "accuracy": float(accuracy_score(actuals, preds)),
        "auc": float(roc_auc_score(actuals, probs)),
        "brier": float(brier_score_loss(actuals, probs)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-04-01")
    parser.add_argument("--end", default="2025-08-16")
    parser.add_argument("--include-weather", action="store_true")
    parser.add_argument("--top-n", type=int, default=80)
    args = parser.parse_args()

    x, y, names = build_dataset(date.fromisoformat(args.start), date.fromisoformat(args.end), args.include_weather)
    ranked = rank_features(x, y, names)
    selected_names = [row["feature"] for row in ranked[: min(args.top_n, len(ranked))]]
    selected_indices = [names.index(name) for name in selected_names]
    x_selected = x[:, selected_indices]

    all_metrics = evaluate_model(x, y)
    selected_metrics = evaluate_model(x_selected, y)

    output = {
        "generated_at": date.today().isoformat(),
        "date_range": {"start": args.start, "end": args.end},
        "games": int(y.shape[0]),
        "features_total": len(names),
        "selected_top_n": len(selected_names),
        "all_features": all_metrics,
        "top_features_model": selected_metrics,
        "top_features": ranked[:100],
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print(f"games={output['games']}")
    print(f"features_total={output['features_total']}")
    print(f"all_features_accuracy={all_metrics['accuracy']:.4f}")
    print(f"top_{len(selected_names)}_accuracy={selected_metrics['accuracy']:.4f}")
    print(f"top_{len(selected_names)}_auc={selected_metrics['auc']:.4f}")


if __name__ == "__main__":
    main()
