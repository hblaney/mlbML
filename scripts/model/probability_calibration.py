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

# Confidence thresholds on the true probability scale + win-separating gates.
# Validated on 2026 market-backed walk-forward (not the old "force ≥3 Highs/day" quota):
#   High:  p≥0.60 + form≥0 + era≥0.5 + market agrees  → ~72% on ~1.2/day
#   Elite: p≥0.65 + form≥0.02 + era≥1.5 + market agrees → ~75% on ~0.25/day
# No daily High quota — if nothing clears, the board shows zero Highs.
MEDIUM_MIN = 0.58
HIGH_MIN_RAW_PICK = 0.60
ELITE_MIN_RAW_PICK = 0.65
HIGH_MIN_ERA_DIFF = 0.5
ELITE_MIN_ERA_DIFF = 1.5
HIGH_MIN_FORM_EDGE = 0.0
ELITE_MIN_FORM_EDGE = 0.02
# Also require a real price edge so High isn't just chalk the book already loves.
HIGH_MIN_MODEL_EDGE = 0.02
ELITE_MIN_MODEL_EDGE = 0.02
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

    # High/Elite require market agreement + price edge. Contrarian / no-edge "Highs"
    # are how the label got worthless.
    edge = float(model_edge)
    tier = "Low"
    if (
        p >= ELITE_MIN_RAW_PICK
        and era_diff >= ELITE_MIN_ERA_DIFF
        and form_edge >= ELITE_MIN_FORM_EDGE
        and edge >= ELITE_MIN_MODEL_EDGE
        and market_agrees is True
    ):
        tier = "Elite"
    elif (
        p >= HIGH_MIN_RAW_PICK
        and era_diff >= HIGH_MIN_ERA_DIFF
        and form_edge >= HIGH_MIN_FORM_EDGE
        and edge >= HIGH_MIN_MODEL_EDGE
        and market_agrees is True
    ):
        tier = "High"
    elif p >= MEDIUM_MIN:
        tier = "Medium"
    return tier
