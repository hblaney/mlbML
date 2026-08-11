from market_pick_policy import resolve_published_side


def test_no_market_keeps_gbm():
    home, override = resolve_published_side(0.58, 0.42, None, None)
    assert home is True
    assert override is False


def test_agreement_no_override():
    home, override = resolve_published_side(0.60, 0.40, 0.57, 0.43)
    assert home is True
    assert override is False


def test_gbm_dog_flips_to_market():
    # GBM likes away, market likes home
    home, override = resolve_published_side(0.44, 0.56, 0.58, 0.42)
    assert home is True
    assert override is True


def test_gbm_home_dog_flips_to_away_favorite():
    home, override = resolve_published_side(0.55, 0.45, 0.47, 0.53)
    assert home is False
    assert override is True


if __name__ == "__main__":
    test_no_market_keeps_gbm()
    test_agreement_no_override()
    test_gbm_dog_flips_to_market()
    test_gbm_home_dog_flips_to_away_favorite()
    print("ok")
