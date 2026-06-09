"""Build the full feature vector for one pre-game matchup."""

from __future__ import annotations

from datetime import date

from context import FeatureContext
from feature_registry import FEATURES, ROLLING_WINDOWS, TEAM_METRICS
from team_tracker import TeamTracker


def _metric_value(team: TeamTracker, metric: str, window: int) -> float:
    if metric == "runs_scored":
        return team.avg_runs_scored(window)
    if metric == "runs_allowed":
        return team.avg_runs_allowed(window)
    if metric in {"first_5_runs_scored", "late_runs_scored"}:
        return team.avg_runs_scored(window) * (0.58 if metric.startswith("first") else 0.42)
    if metric in {"first_5_runs_allowed", "late_runs_allowed"}:
        return team.avg_runs_allowed(window) * (0.58 if metric.startswith("first") else 0.42)
    if metric in {"ops", "obp", "slg", "iso"}:
        base = team.avg_runs_scored(window) / 9.0
        if metric == "ops":
            return base * 1.8
        if metric == "obp":
            return base * 1.2
        if metric == "slg":
            return base * 1.5
        return base * 0.35
    if metric in {"babip", "hard_hit_rate", "barrel_rate"}:
        return min(max(team.win_pct(window), 0.2), 0.8)
    if metric in {"k_rate", "bb_rate", "ground_ball_rate", "fly_ball_rate"}:
        return 0.2 + (team.avg_runs_allowed(window) / 10.0)
    if metric in {"lefty_wrc_plus", "righty_wrc_plus"}:
        return 90 + team.run_differential(window) * 8
    if metric == "starter_ip":
        return 5.5 + team.win_pct(window)
    if metric in {"bullpen_whip", "bullpen_fip", "bullpen_k_rate", "bullpen_bb_rate", "bullpen_hr_rate"}:
        return team.avg_runs_allowed(window) / 4.0
    if metric in {
        "starter_era_proxy",
        "starter_fip_proxy",
        "starter_whip_proxy",
        "starter_k_rate_proxy",
        "starter_bb_rate_proxy",
        "starter_hr_rate_proxy",
    }:
        return team.avg_runs_allowed(window)
    if metric in {"defensive_efficiency", "double_play_rate"}:
        return max(0.0, min(1.0, 0.5 + team.run_differential(window) / 20))
    if metric == "bullpen_era":
        return team.avg_runs_allowed(window) * 1.1
    if metric == "errors":
        return max(0.4, 1.2 - team.win_pct(window))
    if metric == "stolen_bases":
        return team.avg_runs_scored(window) / 3.0
    if metric in {"caught_stealing", "base_running_value", "home_runs", "extra_base_hits"}:
        return team.avg_runs_scored(window) / 4.0
    if metric in {"left_on_base_rate", "one_run_game_win_pct", "extra_inning_win_pct"}:
        return team.win_pct(window)
    return team.win_pct(window)


