"""Walk-forward model benchmark — pick the model by out-of-sample metrics, not vibes.

Extracts the chronological feature matrix once (cached to npz), then evaluates each
candidate classifier under the SAME walk-forward protocol the live model uses
(warmup 180, refit every 30, recency-weighted samples). Scores raw home-win
probability quality with log-loss / Brier / AUC / ECE / accuracy.

We only adopt a new model if it beats the current GradientBoostingClassifier
out-of-sample. HistGradientBoostingClassifier is sklearn's histogram booster
(LightGBM-class) and needs no new dependency.

Usage:
  python3 scripts/model/benchmark_models.py            # build matrix (cached) + compare
  python3 scripts/model/benchmark_models.py --rebuild  # force matrix rebuild
"""

from __future__ import annotations

import argparse
import math
from datetime import date
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, HistGradientBoostingClassifier

from mlb_api import load_or_fetch_games
from team_tracker import LeagueState
from trained_edge_model import (
    CURRENT_SEASON_SAMPLE_WEIGHT,
    PRIOR_SEASON_SAMPLE_WEIGHT,
    REFIT_EVERY,
    WARMUP_GAMES,
    _clean_matrix,
    feature_row,
)

ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "data" / "model" / "feature_matrix.npz"


def _season_bounds(year: int) -> tuple[date, date]:
    return date(year, 3, 20), date(year, 10, 5)


def build_matrix(rebuild: bool = False) -> dict:
    if MATRIX_PATH.exists() and not rebuild:
        data = np.load(MATRIX_PATH, allow_pickle=True)
        print(f"loaded cached matrix: {data['X'].shape[0]} games x {data['X'].shape[1]} features")
        return {k: data[k] for k in data.files}

    today = date.today()
    cur_year = today.year
    prior_year = cur_year - 1
    prior = load_or_fetch_games(*_season_bounds(prior_year))
    cur_start, _ = _season_bounds(cur_year)
    current = load_or_fetch_games(cur_start, today)
    stream = [(g, PRIOR_SEASON_SAMPLE_WEIGHT, 0) for g in prior] + \
             [(g, CURRENT_SEASON_SAMPLE_WEIGHT, 1) for g in current]
    print(f"replaying {len(prior)} prior + {len(current)} current games for features...")

    league = LeagueState()
    feats: list[list[float]] = []
    labels: list[int] = []
    weights: list[float] = []
    is_current: list[int] = []
    for i, (game, weight, cur_flag) in enumerate(stream):
        feats.append(feature_row(game, league))
        labels.append(1 if game.home_won else 0)
        weights.append(weight)
        is_current.append(cur_flag)
        league.apply_result(game.game_date, game.home_team_id, game.away_team_id, game.home_score, game.away_score)
        if (i + 1) % 250 == 0:
            print(f"  {i + 1}/{len(stream)}")

    X = _clean_matrix(np.array(feats, dtype=float))
    y = np.array(labels, dtype=int)
    w = np.array(weights, dtype=float)
    cur = np.array(is_current, dtype=int)
    MATRIX_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(MATRIX_PATH, X=X, y=y, w=w, is_current=cur)
    print(f"cached matrix: {X.shape[0]} games x {X.shape[1]} features -> {MATRIX_PATH.name}")
    return {"X": X, "y": y, "w": w, "is_current": cur}


def walk_forward_predict(make_model, X, y, w, refit_every: int = REFIT_EVERY) -> np.ndarray:
    """Return home-win probability for each game using the live walk-forward protocol.
    Refit every `refit_every` games on all prior data; predict the block of games up to
    the next refit in one call (same predictions as single-row, far faster). Pre-warmup
    games get NaN and are excluded from scoring."""
    n = len(y)
    preds = np.full(n, np.nan)
    # Fit points: first at WARMUP_GAMES, then every refit_every.
    fit_points = list(range(WARMUP_GAMES, n, refit_every))
    for k, start in enumerate(fit_points):
        if len(set(y[:start].tolist())) < 2:
            continue
        model = make_model()
        model.fit(X[:start], y[:start], sample_weight=w[:start])
        end = fit_points[k + 1] if k + 1 < len(fit_points) else n
        preds[start:end] = model.predict_proba(X[start:end])[:, 1]
    return preds


