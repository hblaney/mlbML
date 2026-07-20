"""Pre-publish guards must catch Valdez-style absurd projections before ship."""

from __future__ import annotations

from prop_publish_guards import assert_payload_sane, scrub_predictions, violation_reason


def test_sb_under_unbettable():
    row = {
        "player": "Slow Guy",
        "prop": "batter_stolen_bases",
        "side": "Under",
        "line": 0.5,
        "projection": 0.01,
        "model_prob": 0.98,
    }
    assert violation_reason(row) == "unbettable_prop:batter_stolen_bases"


def test_valdez_hr_rejected():
    row = {
        "player": "Esmerlyn Valdez",
        "prop": "batter_home_runs",
        "side": "Over",
        "line": 0.5,
        "projection": 1.242,
        "model_prob": 0.999,
    }
    assert violation_reason(row) is not None


def test_sane_hr_allowed():
    row = {
        "player": "Normal",
        "prop": "batter_home_runs",
        "side": "Over",
        "line": 0.5,
        "projection": 0.35,
        "model_prob": 0.30,
    }
    assert violation_reason(row) is None


def test_scrub_drops_absurd_keeps_sane():
    bad = {
        "player": "Esmerlyn Valdez",
        "prop": "batter_home_runs",
        "side": "Over",
        "line": 0.5,
        "projection": 1.242,
        "model_prob": 0.999,
    }
    good = {
        "player": "Dylan Cease",
        "prop": "pitcher_strikeouts",
        "side": "Over",
        "line": 5.5,
        "projection": 8.2,
        "model_prob": 0.74,
    }
    kept, dropped = scrub_predictions([bad, good])
    assert len(kept) == 1 and kept[0]["player"] == "Dylan Cease"
    assert len(dropped) == 1 and dropped[0]["player"] == "Esmerlyn Valdez"


def test_assert_payload_sane_fails_closed():
    payload = {
        "predictions": [{
            "player": "Esmerlyn Valdez",
            "prop": "batter_home_runs",
            "side": "Over",
            "line": 0.5,
            "projection": 1.242,
            "model_prob": 0.999,
        }],
        "top_bets": [],
        "parlay": {"legs": []},
    }
    try:
        assert_payload_sane(payload)
        raised = False
    except SystemExit:
        raised = True
    assert raised


if __name__ == "__main__":
    test_sb_under_unbettable()
    test_valdez_hr_rejected()
    test_sane_hr_allowed()
    test_scrub_drops_absurd_keeps_sane()
    test_assert_payload_sane_fails_closed()
    print("prop_publish_guards_ok")
