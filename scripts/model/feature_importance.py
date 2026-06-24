"""Feature importance + pruning test for the live GBM.

Names every column to match trained_edge_model.feature_row order, ranks impurity
importance from a full-matrix fit, then TESTS whether dropping the lowest-importance
features actually improves out-of-sample walk-forward metrics. Trees ignore useless
features, so pruning often helps little — we only prune if the harness says so.

Usage:
  python3 scripts/model/feature_importance.py
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

from benchmark_models import build_matrix, walk_forward_predict, metrics

WINDOWS = [3, 5, 7, 10, 14, 21, 30]


def feature_names() -> list[str]:
    base = [
        "elo_prob", "home_winpct", "away_winpct", "home_winpct10", "away_winpct10",
        "home_rundiff", "away_rundiff", "home_rundiff10", "away_rundiff10",
        "home_rest", "away_rest", "home_scored10", "away_scored10", "home_allowed10", "away_allowed10",
        "home_era", "away_era", "era_away_minus_home",
        "home_ops", "away_ops", "home_obp", "away_obp", "home_slg", "away_slg",
        "home_rpg", "away_rpg", "home_hrpg", "away_hrpg", "home_krate", "away_krate",
        "home_bbrate", "away_bbrate", "home_pit_era", "away_pit_era", "home_whip", "away_whip",
        "home_ops_allowed", "away_ops_allowed", "home_k9", "away_k9", "home_bb9", "away_bb9",
        "home_hr9", "away_hr9", "home_sp_whip", "away_sp_whip", "home_sp_k9", "away_sp_k9",
        "home_sp_bb9", "away_sp_bb9", "home_sp_hr9", "away_sp_hr9", "home_sp_opsa", "away_sp_opsa",
        "home_sp_ip", "away_sp_ip", "home_off_vs_away_pit", "away_off_vs_home_pit", "off_matchup_net",
        "sp_opsa_diff", "home_streak", "away_streak", "streak_diff", "rest_diff",
        "home_pyth", "away_pyth", "pyth_diff", "pyth30_diff",
        "home_homewin", "away_awaywin", "home_away_split_diff",
        "scored_recent7_diff", "home_scored5_vs_away_allowed5", "away_scored5_vs_home_allowed5",
        "winpct5_diff", "season_rundiff_diff",
        "park_runs", "park_hr", "park_alt", "park_lf", "park_cf", "park_rf",
        "temp", "wind_speed", "wind_dir", "wind_out_cf", "humidity", "precip", "pressure", "is_dome",
        "hour", "is_day_ish", "month", "bias_const",
    ]
    for side in ("home", "away"):
        for w in WINDOWS:
            base += [f"{side}_roll{w}_winpct", f"{side}_roll{w}_rundiff", f"{side}_roll{w}_scored",
                     f"{side}_roll{w}_allowed", f"{side}_roll{w}_net"]
    for w in WINDOWS:
        base += [f"mu{w}_winpct_diff", f"mu{w}_rundiff_diff", f"mu{w}_home_off_edge",
                 f"mu{w}_away_off_edge", f"mu{w}_net"]
    base += ["sp_vet_home_vs_thin_away", "sp_vet_away_vs_thin_home", "sp_ip_diff_norm",
             "home_sp_recent_era", "away_sp_recent_era", "home_sp_era_trend", "away_sp_era_trend",
             "sp_recent_era_diff"]
    base += ["h2h_games", "h2h_home_winpct", "h2h_run_diff", "h2h_home_won_last",
             "h2h_home_lost_last_two", "h2h_none_flag"]
    base += ["home_sp_vs_away_era", "home_sp_vs_away_winpct", "away_sp_vs_home_era",
             "away_sp_vs_home_winpct", "sp_vs_opp_era_diff"]
    return base


def main() -> None:
    data = build_matrix()
    X, y, w, cur = data["X"], data["y"], data["w"], data["is_current"]
    names = feature_names()
    if len(names) != X.shape[1]:
        print(f"WARNING: {len(names)} names vs {X.shape[1]} columns — name map out of sync")

    model = GradientBoostingClassifier(n_estimators=140, learning_rate=0.035, max_depth=2,
                                       subsample=0.90, random_state=42)
    model.fit(X, y, sample_weight=w)
    imp = model.feature_importances_
    order = np.argsort(imp)[::-1]

    print(f"\nTop 20 features by importance ({X.shape[1]} total):")
    for i in order[:20]:
        nm = names[i] if i < len(names) else f"col{i}"
        print(f"  {nm:28s} {imp[i]:.4f}")

    near_zero = [i for i in range(len(imp)) if imp[i] < 0.001]
    print(f"\n{len(near_zero)} features carry <0.1% importance (candidates to prune)")
    cum = np.cumsum(imp[order])
    n95 = int(np.searchsorted(cum, 0.95) + 1)
    print(f"{n95} features carry 95% of total importance")

    # Prune test: keep top-K features, drop the rest, re-run walk-forward.
    cur_mask = cur == 1
    REFIT = 150
    base_preds = walk_forward_predict(
        lambda: GradientBoostingClassifier(n_estimators=140, learning_rate=0.035, max_depth=2,
                                           subsample=0.90, random_state=42),
        X, y, w, refit_every=REFIT)
    base_m = metrics(base_preds, y, cur_mask)
    print(f"\n(prune test at refit={REFIT})")
    print(f"{'config':18s} {'feats':>5s} {'brier':>8s} {'logloss':>9s} {'auc':>7s} {'ece':>7s}")
    print(f"{'full':18s} {X.shape[1]:>5d} {base_m['brier']:>8.4f} {base_m['log_loss']:>9.4f} {base_m['auc']:>7.4f} {base_m['ece']:>7.4f}")

    for keep in (45, 40, 35, 30):
        keep_idx = np.sort(order[:keep])
        Xk = X[:, keep_idx]
        preds = walk_forward_predict(
            lambda: GradientBoostingClassifier(n_estimators=140, learning_rate=0.035, max_depth=2,
                                               subsample=0.90, random_state=42),
            Xk, y, w, refit_every=REFIT)
        m = metrics(preds, y, cur_mask)
        flag = "  <- better" if m["log_loss"] < base_m["log_loss"] else ""
        print(f"{'top'+str(keep):18s} {keep:>5d} {m['brier']:>8.4f} {m['log_loss']:>9.4f} {m['auc']:>7.4f} {m['ece']:>7.4f}{flag}")


if __name__ == "__main__":
    main()
