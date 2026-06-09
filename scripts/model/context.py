"""External pre-game context: market, weather, and ballpark conditions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TeamStatSnapshot:
    batting_avg: float = 0.0
    obp: float = 0.0
    slg: float = 0.0
    ops: float = 0.0
    babip: float = 0.0
    runs_per_game: float = 0.0
    home_runs_per_game: float = 0.0
    strikeout_rate: float = 0.0
    walk_rate: float = 0.0
    stolen_bases_per_game: float = 0.0
    left_on_base_per_game: float = 0.0
    pitching_era: float = 0.0
    pitching_whip: float = 0.0
    pitching_avg_allowed: float = 0.0
    pitching_obp_allowed: float = 0.0
    pitching_slg_allowed: float = 0.0
    pitching_ops_allowed: float = 0.0
    strikeouts_per_9: float = 0.0
    walks_per_9: float = 0.0
    hits_per_9: float = 0.0
    home_runs_per_9: float = 0.0


@dataclass(frozen=True)
class MarketSnapshot:
    home_implied_probability: float = 0.5
    away_implied_probability: float = 0.5
    home_moneyline: int = 0
    away_moneyline: int = 0
    market_total: float = 8.5
    over_price: int = 0
    under_price: int = 0
    home_runline: float = -1.5
    away_runline: float = 1.5
    home_runline_price: int = 0
    away_runline_price: int = 0
    source_count: int = 0


@dataclass(frozen=True)
class WeatherSnapshot:
    temperature_f: float = 72.0
    wind_speed_mph: float = 0.0
    wind_direction_degrees: float = 0.0
    wind_out_to_center: float = 0.0
    humidity_pct: float = 50.0
    precipitation_probability: float = 0.0
    pressure_hpa: float = 1013.0
    is_dome: bool = False


@dataclass(frozen=True)
class ParkSnapshot:
    park_factor_runs: float = 1.0
    park_factor_hr: float = 1.0
    altitude_ft: float = 500.0
    left_field_ft: float = 330.0
    center_field_ft: float = 400.0
    right_field_ft: float = 330.0
    foul_territory_index: float = 1.0


@dataclass(frozen=True)
class FeatureContext:
    market: MarketSnapshot = MarketSnapshot()
    weather: WeatherSnapshot = WeatherSnapshot()
    park: ParkSnapshot = ParkSnapshot()
    home_stats: TeamStatSnapshot = TeamStatSnapshot()
    away_stats: TeamStatSnapshot = TeamStatSnapshot()
    game_hour_utc: float = 0.0
    is_day_game: bool = False
