"""Search high-signal feature combinations from the top 200 predictors.

This is the heavy feature-combo lab:
- rank all features
- keep the top 200 candidates
- test all singles
- test every pair among top 200
- test sampled triples and larger random subsets
- run beam search to build strong multi-feature combinations
- re-score finalists with time-series cross validation

It intentionally does not claim to test 2^200 subsets. That number is larger
than any practical compute budget. The goal is to test the most plausible
combinations deeply and honestly.
"""

from __future__ import annotations

import argparse
import json
import random
import warnings
from dataclasses import dataclass
from datetime import date
from itertools import combinations
from pathlib import Path

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from feature_lab import build_dataset, evaluate_columns, rank_individual_features
from mlb_api import load_or_fetch_games

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "top200-search.json"
warnings.filterwarnings("ignore", category=RuntimeWarning)


@dataclass(frozen=True)
class Candidate:
    name: str
    indices: tuple[int, ...]
    source: str


def clean_x(x: np.ndarray) -> np.ndarray:
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    return np.clip(x, -1_000_000, 1_000_000)


def holdout_score(x: np.ndarray, y: np.ndarray, indices: tuple[int, ...]) -> dict[str, float]:
    """Fast chronological screen before expensive CV."""
    if not indices:
        return {"accuracy": 0.0, "auc": 0.5, "brier": 1.0}

    subset = clean_x(x[:, indices])
    split = int(len(y) * 0.72)
    train_x, test_x = subset[:split], subset[split:]
    train_y, test_y = y[:split], y[split:]

    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=350, C=0.35, solver="liblinear"),
    )
    model.fit(train_x, train_y)
    probability = model.predict_proba(test_x)[:, 1]
    predictions = (probability >= 0.5).astype(int)

    return {
        "accuracy": float(accuracy_score(test_y, predictions)),
        "auc": float(roc_auc_score(test_y, probability)),
        "brier": float(brier_score_loss(test_y, probability)),
    }


def ensemble_cv_score(x: np.ndarray, y: np.ndarray, indices: tuple[int, ...]) -> dict[str, float]:
    subset = clean_x(x[:, indices])
    splitter = TimeSeriesSplit(n_splits=5)
    probabilities: list[float] = []
    actuals: list[int] = []

    for train_idx, test_idx in splitter.split(subset):
        gbm = HistGradientBoostingClassifier(
            max_depth=4,
            learning_rate=0.035,
            max_iter=220,
            l2_regularization=0.02,
            random_state=42,
        )
        forest = RandomForestClassifier(
            n_estimators=220,
            max_depth=7,
            min_samples_leaf=18,
            random_state=43,
            n_jobs=-1,
        )
        extra = ExtraTreesClassifier(
            n_estimators=220,
            max_depth=7,
            min_samples_leaf=18,
            random_state=44,
            n_jobs=-1,
        )
        model = VotingClassifier(
            estimators=[("gbm", gbm), ("rf", forest), ("extra", extra)],
            voting="soft",
            weights=[3, 1, 1],
        )
        model.fit(subset[train_idx], y[train_idx])
        probability = model.predict_proba(subset[test_idx])[:, 1]
        probabilities.extend(probability.tolist())
        actuals.extend(y[test_idx].tolist())

    preds = [1 if value >= 0.5 else 0 for value in probabilities]
    return {
        "accuracy": float(accuracy_score(actuals, preds)),
        "auc": float(roc_auc_score(actuals, probabilities)),
        "brier": float(brier_score_loss(actuals, probabilities)),
    }


def candidate_payload(candidate: Candidate, metrics: dict[str, float], feature_names: list[str]) -> dict:
    return {
        "name": candidate.name,
        "source": candidate.source,
        "feature_count": len(candidate.indices),
        "features": [feature_names[index] for index in candidate.indices],
        **metrics,
    }


def evaluate_candidates(x: np.ndarray, y: np.ndarray, candidates: list[Candidate], feature_names: list[str], keep: int) -> list[dict]:
    scored = []
    total = len(candidates)
    for idx, candidate in enumerate(candidates, start=1):
        metrics = holdout_score(x, y, candidate.indices)
        scored.append(candidate_payload(candidate, metrics, feature_names))
        if idx % 500 == 0 or idx == total:
            print(f"candidate_progress={idx}/{total}", flush=True)

    scored.sort(key=lambda item: (item["accuracy"], item["auc"], -item["brier"]), reverse=True)
    return scored[:keep]


def build_beam_candidates(
    x: np.ndarray,
    y: np.ndarray,
    top_indices: list[int],
    feature_names: list[str],
    beam_width: int,
    max_size: int,
) -> list[dict]:
    beam: list[tuple[tuple[int, ...], dict[str, float]]] = []
    all_results: list[dict] = []

    singles = [
        Candidate(name=f"beam_single_{feature_names[index]}", indices=(index,), source="beam_single")
        for index in top_indices
    ]
    single_results = evaluate_candidates(x, y, singles, feature_names, keep=beam_width)
    for row in single_results:
        indices = tuple(feature_names.index(name) for name in row["features"])
        beam.append((indices, {key: row[key] for key in ("accuracy", "auc", "brier")}))
    all_results.extend(single_results)

    for size in range(2, max_size + 1):
        candidates: list[Candidate] = []
        seen: set[tuple[int, ...]] = set()

        for indices, _metrics in beam:
            for feature_index in top_indices:
                if feature_index in indices:
                    continue
                combo = tuple(sorted((*indices, feature_index)))
                if combo in seen:
                    continue
                seen.add(combo)
                candidates.append(
                    Candidate(
                        name=f"beam_size_{size}_{len(seen)}",
                        indices=combo,
                        source=f"beam_size_{size}",
                    )
                )

        print(f"beam_size={size} candidates={len(candidates)}")
        scored = evaluate_candidates(x, y, candidates, feature_names, keep=beam_width)
        all_results.extend(scored)
        beam = []
        for row in scored:
            indices = tuple(sorted(feature_names.index(name) for name in row["features"]))
            beam.append((indices, {key: row[key] for key in ("accuracy", "auc", "brier")}))

    all_results.sort(key=lambda item: (item["accuracy"], item["auc"], -item["brier"]), reverse=True)
    return all_results[:100]


