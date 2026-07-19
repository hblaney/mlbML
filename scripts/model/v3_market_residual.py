"""V3 probability layer — market-anchored residual, honest small edges.

    P(home) = market_home + α_eff × (model_home − market_home)

Design (Jul 2026 — bet-ready hardening):
  - Markets are the prior. We do NOT invent huge edges by trusting an overconfident GBM.
  - When the raw model fights the market, α collapses toward 0 (follow the market).
  - Published edge is capped — "big edge" was mostly model error in live locks.
  - High confidence requires market AGREEMENT, not disagreement.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import NamedTuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PARAMS_PATH = REPO_ROOT / "data" / "model" / "v3_params.json"

# Hug the market: the model was fighting the book too hard and picking longshots
# that didn't hit (Jul 2026). Lower alpha => published prob sits much closer to the
# market consensus, so picks track favorites instead of anti-market dogs. (was 0.38)
DEFAULT_ALPHA = 0.22
# When raw model side ≠ market side, barely move off the market.
DISAGREE_ALPHA = 0.05
PICK_PROB_FLOOR = 0.38
# Don't publish 72%+ — last-100 buckets at 70%+ were ~coin flips.
PICK_PROB_CAP = 0.66
# Cap published model−book gap so tickets can't hunt fake 15–25% edges.
MAX_EDGE_AGREE = 0.035
MAX_EDGE_DISAGREE = 0.01


class V3Params(NamedTuple):
    alpha: float
    tuned_on: str
    holdout_brier: float
    holdout_n: int


class V3PublishResult(NamedTuple):
    home_probability: float
    away_probability: float
    pick_probability: float
    raw_pick_probability: float
    confidence: str
    market_agrees: bool | None
    model_edge: float


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def load_v3_params() -> V3Params:
    if not PARAMS_PATH.exists():
        return V3Params(alpha=DEFAULT_ALPHA, tuned_on="default", holdout_brier=0.0, holdout_n=0)
    try:
        raw = json.loads(PARAMS_PATH.read_text())
        return V3Params(
            alpha=float(raw.get("alpha", DEFAULT_ALPHA)),
            tuned_on=str(raw.get("tuned_on", "")),
            holdout_brier=float(raw.get("holdout_brier", 0.0)),
            holdout_n=int(raw.get("holdout_n", 0)),
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return V3Params(alpha=DEFAULT_ALPHA, tuned_on="default", holdout_brier=0.0, holdout_n=0)


def save_v3_params(params: V3Params) -> None:
    PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PARAMS_PATH.write_text(
        json.dumps(
            {
                "alpha": round(params.alpha, 4),
                "tuned_on": params.tuned_on,
                "holdout_brier": round(params.holdout_brier, 5),
                "holdout_n": params.holdout_n,
                "architecture": "market_residual_v3_honest",
                "disagree_alpha": DISAGREE_ALPHA,
                "max_edge_agree": MAX_EDGE_AGREE,
                "pick_prob_cap": PICK_PROB_CAP,
            },
            indent=2,
        )
    )


def normalize_market(home: float, away: float) -> tuple[float, float]:
    total = home + away
    if total <= 0:
        return 0.5, 0.5
    return home / total, away / total


def anchor_model_to_market(model_home: float, market_home: float, market_away: float, alpha: float) -> tuple[float, float]:
    mh, ma = normalize_market(market_home, market_away)
    home = mh + alpha * (model_home - mh)
    home = _clip(home, PICK_PROB_FLOOR, PICK_PROB_CAP)
    away = 1.0 - home
    total = home + away
    return home / total, away / total


def _effective_alpha(model_home: float, market_home: float, market_away: float, base_alpha: float) -> float:
    mh, ma = normalize_market(market_home, market_away)
    market_pick_home = mh >= ma
    raw_pick_home = model_home >= 0.5
    if market_pick_home == raw_pick_home:
        return min(base_alpha, DEFAULT_ALPHA)
    return DISAGREE_ALPHA


def _cap_edge(home_p: float, mh: float, ma: float, *, agrees: bool) -> tuple[float, float]:
    """Pull published probs toward the book so |edge| cannot explode."""
    pick_home = home_p >= 0.5
    pick_p = home_p if pick_home else 1.0 - home_p
    book = mh if pick_home else ma
    edge = pick_p - book
    max_edge = MAX_EDGE_AGREE if agrees else MAX_EDGE_DISAGREE
    if abs(edge) <= max_edge:
        return home_p, 1.0 - home_p
    # Shrink pick toward book by the excess edge.
    target_pick = book + (max_edge if edge > 0 else -max_edge)
    target_pick = _clip(target_pick, PICK_PROB_FLOOR, PICK_PROB_CAP)
    if pick_home:
        home = target_pick
    else:
        home = 1.0 - target_pick
    home = _clip(home, PICK_PROB_FLOOR, PICK_PROB_CAP)
    return home, 1.0 - home


def confidence_from_edge(
    pick_probability: float,
    model_edge: float,
    *,
    market_agrees: bool | None,
    starter_certain: bool,
    market_available: bool,
) -> str:
    if not starter_certain or not market_available:
        return "Medium" if pick_probability >= 0.57 else "Low"

    # Never label anti-market picks High — that was a live failure mode.
    if market_agrees is False:
        return "Low" if pick_probability < 0.57 else "Medium"

    if pick_probability >= 0.62 and 0.02 <= model_edge <= MAX_EDGE_AGREE:
        return "High"
    if pick_probability >= 0.57 and model_edge >= 0.015:
        return "Medium"
    if pick_probability >= 0.57:
        return "Medium"
    return "Low"


def publish_v3(
    model_home: float,
    *,
    market_home: float | None = None,
    market_away: float | None = None,
    starter_certain: bool = True,
    alpha: float | None = None,
) -> V3PublishResult:
    """Convert raw GBM home win prob into public pick + capped edge."""
    params = load_v3_params()
    base_alpha = params.alpha if alpha is None else alpha
    # Prefer the honest default if an old hot-alpha was persisted.
    if alpha is None and base_alpha > DEFAULT_ALPHA + 0.05:
        base_alpha = DEFAULT_ALPHA

    if market_home is not None and market_away is not None:
        mh, ma = normalize_market(market_home, market_away)
        use_alpha = _effective_alpha(model_home, market_home, market_away, base_alpha)
        home_p, away_p = anchor_model_to_market(model_home, market_home, market_away, use_alpha)
        market_pick_home = mh >= ma
        model_pick_home = home_p >= away_p
        market_agrees = market_pick_home == model_pick_home
        home_p, away_p = _cap_edge(home_p, mh, ma, agrees=bool(market_agrees))
        pick_is_home = home_p >= away_p
        book_pick = mh if pick_is_home else ma
        pick_p = home_p if pick_is_home else away_p
        model_edge = pick_p - book_pick
        market_agrees = (mh >= ma) == pick_is_home
    else:
        home_p = _clip(model_home, PICK_PROB_FLOOR, PICK_PROB_CAP)
        away_p = 1.0 - home_p
        pick_p = max(home_p, away_p)
        market_agrees = None
        model_edge = 0.0

    confidence = confidence_from_edge(
        pick_p,
        model_edge,
        market_agrees=market_agrees,
        starter_certain=starter_certain,
        market_available=market_home is not None and market_away is not None,
    )

    return V3PublishResult(
        home_probability=round(home_p, 4),
        away_probability=round(away_p, 4),
        pick_probability=round(pick_p, 4),
        raw_pick_probability=round(max(model_home, 1.0 - model_home), 4),
        confidence=confidence,
        market_agrees=market_agrees,
        model_edge=round(model_edge, 4),
    )


def tune_alpha(samples: list[tuple[float, float, float, int]]) -> V3Params:
    """Tune α on (model_home, market_home_nv, market_away_nv, home_won) rows.

    Search stays in the honest band [0.20, 0.45] — higher α reintroduced fake edges.
    """
    if len(samples) < 40:
        return V3Params(alpha=DEFAULT_ALPHA, tuned_on="insufficient_data", holdout_brier=0.25, holdout_n=len(samples))

    best_alpha = DEFAULT_ALPHA
    best_brier = math.inf

    for alpha in np.linspace(0.20, 0.45, 14):
        preds = []
        for mh_model, mh, ma, _label in samples:
            eff = _effective_alpha(mh_model, mh, ma, float(alpha))
            ph, _ = anchor_model_to_market(mh_model, mh, ma, eff)
            # Apply same edge cap used at publish time.
            mhn, man = normalize_market(mh, ma)
            agrees = (mhn >= man) == (ph >= 0.5)
            ph, _ = _cap_edge(ph, mhn, man, agrees=agrees)
            preds.append(ph)
        y = np.array([s[3] for s in samples], dtype=float)
        p = np.clip(np.array(preds), 1e-6, 1 - 1e-6)
        brier = float(np.mean((p - y) ** 2))
        if brier < best_brier:
            best_brier = brier
            best_alpha = float(alpha)

    return V3Params(
        alpha=best_alpha,
        tuned_on=f"{len(samples)}_market_games_honest",
        holdout_brier=best_brier,
        holdout_n=len(samples),
    )
