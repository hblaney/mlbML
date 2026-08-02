"""Guards against the junk-card failure mode shipping again."""

from __future__ import annotations

from generate_prop_predictions import (
    TOP_BET_MIN_CONF,
    _batter_over_lane,
    _confidence,
    _is_thin_under,
    _is_unplayable_on_prizepicks,
    _k_over_lane,
    _sanitize_leg,
    _under_proj_gap,
    build_parlay,
    build_top_bets,
    K_UNDER_ACE_LINE,
    K_UNDER_ACE_MIN_GAP,
)


def _leg(player: str, prop: str, line: float, model_prob: float, projection: float) -> dict:
    # Keep test Unders on the legal side of the thin-projection gate.
    min_gap = _under_proj_gap(prop)
    if prop == "pitcher_strikeouts" and float(line) >= K_UNDER_ACE_LINE:
        min_gap = max(min_gap, K_UNDER_ACE_MIN_GAP)
    safe_proj = min(float(projection), float(line) - min_gap - 0.05)
    return {
        "player": player,
        "prop": prop,
        "prop_label": prop,
        "line": line,
        "side": "Under",
        "pick": f"Under {line}",
        "model_prob": model_prob,
        "edge": model_prob - 0.5,
        "projection": safe_proj,
        "book_count": 3,
        "market_prob": 0.5,
        "confidence": "Elite",  # stale bad tag — sanitizer must kill this
        "line_source": "prizepicks",
        "pp_odds_type": "standard",  # Under only playable on standard
        "market_is_pickem": True,
    }


def test_no_fake_elite_from_edge_vs_pickem():
    assert _confidence(0.20, 3, side="Under", model_prob=0.71) != "Elite"
    assert _confidence(0.25, 3, side="Under", model_prob=0.72) == "Elite"
    # PrizePicks pick'em must never mint Elite just because edge looks fat vs 0.5.
    assert _confidence(0.30, 0, side="Under", model_prob=0.85, market_is_pickem=True) != "Elite"


def test_rejects_thin_and_ace_k_unders():
    gasser = {
        "player": "Robert Gasser",
        "prop": "pitcher_strikeouts",
        "side": "Under",
        "line": 5.0,
        "projection": 4.83,
        "model_prob": 0.60,
    }
    yamamoto = {
        "player": "Yoshinobu Yamamoto",
        "prop": "pitcher_strikeouts",
        "side": "Under",
        "line": 6.5,
        "projection": 5.18,
        "model_prob": 0.68,
    }
    solid = {
        "player": "Solid",
        "prop": "pitcher_strikeouts",
        "side": "Under",
        "line": 5.5,
        "projection": 4.2,
        "model_prob": 0.70,
    }
    assert _is_thin_under(gasser) is True
    assert _is_thin_under(yamamoto) is True
    assert _is_thin_under(solid) is False
    top = build_top_bets(
        [
            {**gasser, "edge": 0.10, "book_count": 0, "line_source": "prizepicks", "pp_odds_type": "standard", "market_is_pickem": True},
            {**yamamoto, "edge": 0.18, "book_count": 0, "line_source": "prizepicks", "pp_odds_type": "standard", "market_is_pickem": True},
            {**solid, "edge": 0.20, "book_count": 0, "line_source": "prizepicks", "pp_odds_type": "standard", "market_is_pickem": True},
            _leg("H1", "batter_hits", 1.5, 0.80, 1.0),
            _leg("H2", "batter_hits", 1.5, 0.78, 1.0),
        ],
        n=5,
    )
    names = {t["player"] for t in top}
    assert "Robert Gasser" not in names
    assert "Yoshinobu Yamamoto" not in names
    assert "Solid" in names


def test_top_five_caps_strikeout_legs():
    preds = [
        _leg(f"K{i}", "pitcher_strikeouts", 5.5, 0.90 - i * 0.01, 4.0)
        for i in range(5)
    ] + [
        _leg("H1", "batter_hits", 1.5, 0.70, 1.0),
        _leg("H2", "batter_total_bases", 1.5, 0.69, 1.0),
        _leg("H3", "batter_hits", 0.5, 0.68, 0.2),
    ]
    top = build_top_bets(preds, n=5)
    k_legs = [t for t in top if t["prop"] == "pitcher_strikeouts"]
    assert len(k_legs) <= 2
    assert any(t["prop"].startswith("batter_") for t in top)


