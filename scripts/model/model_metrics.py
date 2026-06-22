"""Standard ML + betting evaluation harness for the MLB model.

This is the source of truth for whether a model change is actually an improvement.
Every change to the model/calibration should be judged on these metrics, not on
hit rate alone or on cosmetic display numbers.

Metrics:
  - Accuracy        : raw correct-pick rate (baseline sanity)
  - Brier score     : mean squared error of probabilities (lower = better)
  - Log loss        : penalises confident wrong picks (lower = better)
  - AUC             : ranking/discrimination power (0.5 = coin flip)
  - ECE             : expected calibration error (|predicted - actual|, lower = better)
  - Calibration tbl : predicted-probability bin vs actual win rate
  - ROI (optional)  : flat-stake return if moneylines are present

Usage:
  python3 scripts/model/model_metrics.py
  python3 scripts/model/model_metrics.py --prob-key rawPickProbability
  python3 scripts/model/model_metrics.py --since 2026-03-20
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HISTORY_PATH = ROOT / "public" / "prediction-history.json"

_EPS = 1e-6


def _load_rows(since: str | None) -> list[dict]:
    payload = json.loads(HISTORY_PATH.read_text())
    rows = payload.get("predictions", payload if isinstance(payload, list) else [])
    out = []
    for r in rows:
        if r.get("correct") not in (0, 1):
            continue
        if since and str(r.get("date", "")) < since:
            continue
        out.append(r)
    return out


def _clip(p: float) -> float:
    return min(max(float(p), _EPS), 1.0 - _EPS)


def accuracy(rows: list[dict]) -> float:
    return sum(int(r["correct"]) for r in rows) / len(rows)


def brier(rows: list[dict], key: str) -> float:
    return sum((_clip(r[key]) - int(r["correct"])) ** 2 for r in rows) / len(rows)


def log_loss(rows: list[dict], key: str) -> float:
    total = 0.0
    for r in rows:
        p = _clip(r[key])
        y = int(r["correct"])
        total += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return total / len(rows)


def auc(rows: list[dict], key: str) -> float:
    """Mann-Whitney U / rank-based AUC of pick-prob vs correct outcome."""
    ps = [( _clip(r[key]), int(r["correct"]) ) for r in rows]
    ps.sort(key=lambda t: t[0])
    npos = sum(1 for _, y in ps if y == 1)
    nneg = len(ps) - npos
    if npos == 0 or nneg == 0:
        return float("nan")
    # average ranks for ties
    rank_sum_pos = 0.0
    i = 0
    n = len(ps)
    while i < n:
        j = i
        while j < n and ps[j][0] == ps[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0  # ranks are 1-indexed
        for k in range(i, j):
            if ps[k][1] == 1:
                rank_sum_pos += avg_rank
        i = j
    return (rank_sum_pos - npos * (npos + 1) / 2.0) / (npos * nneg)


def calibration_table(rows: list[dict], key: str, edges: list[float]) -> tuple[list[dict], float]:
    table = []
    ece = 0.0
    n_total = len(rows)
    for lo, hi in zip(edges[:-1], edges[1:]):
        sub = [r for r in rows if lo <= float(r[key]) < hi]
        if not sub:
            continue
        mean_pred = sum(float(r[key]) for r in sub) / len(sub)
        actual = sum(int(r["correct"]) for r in sub) / len(sub)
        table.append({
            "lo": lo, "hi": hi, "n": len(sub),
            "mean_pred": round(mean_pred, 4),
            "actual": round(actual, 4),
            "gap": round(mean_pred - actual, 4),
        })
        ece += (len(sub) / n_total) * abs(mean_pred - actual)
    return table, ece


def roi_flat(rows: list[dict]) -> float | None:
    """Flat $1 stake ROI using stored moneyline of the picked side, if present."""
    staked = 0.0
    ret = 0.0
    for r in rows:
        ml = r.get("pickMoneyline") or r.get("moneyline")
        if ml is None:
            continue
        staked += 1.0
        if int(r["correct"]) == 1:
            ret += (ml / 100.0) if ml > 0 else (100.0 / -ml)
    if staked == 0:
        return None
    return (ret - staked) / staked


def evaluate(rows: list[dict], key: str) -> dict:
    cal_edges = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 1.01]
    table, ece = calibration_table(rows, key, cal_edges)
    return {
        "key": key,
        "n": len(rows),
        "accuracy": round(accuracy(rows), 4),
        "brier": round(brier(rows, key), 4),
        "log_loss": round(log_loss(rows, key), 4),
        "auc": round(auc(rows, key), 4),
        "ece": round(ece, 4),
        "calibration": table,
    }


def _print_report(rows: list[dict], keys: list[str]) -> None:
    print(f"Evaluated on {len(rows)} graded predictions\n")
    print(f"{'metric':12s} " + " ".join(f"{k:>22s}" for k in keys))
    results = {k: evaluate(rows, k) for k in keys if rows and k in rows[0]}
    for metric in ("accuracy", "brier", "log_loss", "auc", "ece"):
        line = f"{metric:12s} " + " ".join(f"{results[k][metric]:>22.4f}" for k in results)
        print(line)
    print("\n(brier/log_loss/ece: lower is better · auc/accuracy: higher is better)\n")
    for k in results:
        print(f"Calibration table — {k}:")
        print(f"  {'bin':14s} {'n':>6s} {'shown':>8s} {'actual':>8s} {'gap':>8s}")
        for b in results[k]["calibration"]:
            print(f"  {b['lo']:.2f}-{b['hi']:.2f}    {b['n']:>6d} {b['mean_pred']:>8.3f} {b['actual']:>8.3f} {b['gap']:>+8.3f}")
        print()
    roi = roi_flat(rows)
    if roi is not None:
        print(f"Flat-stake ROI (picked side ML): {roi:+.3%}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prob-key", default=None, help="Single probability key to evaluate")
    ap.add_argument("--since", default=None, help="Only rows on/after this YYYY-MM-DD")
    args = ap.parse_args()
    rows = _load_rows(args.since)
    if not rows:
        print("No graded rows found.")
        return
    keys = [args.prob_key] if args.prob_key else ["rawPickProbability", "pickProbability"]
    _print_report(rows, keys)


if __name__ == "__main__":
    main()
