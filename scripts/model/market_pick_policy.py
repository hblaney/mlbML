"""Published-side policy when GBM fades a live market.

August 2026: Low + market-disagree went 4-29 (12%). Taking the sportsbook
favorite on those games lifts the full slate from ~41% to ~60% without
touching High/Elite tickets (those already require market agreement).

July check: flipping disagrees was 6-3 vs 3-6 for GBM — same direction.
"""

from __future__ import annotations


def resolve_published_side(
    gbm_home: float,
    gbm_away: float,
    market_home: float | None,
    market_away: float | None,
) -> tuple[bool, bool]:
    """Return (publish_home, market_override).

    Override only when both sides have a market price and GBM picks the dog.
    """
    gbm_home_pick = float(gbm_home) >= float(gbm_away)
    if market_home is None or market_away is None:
        return gbm_home_pick, False
    market_home_pick = float(market_home) >= float(market_away)
    if gbm_home_pick == market_home_pick:
        return gbm_home_pick, False
    return market_home_pick, True
