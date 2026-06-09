import math


DEFAULT_ELO = 1500.0
HOME_FIELD_ELO = 24.0
K_FACTOR = 18.0


def win_probability(home_elo: float, away_elo: float) -> float:
    adjusted_home = home_elo + HOME_FIELD_ELO
    return 1 / (1 + math.pow(10, (away_elo - adjusted_home) / 400))


def update_elo(home_elo: float, away_elo: float, home_won: bool) -> tuple[float, float]:
    expected_home = win_probability(home_elo, away_elo)
    actual_home = 1.0 if home_won else 0.0
    change = K_FACTOR * (actual_home - expected_home)
    return home_elo + change, away_elo - change