def build_feature_map(
    home: TeamTracker,
    away: TeamTracker,
    game_date: date,
    home_starter_era: float,
    away_starter_era: float,
    context: FeatureContext | None = None,
) -> dict[str, float]:
    context = context or FeatureContext()
    values: dict[str, float] = {
        "home_team_elo": home.elo,
        "away_team_elo": away.elo,
        "elo_difference": home.elo - away.elo,
        "home_field_advantage": 1.0,
        "home_rest_days": home.rest_days(game_date),
        "away_rest_days": away.rest_days(game_date),
        "home_travel_miles_last_3_days": 0.0,
        "away_travel_miles_last_3_days": 0.0,
        "home_win_pct": home.win_pct(),
        "away_win_pct": away.win_pct(),
        "home_run_differential": home.run_differential(),
        "away_run_differential": away.run_differential(),
        "home_wrc_plus_season": 100 + home.run_differential() * 10,
        "away_wrc_plus_season": 100 + away.run_differential() * 10,
        "home_wrc_plus_last_14": 100 + home.run_differential(14) * 10,
        "away_wrc_plus_last_14": 100 + away.run_differential(14) * 10,
        "home_bullpen_era": home.avg_runs_allowed(7) * 1.1,
        "away_bullpen_era": away.avg_runs_allowed(7) * 1.1,
        "home_bullpen_ip_last_3": 9.0,
        "away_bullpen_ip_last_3": 9.0,
        "home_starter_era": home_starter_era,
        "away_starter_era": away_starter_era,
        "home_starter_fip": home_starter_era * 0.95,
        "away_starter_fip": away_starter_era * 0.95,
        "home_starter_xfip": home_starter_era * 0.98,
        "away_starter_xfip": away_starter_era * 0.98,
        "home_starter_k_rate": max(0.12, 0.25 - (home_starter_era - 4.0) * 0.02),
        "away_starter_k_rate": max(0.12, 0.25 - (away_starter_era - 4.0) * 0.02),
        "home_starter_bb_rate": min(0.12, 0.04 + (home_starter_era - 3.5) * 0.01),
        "away_starter_bb_rate": min(0.12, 0.04 + (away_starter_era - 3.5) * 0.01),
        "home_defensive_runs_saved": home.run_differential(30),
        "away_defensive_runs_saved": away.run_differential(30),
        "park_factor_runs": context.park.park_factor_runs,
        "temperature": context.weather.temperature_f,
        "wind_speed": context.weather.wind_speed_mph,
        "wind_out_to_center": context.weather.wind_out_to_center,
        "market_home_implied_probability": context.market.home_implied_probability,
        "market_away_implied_probability": context.market.away_implied_probability,
        "closing_line_home": float(context.market.home_moneyline),
        "closing_line_away": float(context.market.away_moneyline),
        "market_total": context.market.market_total,
        "market_home_runline": context.market.home_runline,
        "market_away_runline": context.market.away_runline,
        "market_home_runline_price": float(context.market.home_runline_price),
        "market_away_runline_price": float(context.market.away_runline_price),
        "market_source_count": float(context.market.source_count),
        "park_factor_hr": context.park.park_factor_hr,
        "park_altitude_ft": context.park.altitude_ft,
        "park_left_field_ft": context.park.left_field_ft,
        "park_center_field_ft": context.park.center_field_ft,
        "park_right_field_ft": context.park.right_field_ft,
        "park_foul_territory_index": context.park.foul_territory_index,
        "weather_temperature_f": context.weather.temperature_f,
        "weather_wind_speed_mph": context.weather.wind_speed_mph,
        "weather_wind_direction_degrees": context.weather.wind_direction_degrees,
        "weather_humidity_pct": context.weather.humidity_pct,
        "weather_precipitation_probability": context.weather.precipitation_probability,
        "weather_pressure_hpa": context.weather.pressure_hpa,
        "weather_is_dome": 1.0 if context.weather.is_dome else 0.0,
        "game_hour_utc": context.game_hour_utc,
        "is_day_game": 1.0 if context.is_day_game else 0.0,
        "home_batting_avg_asof": context.home_stats.batting_avg,
        "away_batting_avg_asof": context.away_stats.batting_avg,
        "home_obp_asof": context.home_stats.obp,
        "away_obp_asof": context.away_stats.obp,
        "home_slg_asof": context.home_stats.slg,
        "away_slg_asof": context.away_stats.slg,
        "home_ops_asof": context.home_stats.ops,
        "away_ops_asof": context.away_stats.ops,
        "home_babip_asof": context.home_stats.babip,
        "away_babip_asof": context.away_stats.babip,
        "home_runs_per_game_asof": context.home_stats.runs_per_game,
        "away_runs_per_game_asof": context.away_stats.runs_per_game,
        "home_hr_per_game_asof": context.home_stats.home_runs_per_game,
        "away_hr_per_game_asof": context.away_stats.home_runs_per_game,
        "home_k_rate_asof": context.home_stats.strikeout_rate,
        "away_k_rate_asof": context.away_stats.strikeout_rate,
        "home_bb_rate_asof": context.home_stats.walk_rate,
        "away_bb_rate_asof": context.away_stats.walk_rate,
        "home_stolen_bases_per_game_asof": context.home_stats.stolen_bases_per_game,
        "away_stolen_bases_per_game_asof": context.away_stats.stolen_bases_per_game,
        "home_lob_per_game_asof": context.home_stats.left_on_base_per_game,
        "away_lob_per_game_asof": context.away_stats.left_on_base_per_game,
        "home_pitching_era_asof": context.home_stats.pitching_era,
        "away_pitching_era_asof": context.away_stats.pitching_era,
        "home_pitching_whip_asof": context.home_stats.pitching_whip,
        "away_pitching_whip_asof": context.away_stats.pitching_whip,
        "home_avg_allowed_asof": context.home_stats.pitching_avg_allowed,
        "away_avg_allowed_asof": context.away_stats.pitching_avg_allowed,
        "home_obp_allowed_asof": context.home_stats.pitching_obp_allowed,
        "away_obp_allowed_asof": context.away_stats.pitching_obp_allowed,
        "home_slg_allowed_asof": context.home_stats.pitching_slg_allowed,
        "away_slg_allowed_asof": context.away_stats.pitching_slg_allowed,
        "home_ops_allowed_asof": context.home_stats.pitching_ops_allowed,
        "away_ops_allowed_asof": context.away_stats.pitching_ops_allowed,
        "home_pitching_k9_asof": context.home_stats.strikeouts_per_9,
        "away_pitching_k9_asof": context.away_stats.strikeouts_per_9,
        "home_pitching_bb9_asof": context.home_stats.walks_per_9,
        "away_pitching_bb9_asof": context.away_stats.walks_per_9,
        "home_pitching_h9_asof": context.home_stats.hits_per_9,
        "away_pitching_h9_asof": context.away_stats.hits_per_9,
        "home_pitching_hr9_asof": context.home_stats.home_runs_per_9,
        "away_pitching_hr9_asof": context.away_stats.home_runs_per_9,
        "matchup_ops_vs_pitching_ops_allowed": context.home_stats.ops - context.away_stats.pitching_ops_allowed,
        "matchup_slg_vs_pitching_slg_allowed": context.home_stats.slg - context.away_stats.pitching_slg_allowed,
        "matchup_obp_vs_pitching_obp_allowed": context.home_stats.obp - context.away_stats.pitching_obp_allowed,
        "matchup_run_creation_gap": context.home_stats.runs_per_game - context.away_stats.runs_per_game,
        "home_road_context": 1.0,
    }

    for side, team in (("home", home), ("away", away)):
        for metric in TEAM_METRICS:
            for window in ROLLING_WINDOWS:
                values[f"{side}_{metric}_last_{window}"] = _metric_value(team, metric, window)

    return values


def build_feature_vector(
    home: TeamTracker,
    away: TeamTracker,
    game_date: date,
    home_starter_era: float,
    away_starter_era: float,
    context: FeatureContext | None = None,
) -> list[float]:
    values = build_feature_map(home, away, game_date, home_starter_era, away_starter_era, context)
    return [float(values[name]) for name in FEATURES]