def _over_leg(player: str, prop: str, line: float, model_prob: float, projection: float) -> dict:
    return {
        "player": player,
        "prop": prop,
        "prop_label": prop,
        "line": line,
        "side": "Over",
        "pick": f"Over {line}",
        "model_prob": model_prob,
        "edge": model_prob - 0.5,
        "projection": projection,
        "book_count": 0,
        "market_prob": 0.5,
        "confidence": "Low",
        "line_source": "prizepicks",
        "pp_odds_type": "goblin",
        "market_is_pickem": True,
        "lineup_confirmed": True,
    }


def test_top_five_mixes_batter_overs_not_just_ks():
    """When Unders are demon/unplayable, Top 5 still mixes hits/TB Overs with Ks."""
    demon_unders = [
        {
            **_leg(f"Demon{i}", "batter_hits", 1.5, 0.80 - i * 0.01, 0.9),
            "pp_odds_type": "demon",
        }
        for i in range(3)
    ]
    k_overs = [
        {
            "player": f"K{i}",
            "prop": "pitcher_strikeouts",
            "prop_label": "K",
            "line": 5.5,
            "side": "Over",
            "pick": "Over 5.5",
            "model_prob": 0.72 - i * 0.01,
            "edge": 0.22,
            "projection": 7.0,
            "book_count": 0,
            "market_prob": 0.5,
            "line_source": "prizepicks",
            "pp_odds_type": "goblin",
            "market_is_pickem": True,
        }
        for i in range(5)
    ]
    batter_overs = [
        _over_leg("Hit1", "batter_hits", 0.5, 0.70, 1.2),
        _over_leg("TB1", "batter_total_bases", 0.5, 0.68, 1.4),
        _over_leg("Hit2", "batter_hits", 0.5, 0.66, 1.1),
    ]
    preds = demon_unders + k_overs + batter_overs
    assert _batter_over_lane(preds)
    top = build_top_bets(preds, n=5)
    assert any(t["prop"].startswith("batter_") and t["side"] == "Over" for t in top)
    assert sum(1 for t in top if t["prop"] == "pitcher_strikeouts") <= 2
    assert all(t.get("pp_odds_type") != "demon" or t["side"] != "Under" for t in top)


def test_batter_over_can_earn_high_confidence():
    assert _confidence(0.20, 0, side="Over", model_prob=0.71, prop="batter_hits", market_is_pickem=True) == "High"
    assert _confidence(0.15, 0, side="Over", model_prob=0.63, prop="batter_total_bases", market_is_pickem=True) == "Medium"


def test_sanitize_strips_stale_elite():
    row = _sanitize_leg(_leg("A", "batter_hits", 1.5, 0.57, 1.2))
    assert row["confidence"] != "Elite"
    assert row.get("below_oos_threshold") is True


def test_thin_card_when_below_floor():
    """Do not pad Top 5 with sub-threshold or banned-market junk."""
    preds = [
        _leg("P1", "batter_rbis", 1.5, 0.90, 1.0),  # banned market (no runner id in sim)
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
        _leg("U5", "batter_total_bases", 1.5, 0.70, 1.0),
    ]
    top5 = build_top_bets(strong, n=5)
    assert len(top5) == 5
    assert len({t["player"] for t in top5}) == 5
    assert all(t["prop"] in ("batter_hits", "batter_total_bases", "pitcher_strikeouts") for t in top5)
    # Cap: ≤2 per prop market (and ≤2 strikeouts).
    assert all(
        sum(1 for t in top5 if t["prop"] == prop) <= 2
        for prop in ("batter_hits", "batter_total_bases", "pitcher_strikeouts")
    )
    parlay = build_parlay(strong)
    assert parlay["n_legs"] == 5
    assert parlay.get("flex_cash_rate_oos") is None


