"""Fit per-prop isotonic calibration from walk-forward backtest records.

Reads data/prop_backtest_records.json (raw (pred, outcome) pairs produced by
backtest_prop_projections.py with the `dump` flag) and fits a monotonic
raw_prob -> P(actual over) mapping per prop family, plus a pooled default.

Writes data/prop_calibration.json consumed by prop_calibration.calibrate().
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression

REPO_ROOT = Path(__file__).resolve().parents[2]
RECORDS = REPO_ROOT / "data" / "prop_backtest_records.json"
OUT = REPO_ROOT / "data" / "prop_calibration.json"

MIN_SAMPLES = 200   # need enough out-of-sample points to trust a per-prop curve
# Pitcher props are rarer (~2 starters/game); accept a smaller but still useful n.
MIN_SAMPLES_PITCHER = 100
KNOTS = 21          # sampled points of the fitted curve stored for interpolation


def _min_n(prop: str) -> int:
    return MIN_SAMPLES_PITCHER if prop.startswith("pitcher_") else MIN_SAMPLES


def _fit_curve(pred: np.ndarray, out: np.ndarray, min_n: int = MIN_SAMPLES) -> dict | None:
    if len(pred) < min_n:
        return None
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(pred, out)
    xs = np.linspace(0.0, 1.0, KNOTS)
    ys = iso.predict(xs)
    return {"x": [round(float(x), 4) for x in xs],
            "y": [round(float(y), 4) for y in ys],
            "n": int(len(pred))}


def main() -> None:
    raw = json.loads(RECORDS.read_text())

    # group by prop family (strip the |line suffix)
    by_prop: dict[str, list[tuple[float, int]]] = defaultdict(list)
    all_rows: list[tuple[float, int]] = []
    for key, rows in raw.items():
        prop = key.split("|", 1)[0]
        for p, o in rows:
            by_prop[prop].append((float(p), int(o)))
            all_rows.append((float(p), int(o)))

    table: dict[str, dict] = {}

    # pooled default
    if all_rows:
        pred = np.array([r[0] for r in all_rows])
        out = np.array([r[1] for r in all_rows])
        default = _fit_curve(pred, out)
        if default:
            table["_default"] = default

    for prop, rows in by_prop.items():
        pred = np.array([r[0] for r in rows])
        out = np.array([r[1] for r in rows])
        curve = _fit_curve(pred, out, min_n=_min_n(prop))
        if curve:
            table[prop] = curve
            base = out.mean()
            mean_pred = pred.mean()
            print(f"{prop:26s} n={len(rows):6d} raw_mean={mean_pred:.3f} actual={base:.3f} "
                  f"bias={mean_pred - base:+.3f} -> calibrated")
        else:
            print(f"{prop:26s} n={len(rows):6d} (too few — left uncalibrated)")

    OUT.write_text(json.dumps(table, indent=2))
    try:
        from prop_calibration import reload
        reload()
    except Exception:
        pass
    print(f"\nwrote {OUT} with {len(table)} curves")


if __name__ == "__main__":
    main()
