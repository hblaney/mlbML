"""Feature registry for the MLB prediction model.

The first production model should start with features that can be measured reliably
before first pitch. The registry intentionally supports 200+ fields, but accuracy
comes from clean data and validation, not from feature count alone.
"""

CORE_FEATURES = [
    "home_team_elo",
    "away_team_elo",
    "elo_difference",
    "home_field_advantage",
    "home_rest_days",
    "away_rest_days",
    "home_travel_miles_last_3_days",
    "away_travel_miles_last_3_days",
    "home_win_pct",
    "away_win_pct",
    "home_run_differential",
    "away_run_differential",
    "home_wrc_plus_season",
    "away_wrc_plus_season",
    "home_wrc_plus_last_14",
    "away_wrc_plus_last_14",
    "home_bullpen_era",
    "away_bullpen_era",
    "home_bullpen_ip_last_3",
    "away_bullpen_ip_last_3",
    "home_starter_era",
    "away_starter_era",
    "home_starter_fip",
    "away_starter_fip",
    "home_starter_xfip",
    "away_starter_xfip",
    "home_starter_k_rate",
    "away_starter_k_rate",
    "home_starter_bb_rate",
    "away_starter_bb_rate",
    "home_defensive_runs_saved",
    "away_defensive_runs_saved",
    "park_factor_runs",
    "temperature",
    "wind_speed",
    "wind_out_to_center",
    "market_home_implied_probability",
    "market_away_implied_probability",
    "closing_line_home",
    "closing_line_away",
    "market_total",
    "market_home_runline",
    "market_away_runline",
    "market_home_runline_price",
    "market_away_runline_price",
    "market_source_count",
    "park_factor_hr",
    "park_altitude_ft",
    "park_left_field_ft",
    "park_center_field_ft",
    "park_right_field_ft",
    "park_foul_territory_index",
    "weather_temperature_f",
    "weather_wind_speed_mph",
    "weather_wind_direction_degrees",
    "weather_humidity_pct",
    "weather_precipitation_probability",
    "weather_pressure_hpa",
    "weather_is_dome",
    "game_hour_utc",
    "is_day_game",
    "home_batting_avg_asof",
    "away_batting_avg_asof",
    "home_obp_asof",
    "away_obp_asof",
    "home_slg_asof",
    "away_slg_asof",
    "home_ops_asof",
    "away_ops_asof",
    "home_babip_asof",
    "away_babip_asof",
    "home_runs_per_game_asof",
    "away_runs_per_game_asof",
    "home_hr_per_game_asof",
    "away_hr_per_game_asof",
    "home_k_rate_asof",
    "away_k_rate_asof",
    "home_bb_rate_asof",
    "away_bb_rate_asof",
    "home_stolen_bases_per_game_asof",
    "away_stolen_bases_per_game_asof",
    "home_lob_per_game_asof",
    "away_lob_per_game_asof",
    "home_pitching_era_asof",
    "away_pitching_era_asof",
    "home_pitching_whip_asof",
    "away_pitching_whip_asof",
    "home_avg_allowed_asof",
    "away_avg_allowed_asof",
    "home_obp_allowed_asof",
    "away_obp_allowed_asof",
    "home_slg_allowed_asof",
    "away_slg_allowed_asof",
    "home_ops_allowed_asof",
    "away_ops_allowed_asof",
    "home_pitching_k9_asof",
    "away_pitching_k9_asof",
    "home_pitching_bb9_asof",
    "away_pitching_bb9_asof",
    "home_pitching_h9_asof",
    "away_pitching_h9_asof",
    "home_pitching_hr9_asof",
    "away_pitching_hr9_asof",
    "matchup_ops_vs_pitching_ops_allowed",
    "matchup_slg_vs_pitching_slg_allowed",
    "matchup_obp_vs_pitching_obp_allowed",
    "matchup_run_creation_gap",
    "home_road_context"
]

ROLLING_WINDOWS = [3, 5, 7, 10, 14, 21, 30, 45, 60, 90]
TEAM_METRICS = [
    "runs_scored",
    "runs_allowed",
    "first_5_runs_scored",
    "first_5_runs_allowed",
    "late_runs_scored",
    "late_runs_allowed",
    "ops",
    "obp",
    "slg",
    "iso",
    "babip",
    "k_rate",
    "bb_rate",
    "hard_hit_rate",
    "barrel_rate",
    "ground_ball_rate",
    "fly_ball_rate",
    "lefty_wrc_plus",
    "righty_wrc_plus",
    "starter_ip",
    "bullpen_whip",
    "bullpen_fip",
    "bullpen_k_rate",
    "bullpen_bb_rate",
    "bullpen_hr_rate",
    "starter_era_proxy",
    "starter_fip_proxy",
    "starter_whip_proxy",
    "starter_k_rate_proxy",
    "starter_bb_rate_proxy",
    "starter_hr_rate_proxy",
    "defensive_efficiency",
    "double_play_rate",
    "errors",
    "stolen_bases",
    "caught_stealing",
    "base_running_value",
    "home_runs",
    "extra_base_hits",
    "left_on_base_rate",
    "one_run_game_win_pct",
    "extra_inning_win_pct"
]


def rolling_features() -> list[str]:
    features: list[str] = []

    for side in ("home", "away"):
        for metric in TEAM_METRICS:
            for window in ROLLING_WINDOWS:
                features.append(f"{side}_{metric}_last_{window}")

    return features


FEATURES = CORE_FEATURES + rolling_features()


def validate_feature_count(minimum: int = 200) -> None:
    if len(FEATURES) < minimum:
        raise RuntimeError(f"Expected at least {minimum} features, found {len(FEATURES)}")


if __name__ == "__main__":
    validate_feature_count()
    print(f"registered_features={len(FEATURES)}")
