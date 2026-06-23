"""Nightly model-health check + harness-validated recalibration gate (Step 5).

Runs after the board/history refresh. Two jobs:

1. HEALTH: compute rolling out-of-sample metrics (accuracy, brier, log-loss, AUC,
   ECE) on the live probability over recent windows and grade them against fixed
   quality gates. This is the trip-wire that catches silent drift — if the model
   stops being calibrated or stops discriminating, the status drops to "watch" or
   "degraded" and it shows on the site instead of failing quietly.

2. RECALIBRATION (validated): fit a Platt recalibrator on the older portion of the
   season and test it on a held-out recent portion. Only RECOMMEND applying it if it
   actually beats the raw probability on BOTH log-loss and ECE on that holdout. The
   model already ships raw (no display inflation), so the expected — and healthy —
   answer is "none: raw is well-calibrated". This guarantees we never bolt on a
   calibration layer that the harness can't justify.

Writes public/model-health.json and prints a summary.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from model_metrics import evaluate

ROOT = Path(__file__).resolve().parents[2]
HISTORY_PATH = ROOT / "public" / "prediction-history.json"
OUT_PATH = ROOT / "public" / "model-health.json"

LIVE_KEY = "rawPickProbability"

# Quality gates (graded on the primary recent window).
ECE_HEALTHY = 0.06
ECE_WATCH = 0.10
AUC_MIN = 0.54
ACC_MIN = 0.51
LOGLOSS_MAX = 0.690  # always-0.5 baseline is ~0.693

# Recalibration is only recommended if it clears these margins on the holdout.
RECAL_LOGLOSS_MARGIN = 0.003
RECAL_ECE_MARGIN = 0.005

_EPS = 1e-6


def _load_graded() -> list[dict]:
    payload = json.loads(HISTORY_PATH.read_text())
    rows = payload.get("predictions", payload if isinstance(payload, list) else [])
    graded = [r for r in rows if r.get("correct") in (0, 1) and r.get(LIVE_KEY) is not None]
    graded.sort(key=lambda r: (str(r.get("date", "")), str(r.get("startsAt", ""))))
    return graded


def _clip(p: float) -> float:
    return min(max(float(p), _EPS), 1.0 - _EPS)


def _logit(p: float) -> float:
    p = _clip(p)
    return math.log(p / (1.0 - p))


def _grade_window(rows: list[dict]) -> dict:
    m = evaluate(rows, LIVE_KEY)
    ece, auc, acc, ll = m["ece"], m["auc"], m["accuracy"], m["log_loss"]
    auc_ok = (not math.isnan(auc)) and auc >= AUC_MIN
    gates = {
        "ece_ok": ece <= ECE_WATCH,
        "auc_ok": auc_ok,
        "acc_ok": acc >= ACC_MIN,
        "logloss_ok": ll <= LOGLOSS_MAX,
    }
    if ece <= ECE_HEALTHY and auc_ok and acc >= ACC_MIN and ll <= LOGLOSS_MAX:
        status = "healthy"
    elif ece <= ECE_WATCH and auc_ok:
        status = "watch"
    else:
        status = "degraded"
    return {**m, "gates": gates, "status": status}


def _recalibration_check(rows: list[dict]) -> dict:
    """Fit Platt on older 70%, test raw vs recalibrated on newer 30%."""
    n = len(rows)
    if n < 200:
        return {"verdict": "insufficient_data", "n": n}
    cut = int(n * 0.70)
    train, test = rows[:cut], rows[cut:]

    x_tr = np.array([[_logit(r[LIVE_KEY])] for r in train])
    y_tr = np.array([int(r["correct"]) for r in train])
    if len(set(y_tr.tolist())) < 2:
        return {"verdict": "insufficient_data", "n": n}

    platt = LogisticRegression(C=1e6, solver="lbfgs")
    platt.fit(x_tr, y_tr)

    def _ll_ece(probs: list[float], ys: list[int]) -> tuple[float, float]:
        ll = -sum(y * math.log(_clip(p)) + (1 - y) * math.log(1 - _clip(p)) for p, y in zip(probs, ys)) / len(ys)
        edges = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 1.01]
        ece = 0.0
        for lo, hi in zip(edges[:-1], edges[1:]):
            idx = [i for i, p in enumerate(probs) if lo <= p < hi]
            if not idx:
                continue
            mp = sum(probs[i] for i in idx) / len(idx)
            ac = sum(ys[i] for i in idx) / len(idx)
            ece += (len(idx) / len(probs)) * abs(mp - ac)
        return ll, ece

    ys = [int(r["correct"]) for r in test]
    raw_probs = [_clip(r[LIVE_KEY]) for r in test]
    recal_probs = [float(platt.predict_proba([[_logit(r[LIVE_KEY])]])[0, 1]) for r in test]

    raw_ll, raw_ece = _ll_ece(raw_probs, ys)
    recal_ll, recal_ece = _ll_ece(recal_probs, ys)

    helps = (raw_ll - recal_ll) >= RECAL_LOGLOSS_MARGIN and (raw_ece - recal_ece) >= RECAL_ECE_MARGIN
    return {
        "verdict": "apply_platt" if helps else "none_raw_is_calibrated",
        "holdout_n": len(test),
        "raw_log_loss": round(raw_ll, 4),
        "recal_log_loss": round(recal_ll, 4),
        "raw_ece": round(raw_ece, 4),
        "recal_ece": round(recal_ece, 4),
        "platt_slope": round(float(platt.coef_[0][0]), 4),
        "platt_intercept": round(float(platt.intercept_[0]), 4),
    }


def build() -> dict:
    graded = _load_graded()
    windows = {
        "last100": graded[-100:],
        "last250": graded[-250:],
        "season": graded,
    }
    graded_windows = {name: _grade_window(rows) for name, rows in windows.items() if rows}
    # Grade overall on the largest stable window available. AUC/ECE on tiny windows
    # (30-60 binary outcomes) is dominated by variance and would false-alarm nightly.
    primary = (graded_windows.get("last250")
               if len(graded) >= 250 else graded_windows.get("season"))
    recal = _recalibration_check(graded)

    # Informational recent-form trend (not a hard gate — too small to grade on).
    recent = graded[-30:]
    recent_acc = round(sum(int(r["correct"]) for r in recent) / len(recent), 4) if recent else None
    season_acc = graded_windows["season"]["accuracy"] if "season" in graded_windows else None

    # Bettable tier: High/Elite picks are what the live strategy uses — all-picks last-30
    # often has zero H/E and misleads (e.g. 43% when only Low/Medium games graded recently).
    bettable = [r for r in graded if r.get("confidence") in ("High", "Elite")]
    recent_bettable = bettable[-30:]
    recent_bettable_acc = (
        round(sum(int(r["correct"]) for r in recent_bettable) / len(recent_bettable), 4)
        if recent_bettable
        else None
    )
    season_bettable_acc = (
        round(sum(int(r["correct"]) for r in bettable) / len(bettable), 4) if bettable else None
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "live_probability_key": LIVE_KEY,
        "overall_status": primary["status"] if primary else "unknown",
        "recent_trend": {
            "last30_accuracy": recent_acc,
            "last30_high_elite_accuracy": recent_bettable_acc,
            "last30_high_elite_n": len(recent_bettable),
            "season_accuracy": season_acc,
            "season_high_elite_accuracy": season_bettable_acc,
            "season_high_elite_n": len(bettable),
            "note": (
                "Last-30 all-picks is trend-only and includes Low/Medium games we do not bet. "
                "Use last30_high_elite for live-strategy form."
            ),
        },
        "gates_def": {
            "ece_healthy": ECE_HEALTHY, "ece_watch": ECE_WATCH,
            "auc_min": AUC_MIN, "acc_min": ACC_MIN, "logloss_max": LOGLOSS_MAX,
        },
        "windows": graded_windows,
        "recalibration": recal,
        "note": (
            "Health is graded on the largest stable window (trailing 250 picks). "
            "Recalibration is only "
            "recommended when a Platt fit beats the raw probability on both log-loss "
            "and ECE on a held-out recent split; otherwise the raw model ships as-is."
        ),
    }


def main() -> None:
    health = build()
    OUT_PATH.write_text(json.dumps(health, indent=2))
    print(f"overall_status: {health['overall_status']}")
    for name, w in health["windows"].items():
        print(f"  {name:7s} n={w['n']:>4d} acc={w['accuracy']:.3f} "
              f"logloss={w['log_loss']:.4f} auc={w['auc']:.4f} ece={w['ece']:.4f} -> {w['status']}")
    r = health["recalibration"]
    print(f"recalibration: {r['verdict']}"
          + (f" (raw ll {r['raw_log_loss']} vs platt {r['recal_log_loss']}, "
             f"raw ece {r['raw_ece']} vs platt {r['recal_ece']})" if "raw_log_loss" in r else ""))


if __name__ == "__main__":
    main()
