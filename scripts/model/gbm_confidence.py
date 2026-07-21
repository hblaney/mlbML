"""Daily confidence card for published GBM moneylines.

OOS (2026-05-01 → 2026-07-19, walk-forward GBM):
  - Overall pick accuracy ≈ 61%
  - Top-3 picks/day ≈ 73% (not 90% — MLB moneylines don't support 90% at n≥3/day)
  - p≥0.65 High/Elite ≈ 74% but only ~4/77 days have ≥3 such games

Policy: publish raw GBM win%; label ≥3 High/Elite every day by promoting the
slate's strongest remaining favorites (floor pick_p ≥ 0.52).
"""

from __future__ import annotations

from typing import Any

MIN_HIGH_PER_DAY = 3
PROMOTE_FLOOR = 0.52
ELITE_MIN = 0.65
HIGH_MIN = 0.58
MEDIUM_MIN = 0.55


def base_confidence(pick_probability: float, *, starter_certain: bool) -> str:
    p = float(pick_probability)
    if not starter_certain:
        return "Medium" if p >= 0.60 else "Low"
    if p >= ELITE_MIN:
        return "Elite"
    if p >= HIGH_MIN:
        return "High"
    if p >= MEDIUM_MIN:
        return "Medium"
    return "Low"


def assign_daily_confidence(board: list[dict[str, Any]]) -> None:
    """Mutate board rows: base tiers, then ensure ≥3 High/Elite when possible."""
    if not board:
        return

    for row in board:
        row["confidence"] = base_confidence(
            float(row.get("pickProbability") or 0.0),
            starter_certain=bool(row.get("starterCertain", True)),
        )

    high_n = sum(1 for r in board if r.get("confidence") in ("High", "Elite"))
    if high_n >= MIN_HIGH_PER_DAY:
        return

    need = MIN_HIGH_PER_DAY - high_n
    ranked = sorted(board, key=lambda r: -float(r.get("pickProbability") or 0.0))
    for row in ranked:
        if need <= 0:
            break
        if row.get("confidence") in ("High", "Elite"):
            continue
        p = float(row.get("pickProbability") or 0.0)
        if p < PROMOTE_FLOOR:
            continue
        row["confidence"] = "High"
        notes = list(row.get("explanation") or [])
        notes.append(
            f"Promoted to High for today's top-{MIN_HIGH_PER_DAY} model card "
            f"(OOS top-3/day ≈73%, not 90%)."
        )
        row["explanation"] = notes
        need -= 1
