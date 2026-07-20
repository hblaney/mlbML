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
    assert _confidence(0.20, 3, side="Under", model_prob=0.59) != "Elite"
    assert _confidence(0.25, 3, side="Under", model_prob=TOP_BET_MIN_CONF) == "Elite"


def test_sanitize_strips_stale_elite():
    row = _sanitize_leg(_leg("A", "batter_total_bases", 1.5, 0.57, 1.2))
    assert row["confidence"] != "Elite"
    assert row.get("below_oos_threshold") is True


def test_always_fields_five_legs():
    preds = [
        _leg("P1", "batter_total_bases", 1.5, 0.58, 1.2),
        _leg("P2", "batter_total_bases", 1.5, 0.57, 1.3),
        _leg("P3", "batter_hits", 1.5, 0.56, 1.1),
        _leg("P4", "pitcher_strikeouts", 5.5, 0.55, 5.0),
        _leg("P5", "batter_hits_runs_rbis", 1.5, 0.54, 1.2),
        _leg("P6", "batter_total_bases", 1.5, 0.53, 1.4),  # would be 3rd TB — diversity
    ]
    top = build_top_bets(preds, n=5)
    assert len(top) == 5
    assert len({t["player"] for t in top}) == 5
    assert all(t["confidence"] != "Elite" for t in top)
    parlay = build_parlay(preds)
    assert parlay["n_legs"] == 5
    assert parlay.get("no_bet") is None
    assert parlay.get("card_quality") == "thin"


def test_rejects_under_when_projection_at_or_above_line():
    preds = [
        _leg("Bad", "batter_total_bases", 1.5, 0.80, 1.6),  # coin flip / wrong side
        _leg("P1", "batter_total_bases", 1.5, 0.58, 1.2),
        _leg("P2", "batter_hits", 1.5, 0.57, 1.1),
        _leg("P3", "pitcher_strikeouts", 5.5, 0.56, 5.0),
        _leg("P4", "batter_hits_runs_rbis", 1.5, 0.55, 1.2),
        _leg("P5", "batter_rbis", 0.5, 0.54, 0.3),
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
    # Stronger Under should rank above Miz when sorting by model_prob.
    stronger = _leg("Ace Under", "batter_total_bases", 1.5, 0.86, 1.0)
    preds = [
        miz,
        stronger,
        _leg("P2", "batter_hits", 1.5, 0.72, 1.1),
        _leg("P3", "pitcher_strikeouts", 5.5, 0.70, 5.0),
        _leg("P4", "batter_hits_runs_rbis", 1.5, 0.68, 1.2),
        _leg("P5", "batter_rbis", 0.5, 0.66, 0.3),
    ]
    assert any(p["player"] == "Jacob Misiorowski" for p in _k_over_lane(preds))
    top = build_top_bets(preds, n=5)
    assert top[0]["player"] == "Ace Under"
    assert any(t["player"] == "Jacob Misiorowski" for t in top)
    assert len(top) == 5


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
        _leg("U1", "batter_total_bases", 1.5, 0.85, 1.0),
        _leg("U2", "batter_total_bases", 1.5, 0.84, 1.0),
        _leg("U3", "batter_hits", 1.5, 0.83, 1.0),
        _leg("U4", "pitcher_strikeouts", 5.5, 0.82, 4.0),
        _leg("U5", "batter_hits", 1.5, 0.81, 1.0),
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
            _leg("U1", "batter_total_bases", 1.5, 0.76, 0.9),
            _leg("U2", "batter_total_bases", 1.5, 0.73, 1.0),
            _leg("U3", "batter_hits", 1.5, 0.72, 1.0),
            _leg("U4", "batter_hits", 1.5, 0.70, 1.0),
        ],
        n=5,
    )
    assert all(t["player"] != "Mitch Bratt" for t in top)
    assert any(t["player"] == "Dylan Cease" for t in top)


def test_third_best_k_makes_top_five():
    """#3 by model_prob must ship even if props 1-3 are all strikeouts."""
    preds = [
        {
            "player": "A", "prop": "pitcher_strikeouts", "prop_label": "K",
            "line": 3.5, "side": "Under", "pick": "Under 3.5", "model_prob": 0.85,
            "edge": 0.35, "projection": 2.0, "book_count": 3, "market_prob": 0.5,
            "line_source": "prizepicks",
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
        _leg("C", "batter_total_bases", 1.5, 0.76, 0.9),
        _leg("D", "batter_total_bases", 1.5, 0.73, 1.0),
        _leg("E", "batter_hits", 1.5, 0.72, 1.0),
    ]
    top = build_top_bets(preds, n=5)
    names = [t["player"] for t in top]
    assert "Jacob Misiorowski" in names
    assert names.index("Jacob Misiorowski") == 2


if __name__ == "__main__":
    test_no_fake_elite_from_edge_vs_pickem()
    test_sanitize_strips_stale_elite()
    test_always_fields_five_legs()
    test_rejects_under_when_projection_at_or_above_line()
    test_k_over_eligible_but_not_front_loaded()
    test_weaker_k_over_does_not_beat_better_unders()
    test_demon_goblin_under_unplayable()
    print("prop_card_guards_ok")