def metrics(preds, y, mask) -> dict:
    idx = np.where(mask & ~np.isnan(preds))[0]
    p = np.clip(preds[idx], 1e-6, 1 - 1e-6)
    yy = y[idx]
    brier = float(np.mean((p - yy) ** 2))
    ll = float(np.mean(-(yy * np.log(p) + (1 - yy) * np.log(1 - p))))
    acc = float(np.mean((p >= 0.5).astype(int) == yy))
    # AUC
    order = np.argsort(p)
    ranks = np.empty(len(p)); ranks[order] = np.arange(1, len(p) + 1)
    npos = int(yy.sum()); nneg = len(yy) - npos
    auc = float((ranks[yy == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg)) if npos and nneg else float("nan")
    # ECE
    edges = np.linspace(0.3, 0.8, 11)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi)
        if m.sum():
            ece += m.sum() / len(p) * abs(p[m].mean() - yy[m].mean())
    return {"n": len(idx), "acc": acc, "brier": brier, "log_loss": ll, "auc": auc, "ece": ece}


CANDIDATES = {
    # HistGBM (sklearn histogram booster, LightGBM-class, no new dependency) — fast, run first.
    "HistGBM(lr.05,leaf31,l2=1)": lambda: HistGradientBoostingClassifier(
        learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0,
        max_iter=300, early_stopping=False, random_state=42
    ),
    "HistGBM(lr.03,leaf15,l2=2)": lambda: HistGradientBoostingClassifier(
        learning_rate=0.03, max_leaf_nodes=15, l2_regularization=2.0,
        max_iter=250, early_stopping=False, random_state=42
    ),
    "HistGBM(lr.02,depth3,l2=3)": lambda: HistGradientBoostingClassifier(
        learning_rate=0.02, max_depth=3, max_leaf_nodes=8, l2_regularization=3.0,
        max_iter=300, early_stopping=False, random_state=42
    ),
    "HistGBM(lr.04,leaf15,l2=2,iter250)": lambda: HistGradientBoostingClassifier(
        learning_rate=0.04, max_leaf_nodes=15, l2_regularization=2.0,
        max_iter=250, early_stopping=False, random_state=42
    ),
    # current model last (sklearn GBM is slow under walk-forward refitting).
    "current_GBM(d2,n140,lr.035)": lambda: GradientBoostingClassifier(
        n_estimators=140, learning_rate=0.035, max_depth=2, subsample=0.90, random_state=42
    ),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--refit", type=int, default=90)
    args = ap.parse_args()
    data = build_matrix(rebuild=args.rebuild)
    X, y, w, cur = data["X"], data["y"], data["w"], data["is_current"]
    current_mask = cur == 1

    bench_refit = args.refit
    print(f"\nScoring on current-season games (the live-relevant set). warmup={WARMUP_GAMES} refit={bench_refit}\n")
    print(f"{'model':32s} {'n':>5s} {'acc':>7s} {'brier':>8s} {'logloss':>9s} {'auc':>7s} {'ece':>7s}")
    results = {}
    for name, factory in CANDIDATES.items():
        preds = walk_forward_predict(factory, X, y, w, refit_every=bench_refit)
        m = metrics(preds, y, current_mask)
        results[name] = m
        print(f"{name:32s} {m['n']:>5d} {m['acc']:>7.4f} {m['brier']:>8.4f} {m['log_loss']:>9.4f} {m['auc']:>7.4f} {m['ece']:>7.4f}")

    base = results["current_GBM(d2,n140,lr.035)"]
    best = min(results.items(), key=lambda kv: kv[1]["log_loss"])
    print(f"\nbest by log-loss: {best[0]} ({best[1]['log_loss']:.4f} vs current {base['log_loss']:.4f})")
    if best[0] != "current_GBM(d2,n140,lr.035)" and best[1]["log_loss"] < base["log_loss"] - 0.0005:
        print("=> candidate beats current out-of-sample; worth adopting.")
    else:
        print("=> no candidate clears the bar; keep current model.")


if __name__ == "__main__":
    main()
