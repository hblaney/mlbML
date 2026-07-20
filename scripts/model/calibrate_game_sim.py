"""Walk-forward calibrate the PA Monte Carlo win probabilities.

Leakage-safe: rates/lineups as of game date (providers end yesterday).
Fits a piecewise-linear isotonic map and writes data/model/game_sim_params.json.

Usage:
  python3 calibrate_game_sim.py [START] [END] [n_sims]
  Defaults: last ~45 days through yesterday, 1500 sims/game.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression

from game_sim import DEFAULT_N_SIMS, simulate_game
from game_sim_board import PARAMS_PATH, build_sides
from mlb_api import load_or_fetch_games

REPO_ROOT = Path(__file__).resolve().parents[2]


def _brier(probs: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((probs - y) ** 2))


def _log_loss(probs: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(probs, 1e-6, 1.0 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def collect_raw_probs(
    start: date,
    end: date,
    *,
    n_sims: int,
) -> tuple[np.ndarray, np.ndarray]:
    games = [g for g in load_or_fetch_games(start, end) if g.is_final]
    xs: list[float] = []
    ys: list[float] = []
    skipped = 0
    for i, game in enumerate(games):
        if game.home_score is None or game.away_score is None:
            skipped += 1
            continue
        built = build_sides(game)
        if built is None:
            skipped += 1
            continue
        home, away, _src = built
        result = simulate_game(home, away, n_sims=n_sims, seed=int(game.game_pk))
        xs.append(result.home_win_prob)
        ys.append(1.0 if game.home_won else 0.0)
        if (i + 1) % 25 == 0:
            print(f"  graded {i + 1}/{len(games)} raw_p={result.home_win_prob:.3f}", flush=True)
    print(f"collect_ok n={len(xs)} skipped={skipped}", flush=True)
    return np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64)


def fit_isotonic(x: np.ndarray, y: np.ndarray) -> tuple[list[float], list[float]]:
    if len(x) < 30:
        return [0.0, 0.5, 1.0], [0.0, 0.5, 1.0]
    iso = IsotonicRegression(y_min=0.02, y_max=0.98, out_of_bounds="clip")
    iso.fit(x, y)
    # Store a dense lookup on sorted unique x for piecewise linear apply.
    grid = np.linspace(0.05, 0.95, 19)
    ys = iso.predict(grid)
    # Ensure endpoints
    xs = [0.0] + [float(v) for v in grid] + [1.0]
    ys_out = [float(ys[0])] + [float(v) for v in ys] + [float(ys[-1])]
    return xs, ys_out


def apply_piecewise(x: np.ndarray, xs: list[float], ys: list[float]) -> np.ndarray:
    out = np.empty_like(x)
    for i, val in enumerate(x):
        v = float(val)
        if v <= xs[0]:
            out[i] = ys[0]
            continue
        if v >= xs[-1]:
            out[i] = ys[-1]
            continue
        for j in range(1, len(xs)):
            if v <= xs[j]:
                x0, x1 = xs[j - 1], xs[j]
                y0, y1 = ys[j - 1], ys[j]
                t = 0.0 if x1 <= x0 else (v - x0) / (x1 - x0)
                out[i] = y0 + t * (y1 - y0)
                break
    return out


def main() -> None:
    today = date.today()
    end = today - timedelta(days=1)
    start = end - timedelta(days=44)
    n_sims = 1500
    if len(sys.argv) >= 3:
        start = date.fromisoformat(sys.argv[1])
        end = date.fromisoformat(sys.argv[2])
    if len(sys.argv) >= 4:
        n_sims = int(sys.argv[3])

    print(f"calibrate_game_sim {start} → {end} n_sims={n_sims}", flush=True)
    x, y = collect_raw_probs(start, end, n_sims=n_sims)
    if len(x) < 20:
        payload = {
            "calibration": "identity",
            "x": [0.0, 0.5, 1.0],
            "y": [0.0, 0.5, 1.0],
            "n_sims_default": DEFAULT_N_SIMS,
            "holdout_n": int(len(x)),
            "note": "Insufficient games for isotonic; identity calibration",
            "tuned_on": f"{start.isoformat()}_{end.isoformat()}",
        }
        PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PARAMS_PATH.write_text(json.dumps(payload, indent=2))
        print("wrote identity params (thin sample)")
        return

    # Time-based split: first 70% train, last 30% holdout
    order = np.arange(len(x))
    cut = int(len(x) * 0.70)
    train_x, train_y = x[:cut], y[:cut]
    hold_x, hold_y = x[cut:], y[cut:]
    xs, ys = fit_isotonic(train_x, train_y)
    cal_hold = apply_piecewise(hold_x, xs, ys)
    raw_brier = _brier(hold_x, hold_y)
    cal_brier = _brier(cal_hold, hold_y)
    raw_ll = _log_loss(hold_x, hold_y)
    cal_ll = _log_loss(cal_hold, hold_y)
    market_brier = _brier(np.full_like(hold_y, 0.5), hold_y)  # coin baseline
    # Pick accuracy
    raw_acc = float(np.mean((hold_x >= 0.5) == (hold_y == 1.0)))
    cal_acc = float(np.mean((cal_hold >= 0.5) == (hold_y == 1.0)))

    # Keep isotonic only when it improves holdout Brier; else publish raw (identity).
    use_iso = cal_brier < raw_brier - 1e-4
    if not use_iso:
        xs, ys = [0.0, 0.5, 1.0], [0.0, 0.5, 1.0]
        cal_brier = raw_brier
        cal_ll = raw_ll
        cal_acc = raw_acc

    payload = {
        "calibration": "isotonic_piecewise" if use_iso else "identity",
        "architecture": "pa_monte_carlo_v1",
        "x": xs,
        "y": ys,
        "n_sims_default": DEFAULT_N_SIMS,
        "n_sims_tune": n_sims,
        "tuned_on": f"{start.isoformat()}_{end.isoformat()}",
        "train_n": int(len(train_x)),
        "holdout_n": int(len(hold_x)),
        "holdout_raw_brier": round(raw_brier, 5),
        "holdout_cal_brier": round(cal_brier, 5),
        "holdout_raw_logloss": round(raw_ll, 5),
        "holdout_cal_logloss": round(cal_ll, 5),
        "holdout_coin_brier": round(float(market_brier), 5),
        "holdout_raw_pick_acc": round(raw_acc, 4),
        "holdout_cal_pick_acc": round(cal_acc, 4),
        "isotonic_kept": use_iso,
        "mean_raw_home_prob": round(float(np.mean(x)), 4),
        "home_win_rate": round(float(np.mean(y)), 4),
    }
    PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PARAMS_PATH.write_text(json.dumps(payload, indent=2))
    print(json.dumps({k: payload[k] for k in payload if k not in ("x", "y")}, indent=2))
    print(f"wrote {PARAMS_PATH}")


if __name__ == "__main__":
    main()
