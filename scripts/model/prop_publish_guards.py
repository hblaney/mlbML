"""Hard pre-publish guards for the prop board.

Nothing absurd reaches public/*.json. Call ``scrub_predictions`` before write,
then ``assert_payload_sane`` — CI / generators must fail closed, not ship junk
for a human to notice later.
"""

from __future__ import annotations

import math
from typing import Any

# Single-game physical ceilings. Anything above is a model bug, not a lean.
MAX_PROJ = {
    "batter_home_runs": 0.65,
    "batter_stolen_bases": 1.25,
    "batter_doubles": 1.5,
    "batter_hits": 3.2,
    "batter_singles": 2.8,
    "batter_total_bases": 5.0,
    "batter_rbis": 3.5,
    "batter_runs_scored": 2.5,
    "batter_walks": 2.5,
    "batter_hits_runs_rbis": 5.5,
    "pitcher_strikeouts": 14.0,
    "pitcher_outs": 27.0,
    "pitcher_earned_runs": 7.0,
    "pitcher_hits_allowed": 12.0,
    "pitcher_walks": 6.0,
}

# Probabilities this extreme are almost always freebie / collapsed calibration.
MAX_MODEL_PROB = 0.965

# Never publish these — not because the model is wrong, but because they are
# not real bets (SB Under 0.5 ≈ "yes humans rarely steal").
UNBETTABLE_PROPS = {"batter_stolen_bases", "batter_runs_scored"}


def _finite(x: Any) -> bool:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v)


def violation_reason(row: dict) -> str | None:
    """Return a short reason if this row must not be published, else None."""
    prop = str(row.get("prop") or "")
    side = str(row.get("side") or "")
    if not prop:
        return "missing_prop"
    try:
        line = float(row.get("line") or 0)
    except (TypeError, ValueError):
        line = 0.0
    if prop in UNBETTABLE_PROPS:
        return f"unbettable_prop:{prop}"
    if prop == "batter_home_runs" and line <= 0.5 and side == "Under":
        return "unbettable_hr_under"
    if not _finite(row.get("projection")):
        return "bad_projection"
    if not _finite(row.get("model_prob")):
        return "bad_model_prob"
    proj = float(row["projection"])
    prob = float(row["model_prob"])
    if proj < 0:
        return f"negative_projection:{proj:.3f}"
    cap = MAX_PROJ.get(prop)
    if cap is not None and proj > cap:
        return f"projection_ceiling:{prop}:{proj:.3f}>{cap}"
    if prob >= MAX_MODEL_PROB:
        return f"collapsed_prob:{prob:.3f}"
    if prob <= 0.001:
        return f"collapsed_prob_low:{prob:.3f}"
    # HR Over 0.5 with mean already >0.7 is the Valdez failure mode.
    if (
        prop == "batter_home_runs"
        and side == "Over"
        and line <= 0.5
        and proj >= 0.70
    ):
        return f"absurd_hr_over:{proj:.3f}"
    return None


def scrub_predictions(predictions: list[dict]) -> tuple[list[dict], list[dict]]:
    """Drop unpublishable rows. Returns (kept, dropped_with_reason)."""
    kept: list[dict] = []
    dropped: list[dict] = []
    for row in predictions:
        reason = violation_reason(row)
        if reason is None:
            kept.append(row)
            continue
        bad = dict(row)
        bad["publish_reject_reason"] = reason
        dropped.append(bad)
    return kept, dropped


def assert_payload_sane(payload: dict, *, context: str = "prop board") -> None:
    """Fail closed if any published bucket still contains a violation."""
    buckets = [
        ("predictions", payload.get("predictions") or []),
        ("top_bets", payload.get("top_bets") or []),
        ("parlay.legs", (payload.get("parlay") or {}).get("legs") or []),
    ]
    errors: list[str] = []
    for name, rows in buckets:
        for row in rows:
            reason = violation_reason(row)
            if reason:
                errors.append(
                    f"{name}: {row.get('player')} {row.get('side')} "
                    f"{row.get('line')} {row.get('prop')} ({reason})"
                )
    if errors:
        msg = f"{context} failed publish guards ({len(errors)}):\n  - " + "\n  - ".join(errors[:25])
        raise SystemExit(msg)
