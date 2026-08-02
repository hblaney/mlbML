"""Daily confidence labels for published GBM moneylines.

High/Elite must mean something. We do NOT force a quota of High picks per day —
that policy produced ~47% High/Elite over the last week by promoting 52–58%
favorites with negative form / no market agreement.

Tiers come from probability_calibration.confidence_from_display (walk-forward
gates: pick p, starter ERA edge, form edge, market agree when odds exist).
"""

from __future__ import annotations

from typing import Any

from probability_calibration import confidence_from_display


def assign_daily_confidence(board: list[dict[str, Any]]) -> None:
    """Mutate board rows with accountable High/Elite gates. No daily quota."""
    if not board:
        return

    for row in board:
        p = float(row.get("pickProbability") or 0.0)
        market_available = row.get("homeMoneyline") is not None and row.get("awayMoneyline") is not None
        row["confidence"] = confidence_from_display(
            p,
            model_edge=float(row.get("modelEdge") or 0.0),
            starter_certain=bool(row.get("starterCertain", True)),
            market_available=market_available,
            market_agrees=row.get("marketAgrees"),
            raw_pick=float(row.get("rawPickProbability") or p),
            era_diff=float(row.get("eraDiff") or 0.0),
            form_edge=float(row.get("formEdge") or 0.0),
        )