def random_subset_candidates(top_indices: list[int], count: int, max_size: int, seed: int) -> list[Candidate]:
    rng = random.Random(seed)
    candidates = []
    seen: set[tuple[int, ...]] = set()
    sizes = [3, 4, 5, 8, 10, 15, 20, 30, 40]

    while len(candidates) < count:
        size = min(rng.choice(sizes), max_size, len(top_indices))
        combo = tuple(sorted(rng.sample(top_indices, size)))
        if combo in seen:
            continue
        seen.add(combo)
        candidates.append(Candidate(name=f"random_subset_{len(candidates)+1}", indices=combo, source="random_subset"))

    return candidates


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-n", type=int, default=200)
    parser.add_argument("--beam-width", type=int, default=16)
    parser.add_argument("--beam-max-size", type=int, default=18)
    parser.add_argument("--random-subsets", type=int, default=2000)
    parser.add_argument("--finalists", type=int, default=80)
    args = parser.parse_args()

    games = load_or_fetch_games(date(2024, 3, 20), date.today())
    dataset = build_dataset(games)
    feature_names = dataset.feature_names
    ranked = rank_individual_features(dataset, limit=None)
    name_to_index = {name: idx for idx, name in enumerate(feature_names)}
    top_features = ranked[: args.top_n]
    top_indices = [name_to_index[str(item["feature"])] for item in top_features]

    print(f"games={dataset.y.shape[0]}")
    print(f"features_total={len(feature_names)}")
    print(f"top_n={len(top_indices)}")

    print("stage=all_singles_top200")
    single_candidates = [
        Candidate(name=f"single_{feature_names[index]}", indices=(index,), source="single")
        for index in top_indices
    ]
    singles = evaluate_candidates(dataset.x, dataset.y, single_candidates, feature_names, keep=args.finalists)

    print("stage=all_pairs_top200")
    pair_candidates = [
        Candidate(name=f"pair_{i}_{j}", indices=tuple(sorted((i, j))), source="pair")
        for i, j in combinations(top_indices, 2)
    ]
    pairs = evaluate_candidates(dataset.x, dataset.y, pair_candidates, feature_names, keep=args.finalists)

    print("stage=random_subsets_top200")
    random_candidates = random_subset_candidates(
        top_indices,
        count=args.random_subsets,
        max_size=min(args.beam_max_size * 2, args.top_n),
        seed=42,
    )
    random_results = evaluate_candidates(dataset.x, dataset.y, random_candidates, feature_names, keep=args.finalists)

    print("stage=beam_search_top200")
    beam_results = build_beam_candidates(
        dataset.x,
        dataset.y,
        top_indices,
        feature_names,
        beam_width=args.beam_width,
        max_size=args.beam_max_size,
    )

    finalist_rows = singles + pairs + random_results + beam_results
    finalist_rows.sort(key=lambda item: (item["accuracy"], item["auc"], -item["brier"]), reverse=True)
    finalist_rows = finalist_rows[: args.finalists]

    print("stage=final_time_series_cv")
    validated = []
    for idx, row in enumerate(finalist_rows, start=1):
        indices = tuple(name_to_index[name] for name in row["features"])
        metrics = ensemble_cv_score(dataset.x, dataset.y, indices)
        validated.append({**row, "validated": metrics})
        print(f"finalist_progress={idx}/{len(finalist_rows)} accuracy={metrics['accuracy']:.4f}")

    validated.sort(
        key=lambda item: (
            item["validated"]["accuracy"],
            item["validated"]["auc"],
            -item["validated"]["brier"],
        ),
        reverse=True,
    )

    output = {
        "generated_at": date.today().isoformat(),
        "games": int(dataset.y.shape[0]),
        "total_features": len(feature_names),
        "top_n": args.top_n,
        "tested": {
            "singles": len(single_candidates),
            "pairs": len(pair_candidates),
            "random_subsets": len(random_candidates),
            "beam_width": args.beam_width,
            "beam_max_size": args.beam_max_size,
            "finalists_validated": len(validated),
        },
        "best_validated": validated[0] if validated else None,
        "validated_finalists": validated,
        "best_holdout_singles": singles[:20],
        "best_holdout_pairs": pairs[:20],
        "best_holdout_random_subsets": random_results[:20],
        "best_holdout_beam": beam_results[:20],
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print("stage=complete")
    if validated:
        print(f"best_validated_accuracy={validated[0]['validated']['accuracy']:.4f}")
        print(f"best_validated_features={validated[0]['feature_count']}")
        print(f"best_validated_source={validated[0]['source']}")


if __name__ == "__main__":
    main()
