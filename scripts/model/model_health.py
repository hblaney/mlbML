"""Nightly model-health check + harness-validated recalibration gate (Step 5).

Runs after the board/history refresh. Two jobs:

1. HEALTH: grade the live model on BETTABLE picks (Medium / High / Elite), not on
   Low coin-flip games the strategy should not bet. Low-confidence noise was
   falsely marking overall_status "degraded" while season Medium+ stayed healthy.
   All-picks windows are still published as diagnostics.

2. RECALIBRATION (validated): fit a Platt recalibrator on the older portion of the
   season and test it on a held-out recent portion. Only RECOMMEND applying it if it
   actually beats the raw probability on BOTH log-loss and ECE on that holdout.

Writes public/model-health.json and prints a summary.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from model_metrics import evaluate

ROOT = Path(__file__).resolve().parents[2]
HISTORY_PATH = ROOT / "public" / "prediction-history.json"
OUT_PATH = ROOT / "public" / "model-health.json"

LIVE_KEY = "rawPickProbability"
BETTABLE_CONFIDENCE = {"Medium", "High", "Elite"}

# Quality gates (graded on the primary bettable window).
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


def _bettable(rows: list[dict]) -> list[dict]:
    """Picks the live product should care about — excludes Low coin-flips."""
    return [r for r in rows if r.get("confidence") in BETTABLE_CONFIDENCE]


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


def _window_set(rows: list[dict]) -> dict[str, dict]:
    windows = {
        "last100": rows[-100:],
        "last250": rows[-250:],
        "season": rows,
    }
    return {name: _grade_window(chunk) for name, chunk in windows.items() if chunk}


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


def _calendar_window(rows: list[dict], days: int, *, as_of: date | None = None) -> list[dict]:
    if not rows and as_of is None:
        return []
    latest = as_of
    if latest is None:
        latest = date.fromisoformat(str(rows[-1]["date"])[:10])
    cutoff = (latest - timedelta(days=days - 1)).isoformat()
    return [r for r in rows if str(r.get("date", ""))[:10] >= cutoff]


def build() -> dict:
    graded = _load_graded()
    bettable = _bettable(graded)

    windows_all = _window_set(graded)
    windows_bettable = _window_set(bettable)

    # Overall status = season Medium+ when available (stable, excludes Low trash).
    # Recent bettable last250 is published separately for drift monitoring.
    season_bettable = windows_bettable.get("season")
    recent_bettable = (
        windows_bettable.get("last250")
        if len(bettable) >= 250
        else windows_bettable.get("season")
    )
    if season_bettable and season_bettable["status"] == "healthy":
        overall = "healthy"
        primary_name = "season_bettable"
    elif recent_bettable:
        overall = recent_bettable["status"]
        primary_name = "last250_bettable" if len(bettable) >= 250 else "season_bettable"
    else:
        overall = windows_all.get("season", {}).get("status", "unknown")
        primary_name = "season_all_picks"

    recal = _recalibration_check(bettable if len(bettable) >= 200 else graded)

    recent_all = graded[-30:]
    recent_acc = round(sum(int(r["correct"]) for r in recent_all) / len(recent_all), 4) if recent_all else None
    season_acc = windows_all["season"]["accuracy"] if "season" in windows_all else None

    # Calendar last-30 High/Elite relative to latest graded game date (not last H/E ever).
    he_all = [r for r in graded if r.get("confidence") in ("High", "Elite")]
    as_of = date.fromisoformat(str(graded[-1]["date"])[:10]) if graded else None
    he_calendar = _calendar_window(he_all, 30, as_of=as_of)
    recent_he_acc = (
        round(sum(int(r["correct"]) for r in he_calendar) / len(he_calendar), 4) if he_calendar else None
    )
    season_he_acc = round(sum(int(r["correct"]) for r in he_all) / len(he_all), 4) if he_all else None

    # Keep `windows` as the primary (bettable) set so existing UI keeps working.
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "live_probability_key": LIVE_KEY,
        "overall_status": overall,
        "primary_universe": "medium_plus",
        "primary_window": primary_name,
        "recent_status": recent_bettable["status"] if recent_bettable else None,
        "recent_trend": {
            "last30_accuracy": recent_acc,
            "last30_high_elite_accuracy": recent_he_acc,
            "last30_high_elite_n": len(he_calendar),
            "season_accuracy": season_acc,
            "season_high_elite_accuracy": season_he_acc,
            "season_high_elite_n": len(he_all),
            "note": (
                "Overall status grades Medium/High/Elite only — Low coin-flips are excluded. "
                "last30_high_elite is calendar last-30 days of High/Elite (0 when none fired)."
            ),
        },
        "gates_def": {
            "ece_healthy": ECE_HEALTHY,
            "ece_watch": ECE_WATCH,
            "auc_min": AUC_MIN,
            "acc_min": ACC_MIN,
            "logloss_max": LOGLOSS_MAX,
        },
        "windows": windows_bettable,
        "windows_all_picks": windows_all,
        "recalibration": recal,
        "note": (
            "Overall status is graded on Medium+ picks (excludes Low). "
            "windows_all_picks keeps the all-confidence diagnostic. "
            "Recalibration only applies when Platt beats raw on holdout log-loss and ECE."
        ),
    }


def main() -> None:
    health = build()
    OUT_PATH.write_text(json.dumps(health, indent=2))
    print(f"overall_status: {health['overall_status']} (universe={health['primary_universe']}, window={health['primary_window']})")
    print("bettable windows:")
    for name, w in health["windows"].items():
        print(
            f"  {name:7s} n={w['n']:>4d} acc={w['accuracy']:.3f} "
            f"logloss={w['log_loss']:.4f} auc={w['auc']:.4f} ece={w['ece']:.4f} -> {w['status']}"
        )
    print("all-picks diagnostic:")
    for name, w in health["windows_all_picks"].items():
        print(
            f"  {name:7s} n={w['n']:>4d} acc={w['accuracy']:.3f} "
            f"logloss={w['log_loss']:.4f} auc={w['auc']:.4f} ece={w['ece']:.4f} -> {w['status']}"
        )
    r = health["recalibration"]
    print(
        f"recalibration: {r['verdict']}"
        + (
            f" (raw ll {r['raw_log_loss']} vs platt {r['recal_log_loss']}, "
            f"raw ece {r['raw_ece']} vs platt {r['recal_ece']})"
            if "raw_log_loss" in r
            else ""
        )
    )


if __name__ == "__main__":
    main()
