"""Honest probability + confidence layer for the MLB model.

DESIGN (validated Jun 2026 on 3,410 graded games, chronological 70/30 split):
  The raw model pick probability is already the best-calibrated estimate we have
  (out-of-sample ECE 2.2%, Brier 0.236). Adding an isotonic/stretch calibration
  on top OVERFIT and made every metric worse out-of-sample. The previous
  "display calibration" stretched empirical hit rates onto a cosmetic 60–90 scale
  and inflated shown probabilities by 8–13 points (displayed-ECE 9.6%).

  So we DO NOT transform the probability for display. The number shown to the
  user IS the model's calibrated probability — i.e. when we say 66%, picks like
  that win ~66% of the time. Confidence tiers sit on this true scale, gated by the
  factors that actually separate winners (starter ERA edge, team form, market).
"""

from __future__ import annotations

# Confidence thresholds on the TRUE probability scale, derived from actual
# walk-forward win rates by raw-probability bucket:
#   raw 0.57-0.64 -> ~57-64% won   (Medium)
#   raw 0.64-0.67 -> ~67-70% won   (High, with starter/form gate) — raised from 0.62 Jun 2026
#   raw 0.67+     -> ~69-74% won   (Elite, with stronger gate)
MEDIUM_MIN = 0.57
HIGH_MIN_RAW_PICK = 0.64
ELITE_MIN_RAW_PICK = 0.67
# Picks with an unconfirmed starter or no market price can't earn High/Elite.
UNCERTAIN_MEDIUM_MIN = 0.60

# Secondary gates (same as before — these empirically separate H/E wins from losses).
HIGH_EDGE_MIN = 0.08
ELITE_EDGE_MIN = 0.10
HIGH_ERA_DIFF_MIN = 1.5
HIGH_FORM_EDGE_MIN = 0.10
ELITE_ERA_DIFF_MIN = 2.5
ELITE_FORM_EDGE_MIN = 0.08


def calibrated_display_probability(raw_pick: float, *, market_available: bool = True) -> float:
    """Honest display probability == the model's calibrated pick probability.

    No transform: the raw pick probability is already well-calibrated. market_available
    is kept for signature compatibility; it only affects the confidence tier, not the %.
    """
    return round(float(raw_pick), 4)


def apply_display_calibration(
    home_probability: float,
    away_probability: float,
    *,
    market_available: bool = True,
) -> tuple[float, float, float]:
    """Identity passthrough — returns home, away, pick unchanged (already calibrated)."""
    pick = max(home_probability, away_probability)
    return round(float(home_probability), 4), round(float(away_probability), 4), round(float(pick), 4)


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
    """Confidence tier on the true probability scale, gated by win-separating factors.

    display_pick is the honest (calibrated == raw) pick probability. No market or an
    unconfirmed starter caps the pick at Medium (we can't confirm direction/quality).
    """
    p = float(display_pick)

    if not starter_certain:
        return "Medium" if p >= UNCERTAIN_MEDIUM_MIN else "Low"

    if not market_available:
        return "Medium" if p >= UNCERTAIN_MEDIUM_MIN else "Low"

    elite_era_ok = era_diff >= ELITE_ERA_DIFF_MIN
    elite_form_ok = form_edge >= ELITE_FORM_EDGE_MIN
    if (
        p >= ELITE_MIN_RAW_PICK
        and model_edge >= ELITE_EDGE_MIN
        and elite_era_ok
        and elite_form_ok
    ):
        return "Elite"

    high_era_ok = era_diff >= HIGH_ERA_DIFF_MIN
    high_form_ok = form_edge >= HIGH_FORM_EDGE_MIN
    if (
        p >= HIGH_MIN_RAW_PICK
        and model_edge >= HIGH_EDGE_MIN
        and (high_era_ok or high_form_ok)
    ):
        return "High"

    if p >= MEDIUM_MIN:
        return "Medium"
    return "Low"
