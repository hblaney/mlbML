"""Controlled before/after for the starting-pitcher leakage fix.

Builds two chronological feature matrices that differ ONLY in how starter stats
are sourced:
  - leaked : fetch_pitcher_season_stats (full FINAL-season line — lookahead)
  - honest : pitcher_stats_as_of (point-in-time, shrunk to prior season)

then runs the identical production walk-forward (GBM 140/0.035/depth-2, top-35
features) on each and prints OOS metrics. A drop in "accuracy" on the leaked
config is expected and good — those numbers were inflated by future information.
What matters is that the honest model stays well-calibrated and above baseline.

Usage:
  python3 scripts/model/experiment_pitcher_leakage.py
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

import trained_edge_model as tem
import benchmark_models as bm
from mlb_api import fetch_pitcher_season_stats

REFIT = 150


def _leaked_stats(game, pitcher_id):
    """Old behaviour: full final-season line regardless of game date."""
    if not pitcher_id:
        return {
            "era": 4.35, "whip": 1.3, "avg_allowed": 0.250, "obp_allowed": 0.320,
            "slg_allowed": 0.400, "ops_allowed": 0.720, "strikeouts_per_9": 8.0,
            "walks_per_9": 3.0, "hits_per_9": 8.5, "home_runs_per_9": 1.1,
            "innings_pitched": 0.0, "games_started": 0.0,
        }
    try:
        return fetch_pitcher_season_stats(pitcher_id, game.game_date.year)
    except Exception:
        return _leaked_stats(game, None)


def _make_model():
    return GradientBoostingClassifier(
        n_estimators=140, learning_rate=0.035, max_depth=2, subsample=0.90, random_state=42
    )


def _evaluate(label: str, data: dict) -> None:
    X, y, w, cur = data["X"], data["y"], data["w"], data["is_current"]
    sel = np.array(tem.SELECTED_FEATURE_INDICES)
    Xk = X[:, sel] if X.shape[1] == 213 else X
    preds = bm.walk_forward_predict(_make_model, Xk, y, w, refit_every=REFIT)
    cur_mask = cur == 1
    all_mask = np.ones(len(y), dtype=bool)
    m_cur = bm.metrics(preds, y, cur_mask)
    m_all = bm.metrics(preds, y, all_mask)
    print(f"\n=== {label} ===")
    print(f"  current-season OOS  n={m_cur['n']:5d}  acc={m_cur['acc']:.4f}  "
          f"logloss={m_cur['log_loss']:.4f}  auc={m_cur['auc']:.4f}  ece={m_cur['ece']:.4f}")
    print(f"  all-games     OOS  n={m_all['n']:5d}  acc={m_all['acc']:.4f}  "
          f"logloss={m_all['log_loss']:.4f}  auc={m_all['auc']:.4f}  ece={m_all['ece']:.4f}")


def main() -> None:
    print("Building LEAKED matrix (full-season pitcher stats)...")
    original = tem._safe_pitcher_stats
    tem._safe_pitcher_stats = _leaked_stats
    try:
        leaked = bm.build_matrix(rebuild=True)
    finally:
        tem._safe_pitcher_stats = original

    print("\nBuilding HONEST matrix (point-in-time pitcher stats)...")
    honest = bm.build_matrix(rebuild=True)  # cache ends on the honest (production) matrix

    _evaluate("LEAKED  (full-season — lookahead)", leaked)
    _evaluate("HONEST  (point-in-time)", honest)


if __name__ == "__main__":
    main()