def test_rejects_under_when_projection_at_or_above_line():
    bad = {
        "player": "Bad",
        "prop": "batter_hits",
        "prop_label": "batter_hits",
        "line": 1.5,
        "side": "Under",
        "pick": "Under 1.5",
        "model_prob": 0.90,
        "edge": 0.40,
        "projection": 1.6,  # at/above line — must not ship
        "book_count": 3,
        "market_prob": 0.5,
        "line_source": "prizepicks",
        "pp_odds_type": "standard",
    }
    preds = [
        bad,
        _leg("P1", "batter_hits", 1.5, 0.89, 1.1),
        _leg("P2", "batter_hits", 0.5, 0.88, 0.3),
        _leg("P3", "pitcher_strikeouts", 5.5, 0.87, 5.0),
        _leg("P4", "batter_total_bases", 1.5, 0.86, 1.0),
        _leg("P5", "pitcher_strikeouts", 6.5, 0.85, 5.0),
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
        _leg("U3", "batter_total_bases", 1.5, 0.90, 1.0),
        _leg("U4", "pitcher_strikeouts", 5.5, 0.89, 4.0),
        _leg("U5", "batter_total_bases", 2.5, 0.88, 1.5),
    ]
    top = build_top_bets(preds, n=5)
    # Stronger Unders fill the card; the weaker K Over stays off.
    assert all(t["player"] != "Jacob Misiorowski" for t in top)
    assert {t["player"] for t in top} == {"U1", "U2", "U3", "U4", "U5"}


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
    """Strong K Over can ship, but the card caps strikeouts at 2 legs."""
    preds = [
        {
            "player": "A", "prop": "pitcher_strikeouts", "prop_label": "K",
            "line": 3.5, "side": "Under", "pick": "Under 3.5", "model_prob": 0.92,
            "edge": 0.35, "projection": 2.0, "book_count": 3, "market_prob": 0.5,
            "line_source": "prizepicks", "pp_odds_type": "standard",
        },
        {
            "player": "Jacob Misiorowski", "prop": "pitcher_strikeouts",
            "prop_label": "K", "line": 6.5, "side": "Over", "pick": "Over 6.5",
            "model_prob": 0.79, "edge": 0.29, "projection": 8.9, "book_count": 3,
            "market_prob": 0.5, "line_source": "prizepicks", "pp_odds_type": "goblin",
        },
        _leg("C", "batter_hits", 1.5, 0.90, 0.9),
        _leg("D", "batter_hits", 0.5, 0.70, 0.3),
        _leg("E", "batter_total_bases", 1.5, 0.68, 1.0),
    ]
    top = build_top_bets(preds, n=5)
    names = [t["player"] for t in top]
    assert "Jacob Misiorowski" in names
    assert sum(1 for t in top if t["prop"] == "pitcher_strikeouts") <= 2
    assert "C" in names  # batter diversity still ships alongside the K Over


def test_unconfirmed_batter_excluded_from_card():
    confirmed = {**_leg("Confirmed", "batter_hits", 1.5, 0.85, 1.0), "lineup_confirmed": True}
    scratched = {**_leg("Scratched", "batter_hits", 1.5, 0.95, 0.8), "lineup_confirmed": False}
    top = build_top_bets([scratched, confirmed], n=5)
    names = [t["player"] for t in top]
    assert "Scratched" not in names
    assert "Confirmed" in names


def test_max_two_legs_per_game():
    preds = [
        {**_leg(f"G1P{i}", "batter_hits", 1.5, 0.90 - i * 0.01, 1.0), "matchup": "NYY @ BOS", "team": "NYY"}
        for i in range(4)
    ] + [
        {**_leg("OtherGame", "batter_total_bases", 1.5, 0.70, 1.0), "matchup": "LAD @ SD", "team": "LAD"},
        {**_leg("OtherGame2", "batter_total_bases", 2.5, 0.69, 1.5), "matchup": "CHC @ MIL", "team": "CHC"},
    ]
    top = build_top_bets(preds, n=5)
    same_game = [t for t in top if t.get("matchup") == "NYY @ BOS"]
    assert len(same_game) == 2
    assert any(t["player"] == "OtherGame" for t in top)


