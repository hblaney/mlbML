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

# Confidence is a BETTING label, not a probability bucket.
# Validated on 2026 market-backed walk-forward (season + last-30/45 stability):
#   High (BET):  p≥0.55 + form≥0.1 + era≥0.5 + edge≥2% + market agrees
#                → ~70% hit, ~0.4/day (last-30/45 ~67%)
#   Medium (LEAN): price-supported edge without the full matchup stack → ~62-66%
#   Low (PASS): rest → ~53-55% — do not bet
#   Elite: stricter High (rare)
# No daily High quota — if nothing clears, the board shows zero Highs.
MEDIUM_MIN = 0.55
HIGH_MIN_RAW_PICK = 0.55
ELITE_MIN_RAW_PICK = 0.65
HIGH_MIN_ERA_DIFF = 0.5
ELITE_MIN_ERA_DIFF = 1.5
HIGH_MIN_FORM_EDGE = 0.1
ELITE_MIN_FORM_EDGE = 0.1
HIGH_MIN_MODEL_EDGE = 0.02
ELITE_MIN_MODEL_EDGE = 0.03
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
    """Confidence tier = actionable betting label on the true probability scale.

    High/Elite require the full win-separating stack (p + ERA + form + price edge +
    market agree). Medium is a lean when price supports the side but a matchup gate
    is soft. Low means pass.
    """
    del raw_pick  # kept for call-site compatibility
    p = float(display_pick)
    era_diff = round(float(era_diff), 6)
    form_edge = round(float(form_edge), 6)
    edge = float(model_edge)

    # An unconfirmed starter or no market price makes the probability less trustworthy:
    # cap such picks at Medium (and only if they clear a slightly higher bar).
    if not starter_certain or not market_available:
        return "Medium" if p >= UNCERTAIN_MEDIUM_MIN else "Low"

    if (
        p >= ELITE_MIN_RAW_PICK
        and era_diff >= ELITE_MIN_ERA_DIFF
        and form_edge >= ELITE_MIN_FORM_EDGE
        and edge >= ELITE_MIN_MODEL_EDGE
        and market_agrees is True
    ):
        return "Elite"
    if (
        p >= HIGH_MIN_RAW_PICK
        and era_diff >= HIGH_MIN_ERA_DIFF
        and form_edge >= HIGH_MIN_FORM_EDGE
        and edge >= HIGH_MIN_MODEL_EDGE
        and market_agrees is True
    ):
        return "High"
    # Lean: book agrees and model has a real price edge, but form/ERA aren't full High.
    if market_agrees is True and edge >= HIGH_MIN_MODEL_EDGE and p >= MEDIUM_MIN:
        return "Medium"
    # Strong matchup without a clean price edge still rates a lean above coin-flips.
    if p >= 0.58 and era_diff >= HIGH_MIN_ERA_DIFF and form_edge >= 0.0:
        return "Medium"
    return "Low"


def bet_action_from_confidence(confidence: str) -> str:
    """Map confidence → what the user should do with bankroll."""
    if confidence in ("Elite", "High"):
        return "bet"
    if confidence == "Medium":
        return "lean"
    return "pass"
