"""Guards against the junk-card failure mode shipping again."""

from __future__ import annotations

from generate_prop_predictions import (
    TOP_BET_MIN_CONF,
    _confidence,
    _is_unplayable_on_prizepicks,
    _k_over_lane,
    _sanitize_leg,
    build_parlay,
    build_top_bets,
)


def _leg(player: str, prop: str, line: float, model_prob: float, projection: float) -> dict:
    return {
        "player": player,
        "prop": prop,
        "prop_label": prop,
        "line": line,
        "side": "Under",
        "pick": f"Under {line}",
        "model_prob": model_prob,
        "edge": model_prob - 0.5,
        "projection": projection,
        "book_count": 3,
        "market_prob": 0.5,
        "confidence": "Elite",  # stale bad tag — sanitizer must kill this
        "line_source": "prizepicks",
        "pp_odds_type": "standard",  # Under only playable on standard
    }


def test_no_fake_elite_from_edge_vs_pickem():
    assert _confidence(0.20, 3, side="Under", model_prob=TOP_BET_MIN_CONF - 0.01) != "Elite"
    assert _confidence(0.25, 3, side="Under", model_prob=TOP_BET_MIN_CONF) == "Elite"


def test_sanitize_strips_stale_elite():
    row = _sanitize_leg(_leg("A", "batter_hits", 1.5, 0.57, 1.2))
    assert row["confidence"] != "Elite"
    assert row.get("below_oos_threshold") is True


def test_thin_card_when_below_floor():
    """Do not pad Top 5 with sub-threshold or banned-market junk."""
    preds = [
        _leg("P1", "batter_total_bases", 1.5, 0.90, 1.0),  # banned market
        _leg("P2", "batter_hits", 1.5, 0.56, 1.1),  # below floor
        _leg("P3", "pitcher_strikeouts", 5.5, 0.55, 5.0),
        _leg("P4", "batter_hits_runs_rbis", 1.5, 0.90, 1.2),  # banned
        _leg("P5", "batter_rbis", 0.5, 0.90, 0.2),  # banned
    ]
    top = build_top_bets(preds, n=5)
    assert len(top) == 0
    strong = [
        _leg("U1", "batter_hits", 1.5, 0.80, 1.0),
        _leg("U2", "batter_hits", 0.5, 0.78, 0.3),
        _leg("U3", "pitcher_strikeouts", 5.5, 0.75, 4.0),
        _leg("U4", "pitcher_strikeouts", 6.5, 0.72, 5.0),
        _leg("U5", "batter_hits", 1.5, 0.70, 1.0),
    ]
    top5 = build_top_bets(strong, n=5)
    assert len(top5) == 5
    assert len({t["player"] for t in top5}) == 5
    assert all(t["prop"] in ("batter_hits", "pitcher_strikeouts") for t in top5)
    parlay = build_parlay(strong)
    assert parlay["n_legs"] == 5
    assert parlay.get("flex_cash_rate_oos") is None


def test_rejects_under_when_projection_at_or_above_line():
    preds = [
        _leg("Bad", "batter_hits", 1.5, 0.90, 1.6),  # coin flip / wrong side
        _leg("P1", "batter_hits", 1.5, 0.89, 1.1),
        _leg("P2", "batter_hits", 0.5, 0.88, 0.3),
        _leg("P3", "pitcher_strikeouts", 5.5, 0.87, 5.0),
        _leg("P4", "batter_hits", 1.5, 0.86, 1.0),
        _leg("P5", "pitcher_strikeouts", 6.5, 0.85, 5.5),
    ]
    top = build_top_bets(preds, n=5)
    assert all(t["player"] != "Bad" for t in top)
    assert len(top) == 5


def test_k_over_eligible_but_not_front_loaded():
    """K overs can make the card on merit; they don't get reserved #1 slots."""
    miz = {
        "player": "Jacob Misiorowski",
        "prop": "pitcher_strikeouts",
        "prop_label": "Pitcher Strikeouts",
        "line": 6.5,
        "side": "Over",
        "pick": "Over 6.5",
        "model_prob": 0.79,
        "edge": 0.29,
        "projection": 8.9,
        "book_count": 3,
        "market_prob": 0.5,
        "confidence": "Low",
        "line_source": "prizepicks",
        "pp_odds_type": "goblin",
    }
    stronger = _leg("Ace Under", "batter_hits", 1.5, 0.92, 1.0)
    preds = [
        miz,
        stronger,
        _leg("P2", "batter_hits", 1.5, 0.90, 1.1),
        _leg("P3", "pitcher_strikeouts", 5.5, 0.88, 5.0),
        _leg("Weak", "batter_hits", 1.5, 0.50, 1.0),
    ]
    assert any(p["player"] == "Jacob Misiorowski" for p in _k_over_lane(preds))
    top = build_top_bets(preds, n=5)
    assert top[0]["player"] == "Ace Under"
    assert any(t["player"] == "Jacob Misiorowski" for t in top)
    assert len(top) == 4


