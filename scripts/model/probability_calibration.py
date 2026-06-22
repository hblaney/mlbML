"""Map raw model pick probability to accountable 60–90% display scale.

Buckets built from 2026 walk-forward empirical hit rates (not threshold gaming).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUCKETS_PATH = ROOT / "data" / "model" / "calibration-buckets.json"

# (raw_lo, raw_hi, empirical_hit_rate) — season walk-forward Jun 2026
DEFAULT_BUCKETS: list[tuple[float, float, float]] = [
    (0.50, 0.55, 0.536),
    (0.55, 0.58, 0.556),
    (0.58, 0.61, 0.569),
    (0.61, 0.64, 0.654),
    (0.64, 0.67, 0.731),
    (0.67, 0.70, 0.686),
    (0.70, 0.73, 0.688),
    (0.73, 0.76, 0.737),
    (0.76, 0.80, 0.923),
    (0.80, 1.00, 0.900),
]

DISPLAY_FLOOR = 0.60
DISPLAY_CEILING = 0.90
# Without market odds we never inflate past raw + this bump (prevents fake High labels).
NO_MARKET_DISPLAY_BUMP = 0.04
NO_MARKET_DISPLAY_CAP = 0.72
# High/Elite need this raw pipeline pick even when display calibration is higher.
HIGH_MIN_RAW_PICK = 0.62
ELITE_MIN_RAW_PICK = 0.67
# Map empirical hit rate [0.52, 0.78] → display [0.60, 0.90]
EMPIRICAL_LO = 0.52
EMPIRICAL_HI = 0.78


def _empirical_to_display(empirical: float) -> float:
    e = max(EMPIRICAL_LO, min(EMPIRICAL_HI, empirical))
    return DISPLAY_FLOOR + (e - EMPIRICAL_LO) / (EMPIRICAL_HI - EMPIRICAL_LO) * (
        DISPLAY_CEILING - DISPLAY_FLOOR
    )


def load_buckets() -> list[tuple[float, float, float]]:
    if BUCKETS_PATH.exists():
        try:
            payload = json.loads(BUCKETS_PATH.read_text())
            return [(b["lo"], b["hi"], b["empirical"]) for b in payload.get("buckets", [])]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    return DEFAULT_BUCKETS


def raw_pick_to_empirical(raw_pick: float, buckets: list[tuple[float, float, float]] | None = None) -> float:
    buckets = buckets or load_buckets()
    p = float(raw_pick)
    for lo, hi, empirical in buckets:
        if lo <= p < hi:
            return empirical
    if p >= buckets[-1][1]:
        return buckets[-1][2]
    return buckets[0][2]


def calibrated_display_probability(raw_pick: float, *, market_available: bool = True) -> float:
    """Honest display % on 60–90 scale from walk-forward bucket hit rates."""
    raw_pick = float(raw_pick)
    if not market_available:
        boosted = raw_pick + NO_MARKET_DISPLAY_BUMP
        return round(max(DISPLAY_FLOOR, min(NO_MARKET_DISPLAY_CAP, boosted)), 4)
    empirical = raw_pick_to_empirical(raw_pick)
    display = _empirical_to_display(empirical)
    return round(max(DISPLAY_FLOOR, min(DISPLAY_CEILING, display)), 4)


def apply_display_calibration(
    home_probability: float,
    away_probability: float,
    *,
    market_available: bool = True,
) -> tuple[float, float, float]:
    """Return home, away, pick on the 60–90 accountable display scale."""
    raw_pick = max(home_probability, away_probability)
    display_pick = calibrated_display_probability(raw_pick, market_available=market_available)
    if home_probability >= away_probability:
        return display_pick, round(1.0 - display_pick, 4), display_pick
    return round(1.0 - display_pick, 4), display_pick, display_pick


def confidence_from_display(
    display_pick: float,
    *,
    model_edge: float = 0.0,
    starter_certain: bool = True,
    market_available: bool = True,
    raw_pick: float = 0.0,
    era_diff: float = 0.0,
    form_edge: float = 0.0,
) -> str:
    """Multi-factor confidence gates — walk-forward calibrated.

    Season data: High/Elite wins avg era_diff=3.5 vs losses=2.4.
    Gates eliminate the ~26% of H/E picks that shouldn't be there.
    No market odds → never High/Elite (can't confirm direction).
    """
    if not starter_certain:
        return "Low" if display_pick < 0.68 else "Medium"

    if not market_available:
        return "Medium" if display_pick >= 0.68 else "Low"

    # Elite: model has extreme separation AND starters confirm AND team form confirms
    elite_era_ok = era_diff >= 2.5
    elite_form_ok = form_edge >= 0.08
    if (
        display_pick >= 0.85
        and model_edge >= 0.10
        and raw_pick >= ELITE_MIN_RAW_PICK
        and elite_era_ok
        and elite_form_ok
    ):
        return "Elite"

    # High: meaningful starter edge OR strong form tilt, not both required
    high_era_ok = era_diff >= 1.5
    high_form_ok = form_edge >= 0.10
    if (
        display_pick >= 0.76
        and model_edge >= 0.08
        and raw_pick >= HIGH_MIN_RAW_PICK
        and (high_era_ok or high_form_ok)
    ):
        return "High"

    if display_pick >= 0.68:
        return "Medium"
    return "Low"


def rebuild_buckets_from_rows(rows: list[dict], min_samples: int = 15) -> list[dict]:
    """Rebuild calibration buckets from walk-forward rows."""
    edges = [0.52, 0.55, 0.58, 0.61, 0.64, 0.67, 0.70, 0.73, 0.76, 0.80, 0.85]
    out: list[dict] = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        sub = [r for r in rows if lo <= float(r.get("rawPickProbability", r.get("pickProbability", 0))) < hi]
        if len(sub) < min_samples:
            continue
        empirical = sum(int(r["correct"]) for r in sub) / len(sub)
        out.append({"lo": lo, "hi": hi, "empirical": round(empirical, 4), "n": len(sub)})
    if out:
        BUCKETS_PATH.parent.mkdir(parents=True, exist_ok=True)
        BUCKETS_PATH.write_text(json.dumps({"buckets": out}, indent=2))
    return out
