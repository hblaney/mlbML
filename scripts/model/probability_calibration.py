"""Honest probability + confidence layer for the MLB model.

DESIGN (recalibrated 2026-09-05 on July+ graded history):
  Raw GBM side-picking collapsed on market-backed July games (~49% vs market ~57%).
  Mid-range published probs were overconfident (0.60–0.65 predicted → ~51% actual).
  Live publish therefore market-anchors via V3 when odds exist. When odds are missing,
  apply temperature shrink (T>1) so the board stops quoting fake mid-60s.

  Full-season isotonic maps still overfit — we only use a single temperature and
  market residual, not a bucket remapping. Confidence tiers remain betting labels
  gated by ERA / form / price agreement, now with a higher probability floor.
"""

from __future__ import annotations

import math

# Confidence is a BETTING label, not a probability bucket.
# 2026-09-12: High p floor aligned with TS (0.55). Strong pitcher + market agree
# can be High/Medium even when GBM quotes a coin-flip (today was 14/15 Low).
#   High (BET):  p≥0.55 + form≥0.1 + era≥0.5 + market agrees
#   Medium (LEAN): market agree + p≥0.52, or big ERA gap
#   Low (PASS): rest
#   Elite: stricter High (rare)
MEDIUM_MIN = 0.52
HIGH_MIN_RAW_PICK = 0.55
ELITE_MIN_RAW_PICK = 0.65
HIGH_MIN_ERA_DIFF = 0.5
ELITE_MIN_ERA_DIFF = 1.5
HIGH_MIN_FORM_EDGE = 0.1
ELITE_MIN_FORM_EDGE = 0.1
HIGH_MIN_MODEL_EDGE = 0.0
ELITE_MIN_MODEL_EDGE = 0.03
# Picks with an unconfirmed starter or no market price can't earn High/Elite (the
# probability is less trustworthy without a confirmed starter / market anchor).
UNCERTAIN_MEDIUM_MIN = 0.55

# No-market fallback: T=1.6 from Jun+ Brier/ECE sweep (sides unchanged, probs honest).
NO_MARKET_TEMPERATURE = 1.6


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def apply_temperature_shrink(home_probability: float, temperature: float = NO_MARKET_TEMPERATURE) -> float:
    """Shrink home win% toward 0.5 via temperature scaling (T>1 = less confident)."""
    t = max(float(temperature), 1e-3)
    return round(_sigmoid(_logit(home_probability) / t), 4)


def calibrated_display_probability(raw_pick: float, *, market_available: bool = True) -> float:
    """Display pick probability. Market rows are already V3-calibrated upstream."""
    p = float(raw_pick)
    if not market_available:
        # raw_pick is a pick-side max(p,1-p); shrink via home-style logit on the pick.
        # Convert to a pseudo-home at pick, shrink, re-max — keeps pick >= 0.5.
        shrunk = apply_temperature_shrink(p)
        return round(max(shrunk, 1.0 - shrunk), 4)
    return round(p, 4)


def apply_display_calibration(
    home_probability: float,
    away_probability: float,
    *,
    market_available: bool = True,
) -> tuple[float, float, float]:
    """Calibrate home/away for display. Market path is identity (V3 already applied)."""
    home = float(home_probability)
    away = float(away_probability)
    if not market_available:
        home = apply_temperature_shrink(home)
        away = 1.0 - home
    pick = max(home, away)
    return round(home, 4), round(away, 4), round(pick, 4)


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
        # Still a lean if the book and model agree at a real favorite; no High/Elite.
        if market_agrees is True and p >= UNCERTAIN_MEDIUM_MIN:
            return "Medium"
        return "Medium" if p >= 0.60 else "Low"

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
    # Lean: book agrees, or a real starter gap even if GBM is conservative.
    if market_agrees is True and p >= MEDIUM_MIN:
        return "Medium"
    if era_diff >= 1.0 and p >= MEDIUM_MIN and form_edge >= 0.0:
        return "Medium"
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
