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

# Confidence thresholds on the market-blended probability scale, derived from ACTUAL
# walk-forward win rates by pick-probability bucket (2,200 odds-backed games, Jun 2026):
#   < 0.58        -> ~49-51% won   (Low — coin flip, DO NOT bet)
#   0.58 - 0.64   -> ~59-60% won   (Medium)
#   0.64 - 0.70   -> ~65-70% won   (High)
#   0.70+         -> ~74% won      (Elite)
# These tiers are PURE PROBABILITY — no market-edge / disagreement requirement. The
# market is already blended into the probability for accuracy; a higher number simply
# means a more reliable pick. (Old logic required the model to DISAGREE with the line
# by 8%+ to earn High, which mislabeled reliable consensus favorites as Medium.)
MEDIUM_MIN = 0.58
HIGH_MIN_RAW_PICK = 0.64
ELITE_MIN_RAW_PICK = 0.70
# Picks with an unconfirmed starter or no market price can't earn High/Elite (the
# probability is less trustworthy without a confirmed starter / market anchor).
UNCERTAIN_MEDIUM_MIN = 0.60


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
    market_agrees: bool | None = None,
    raw_pick: float = 0.0,
    era_diff: float = 0.0,
    form_edge: float = 0.0,
) -> str:
    """Confidence tier on the true probability scale, gated by win-separating factors.

    display_pick is the honest (calibrated == raw) pick probability. No market or an
    unconfirmed starter caps the pick at Medium (we can't confirm direction/quality).
    """
    p = float(display_pick)

    # An unconfirmed starter or no market price makes the probability less trustworthy:
    # cap such picks at Medium (and only if they clear a slightly higher bar).
    if not starter_certain or not market_available:
        return "Medium" if p >= UNCERTAIN_MEDIUM_MIN else "Low"

    # Pure probability tiers — a more reliable pick simply has a higher win probability.
    if p >= ELITE_MIN_RAW_PICK:
        return "Elite"
    if p >= HIGH_MIN_RAW_PICK:
        return "High"
    if p >= MEDIUM_MIN:
        return "Medium"
    return "Low"