def test_no_pitcher_vs_opposing_batter_contradiction():
    pitcher = {
        "player": "Starter", "prop": "pitcher_hits_allowed", "prop_label": "HA",
        "line": 5.5, "side": "Under", "pick": "Under 5.5", "model_prob": 0.90,
        "edge": 0.40, "projection": 4.0, "book_count": 3, "market_prob": 0.5,
        "line_source": "prizepicks", "pp_odds_type": "standard",
        "matchup": "NYY @ BOS", "team": "BOS",
    }
    opp_batter_over = {
        **_leg("OppBat", "batter_hits", 0.5, 0.88, 1.2),
        "side": "Over", "pick": "Over 0.5",
        "matchup": "NYY @ BOS", "team": "NYY", "lineup_confirmed": True,
    }
    top = build_top_bets([pitcher, opp_batter_over], n=5)
    names = [t["player"] for t in top]
    # Pitcher leg is stronger and first; contradictory opposing batter must drop.
    assert "Starter" in names
    assert "OppBat" not in names


def test_started_or_next_day_games_blocked():
    from datetime import datetime, timedelta, timezone

    started = {
        **_leg("Started", "batter_hits", 1.5, 0.95, 1.0),
        "lineup_confirmed": True,
        "commence_time": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    }
    tomorrow = {
        **_leg("Tomorrow", "batter_hits", 1.5, 0.94, 1.0),
        "lineup_confirmed": True,
        "commence_time": (datetime.now(timezone.utc) + timedelta(days=1, hours=6)).isoformat(),
    }
    ok = _leg("Playable", "batter_hits", 1.5, 0.80, 1.0)  # no time = allowed
    top = build_top_bets([started, tomorrow, ok], n=5)
    names = [t["player"] for t in top]
    assert "Started" not in names
    assert "Tomorrow" not in names
    assert "Playable" in names


def test_no_bet_when_card_is_negative_ev():
    # Two barely-qualified legs: 2-power EV = 3*p^2 - 1 < 0 at p=0.55.
    weak = [
        _leg("W1", "batter_hits", 1.5, 0.55, 1.0),
        _leg("W2", "batter_hits", 0.5, 0.55, 0.3),
    ]
    # Floor filters these (0.58) so we test the EV math directly too.
    from generate_prop_predictions import _card_ev

    ev, kind = _card_ev([0.55, 0.55])
    assert kind == "power" and ev < 0
    ev5, kind5 = _card_ev([0.75] * 5)
    assert kind5 == "flex" and ev5 > 0
    parlay = build_parlay(weak)
    assert parlay["no_bet"] is True


def test_strong_card_is_a_bet_with_ev():
    strong = [
        _leg("U1", "batter_hits", 1.5, 0.80, 1.0),
        _leg("U2", "batter_hits", 0.5, 0.78, 0.3),
        _leg("U3", "pitcher_strikeouts", 5.5, 0.75, 4.0),
        _leg("U4", "pitcher_strikeouts", 6.5, 0.72, 5.0),
        _leg("U5", "batter_total_bases", 1.5, 0.70, 1.0),
    ]
    parlay = build_parlay(strong)
    assert parlay["no_bet"] is False
    assert parlay["ev_per_dollar"] is not None and parlay["ev_per_dollar"] > 0
    assert parlay["n_legs"] >= 2


if __name__ == "__main__":
    test_no_fake_elite_from_edge_vs_pickem()
    test_sanitize_strips_stale_elite()
    test_thin_card_when_below_floor()
    test_rejects_under_when_projection_at_or_above_line()
    test_rejects_thin_and_ace_k_unders()
    test_top_five_caps_strikeout_legs()
    test_top_five_mixes_batter_overs_not_just_ks()
    test_batter_over_can_earn_high_confidence()
    test_k_over_eligible_but_not_front_loaded()
    test_weaker_k_over_does_not_beat_better_unders()
    test_demon_goblin_under_unplayable()
    test_third_best_k_makes_top_five()
    test_unconfirmed_batter_excluded_from_card()
    test_max_two_legs_per_game()
    test_no_pitcher_vs_opposing_batter_contradiction()
    test_started_or_next_day_games_blocked()
    test_no_bet_when_card_is_negative_ev()
    test_strong_card_is_a_bet_with_ev()
    print("prop_card_guards_ok")