def test_weaker_k_over_does_not_beat_better_unders():
    miz = {
        "player": "Jacob Misiorowski",
        "prop": "pitcher_strikeouts",
        "prop_label": "Pitcher Strikeouts",
        "line": 6.5,
        "side": "Over",
        "pick": "Over 6.5",
        "model_prob": 0.70,
        "edge": 0.20,
        "projection": 8.9,
        "book_count": 3,
        "market_prob": 0.5,
        "line_source": "prizepicks",
        "pp_odds_type": "goblin",
    }
    preds = [
        miz,
        _leg("U1", "batter_hits", 1.5, 0.92, 1.0),
        _leg("U2", "batter_hits", 0.5, 0.91, 0.3),
        _leg("U3", "batter_hits", 1.5, 0.90, 1.0),
        _leg("U4", "pitcher_strikeouts", 5.5, 0.89, 4.0),
        _leg("U5", "batter_hits", 1.5, 0.88, 1.0),
    ]
    top = build_top_bets(preds, n=5)
    assert all(t["player"] != "Jacob Misiorowski" for t in top)


def test_demon_goblin_under_unplayable():
    demon_under = {
        "player": "Mitch Bratt",
        "prop": "pitcher_strikeouts",
        "prop_label": "K",
        "line": 3.5,
        "side": "Under",
        "pick": "Under 3.5",
        "model_prob": 0.90,
        "edge": 0.40,
        "projection": 2.0,
        "book_count": 3,
        "market_prob": 0.5,
        "line_source": "prizepicks",
        "pp_odds_type": "demon",
    }
    assert _is_unplayable_on_prizepicks(demon_under) is True
    goblin_over = {
        **demon_under,
        "player": "Dylan Cease",
        "side": "Over",
        "pick": "Over 5.5",
        "line": 5.5,
        "pp_odds_type": "goblin",
        "projection": 8.0,
        "model_prob": 0.81,
    }
    assert _is_unplayable_on_prizepicks(goblin_over) is False
    std_under = {**demon_under, "pp_odds_type": "standard", "player": "Std"}
    assert _is_unplayable_on_prizepicks(std_under) is False
    top = build_top_bets(
        [
            demon_under,
            goblin_over,
            _leg("U1", "batter_hits", 1.5, 0.90, 0.9),
            _leg("U2", "batter_hits", 1.5, 0.88, 1.0),
            _leg("U3", "batter_hits", 0.5, 0.87, 0.3),
            _leg("U4", "pitcher_strikeouts", 5.5, 0.86, 4.5),
        ],
        n=5,
    )
    assert all(t["player"] != "Mitch Bratt" for t in top)
    assert any(t["player"] == "Dylan Cease" for t in top)


def test_third_best_k_makes_top_five():
    """Strong K Over ships on merit even when several K legs fill the card."""
    preds = [
        {
            "player": "A", "prop": "pitcher_strikeouts", "prop_label": "K",
            "line": 3.5, "side": "Under", "pick": "Under 3.5", "model_prob": 0.92,
            "edge": 0.35, "projection": 2.0, "book_count": 3, "market_prob": 0.5,
            "line_source": "prizepicks", "pp_odds_type": "standard",
        },
        {
            "player": "B", "prop": "pitcher_strikeouts", "prop_label": "K",
            "line": 5.5, "side": "Over", "pick": "Over 5.5", "model_prob": 0.81,
            "edge": 0.31, "projection": 8.0, "book_count": 3, "market_prob": 0.5,
            "line_source": "prizepicks",
        },
        {
            "player": "Jacob Misiorowski", "prop": "pitcher_strikeouts",
            "prop_label": "K", "line": 6.5, "side": "Over", "pick": "Over 6.5",
            "model_prob": 0.79, "edge": 0.29, "projection": 8.9, "book_count": 3,
            "market_prob": 0.5, "line_source": "prizepicks", "pp_odds_type": "goblin",
        },
        _leg("C", "batter_hits", 1.5, 0.90, 0.9),
        _leg("D", "batter_hits", 0.5, 0.70, 0.3),  # weaker — Miz should beat this
    ]
    top = build_top_bets(preds, n=5)
    names = [t["player"] for t in top]
    assert "Jacob Misiorowski" in names
    assert names.index("Jacob Misiorowski") < names.index("D")


if __name__ == "__main__":
    test_no_fake_elite_from_edge_vs_pickem()
    test_sanitize_strips_stale_elite()
    test_thin_card_when_below_floor()
    test_rejects_under_when_projection_at_or_above_line()
    test_k_over_eligible_but_not_front_loaded()
    test_weaker_k_over_does_not_beat_better_unders()
    test_demon_goblin_under_unplayable()
    test_third_best_k_makes_top_five()
    print("prop_card_guards_ok")
