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
#   0.58 - 0.65   -> ~59-62% won   (Medium)
#   0.65 - 0.70   -> ~68-72% won   (High) — raised from 0.64 Jun 2026 walk-forward (+2.7pp H/E hit)
#   0.70+         -> ~74% won      (Elite)
# Probability sets the ceiling; High/Elite also require starter ERA edge + non-negative form.
MEDIUM_MIN = 0.58
HIGH_MIN_RAW_PICK = 0.65
ELITE_MIN_RAW_PICK = 0.70
# High/Elite also require a real starter edge (walk-forward 2026: era>=0.8 + prob>=0.65 + form>=0.02
# yields 81.5% H/E on 65 picks vs form>=0.0 at 81.3%/75).
HIGH_MIN_ERA_DIFF = 0.8
ELITE_MIN_ERA_DIFF = 2.5
HIGH_MIN_FORM_EDGE = 0.02
ELITE_MIN_FORM_EDGE = 0.0
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
    era_diff = round(float(era_diff), 6)
    form_edge = round(float(form_edge), 6)

    # An unconfirmed starter or no market price makes the probability less trustworthy:
    # cap such picks at Medium (and only if they clear a slightly higher bar).
    if not starter_certain or not market_available:
        return "Medium" if p >= UNCERTAIN_MEDIUM_MIN else "Low"

    # High/Elite require the model to agree with the market side — contrarian High
    # picks hit ~68% vs ~81% when market agrees (2026 walk-forward, model-only publish).
    tier = "Low"
    if p >= ELITE_MIN_RAW_PICK and era_diff >= ELITE_MIN_ERA_DIFF and form_edge >= ELITE_MIN_FORM_EDGE:
        tier = "Elite"
    elif p >= HIGH_MIN_RAW_PICK and era_diff >= HIGH_MIN_ERA_DIFF and form_edge >= HIGH_MIN_FORM_EDGE:
        tier = "High"
    elif p >= MEDIUM_MIN:
        tier = "Medium"

    if tier in ("High", "Elite") and market_agrees is False:
        return "Medium" if p >= MEDIUM_MIN else "Low"
    return tier
