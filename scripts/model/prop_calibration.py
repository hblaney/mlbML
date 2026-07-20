"""Empirical calibration for prop projections, fit from walk-forward backtests.

The parametric projections (binomial for hits, Poisson for total bases / K / outs)
are systematically overconfident on overs — the walk-forward backtest shows the
model predicting ~10-14 points too high. Rather than hand-tune each formula, we
learn a monotonic mapping raw_prob -> calibrated_prob per prop family from real
out-of-sample results (isotonic regression), and apply it before anything else
consumes the probability.

- fit is done offline by fit_prop_calibration.py -> data/prop_calibration.json
- calibrate(prop, p) linearly interpolates that mapping; identity if unavailable.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CALIB_PATH = REPO_ROOT / "data" / "prop_calibration.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    try:
        return json.loads(CALIB_PATH.read_text())
    except Exception:
        return {}


def reload() -> None:
    """Clear the in-process cache after rewriting the calibration file."""
    _load.cache_clear()


def _interp(x: float, xs: list[float], ys: list[float]) -> float:
    if not xs:
        return x
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            x0, x1 = xs[i - 1], xs[i]
            y0, y1 = ys[i - 1], ys[i]
            if x1 == x0:
                return y1
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return ys[-1]


def calibrate(prop: str, raw_prob: float) -> float:
    """Map a raw model P(over) to its calibrated value for this prop family.

    Uses ONLY a curve fit from that prop's own out-of-sample results. We do NOT
    fall back to a pooled default, because different prop families have opposite
    biases (e.g. hitters overpredict overs, pitcher outs underpredict) and a
    shared curve makes the mismatched ones worse.
    """
    entry = _load().get(prop)
    if not entry:
        return raw_prob
    p = _interp(raw_prob, entry.get("x", []), entry.get("y", []))
    return max(0.001, min(0.999, p))


def is_available() -> bool:
    return bool(_load())
