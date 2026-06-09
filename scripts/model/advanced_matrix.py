"""Dynamic advanced feature matrix built from real pre-game sources."""

from __future__ import annotations

from datetime import datetime

from historical_odds import HistoricalOddsStore
from mlb_api import GameRecord, fetch_pitcher_season_era, load_team_abbreviations
from park_factors import park_for_team
from team_stats_provider import raw_team_stats_as_of
from team_tracker import LeagueState
from weather import fetch_historical_weather


def to_float(value: object) -> float | None:
    if value in (None, "", "-.--"):
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def add_numeric_stats(row: dict[str, float], prefix: str, stats: dict) -> None:
    for key, value in stats.items():
        numeric = to_float(value)
        if numeric is not None:
            row[f"{prefix}_{key}"] = numeric


def add_rate_features(row: dict[str, float], prefix: str) -> None:
    pa = max(row.get(f"{prefix}_hitting_plateAppearances", 0.0), 1.0)
    games = max(row.get(f"{prefix}_hitting_gamesPlayed", 0.0), 1.0)
    innings = row.get(f"{prefix}_pitching_inningsPitched", 0.0)
    if innings <= 0:
        innings = max(row.get(f"{prefix}_pitching_outs", 0.0) / 3.0, 1.0)

    row[f"{prefix}_hitting_k_rate_real"] = row.get(f"{prefix}_hitting_strikeOuts", 0.0) / pa
    row[f"{prefix}_hitting_bb_rate_real"] = row.get(f"{prefix}_hitting_baseOnBalls", 0.0) / pa
    row[f"{prefix}_hitting_hr_per_game_real"] = row.get(f"{prefix}_hitting_homeRuns", 0.0) / games
    row[f"{prefix}_hitting_runs_per_game_real"] = row.get(f"{prefix}_hitting_runs", 0.0) / games
    row[f"{prefix}_pitching_hr9_real"] = row.get(f"{prefix}_pitching_homeRuns", 0.0) * 9 / innings
    row[f"{prefix}_pitching_k9_real"] = row.get(f"{prefix}_pitching_strikeOuts", 0.0) * 9 / innings
    row[f"{prefix}_pitching_bb9_real"] = row.get(f"{prefix}_pitching_baseOnBalls", 0.0) * 9 / innings


def add_differences(row: dict[str, float]) -> None:
    for key in list(row.keys()):
        if not key.startswith("home_"):
            continue
        away_key = "away_" + key[5:]
        if away_key in row:
            row[f"diff_{key[5:]}"] = row[key] - row[away_key]

    matchup_pairs = [
        ("hitting_ops", "pitching_ops"),
        ("hitting_obp", "pitching_obp"),
        ("hitting_slg", "pitching_slg"),
        ("hitting_avg", "pitching_avg"),
        ("hitting_runs_per_game_real", "pitching_era"),
        ("hitting_hr_per_game_real", "pitching_hr9_real"),
        ("hitting_k_rate_real", "pitching_k9_real"),
        ("hitting_bb_rate_real", "pitching_bb9_real"),
    ]
    for offense, defense in matchup_pairs:
        home_off = row.get(f"home_{offense}", 0.0)
        away_off = row.get(f"away_{offense}", 0.0)
        home_def = row.get(f"home_{defense}", 0.0)
        away_def = row.get(f"away_{defense}", 0.0)
        row[f"home_matchup_{offense}_vs_away_{defense}"] = home_off - away_def
        row[f"away_matchup_{offense}_vs_home_{defense}"] = away_off - home_def
        row[f"diff_matchup_{offense}_vs_{defense}"] = (
            row[f"home_matchup_{offense}_vs_away_{defense}"]
            - row[f"away_matchup_{offense}_vs_home_{defense}"]
        )


class AdvancedMatrixBuilder:
    def __init__(self, include_weather: bool = False) -> None:
        self.odds = HistoricalOddsStore()
        self.team_abbr = load_team_abbreviations()
        self.include_weather = include_weather

    def build_row(self, game: GameRecord, state: LeagueState) -> dict[str, float]:
        row: dict[str, float] = {}
        home = state.team(game.home_team_id)
        away = state.team(game.away_team_id)
        home_hitting, home_pitching = raw_team_stats_as_of(game.home_team_id, game.game_date)
        away_hitting, away_pitching = raw_team_stats_as_of(game.away_team_id, game.game_date)

        add_numeric_stats(row, "home_hitting", home_hitting)
        add_numeric_stats(row, "home_pitching", home_pitching)
        add_numeric_stats(row, "away_hitting", away_hitting)
        add_numeric_stats(row, "away_pitching", away_pitching)
        add_rate_features(row, "home")
        add_rate_features(row, "away")

        row["home_elo"] = home.elo
        row["away_elo"] = away.elo
        row["diff_elo"] = home.elo - away.elo
        row["home_rest_days"] = home.rest_days(game.game_date)
        row["away_rest_days"] = away.rest_days(game.game_date)
        row["diff_rest_days"] = row["home_rest_days"] - row["away_rest_days"]
        row["home_win_pct_real"] = home.win_pct()
        row["away_win_pct_real"] = away.win_pct()
        row["diff_win_pct_real"] = row["home_win_pct_real"] - row["away_win_pct_real"]
        row["home_run_diff_per_game_real"] = home.run_differential()
        row["away_run_diff_per_game_real"] = away.run_differential()
        row["diff_run_diff_per_game_real"] = row["home_run_diff_per_game_real"] - row["away_run_diff_per_game_real"]

        home_starter_era = fetch_pitcher_season_era(game.home_pitcher_id, game.game_date.year) if game.home_pitcher_id else 4.5
        away_starter_era = fetch_pitcher_season_era(game.away_pitcher_id, game.game_date.year) if game.away_pitcher_id else 4.5
        row["home_starter_era_real"] = home_starter_era
        row["away_starter_era_real"] = away_starter_era
        row["diff_starter_era_real"] = home_starter_era - away_starter_era

        away_abbr = self.team_abbr.get(game.away_team_id, "")
        home_abbr = self.team_abbr.get(game.home_team_id, "")
        market = self.odds.for_game(game.game_date.isoformat(), away_abbr, home_abbr)
        row["market_home_implied_probability"] = market.home_implied_probability
        row["market_away_implied_probability"] = market.away_implied_probability
        row["market_diff_implied_probability"] = market.home_implied_probability - market.away_implied_probability
        row["closing_line_home"] = float(market.home_moneyline)
        row["closing_line_away"] = float(market.away_moneyline)
        row["market_total"] = market.market_total
        row["market_source_count"] = float(market.source_count)

        park = park_for_team(game.home_team_id)
        row["park_factor_runs"] = park.park_factor_runs
        row["park_factor_hr"] = park.park_factor_hr
        row["park_altitude_ft"] = park.altitude_ft
        row["park_left_field_ft"] = park.left_field_ft
        row["park_center_field_ft"] = park.center_field_ft
        row["park_right_field_ft"] = park.right_field_ft

        game_dt = datetime.fromisoformat(game.game_datetime_iso.replace("Z", "+00:00"))
        row["game_hour_utc"] = float(game_dt.hour)
        row["is_day_game"] = 1.0 if game_dt.hour < 22 else 0.0
        row["month"] = float(game_dt.month)

        if self.include_weather:
            weather = fetch_historical_weather(game.home_team_id, game.game_datetime_iso)
            row["weather_temperature_f"] = weather.temperature_f
            row["weather_wind_speed_mph"] = weather.wind_speed_mph
            row["weather_wind_direction_degrees"] = weather.wind_direction_degrees
            row["weather_humidity_pct"] = weather.humidity_pct
            row["weather_precipitation_probability"] = weather.precipitation_probability
            row["weather_pressure_hpa"] = weather.pressure_hpa
            row["weather_is_dome"] = 1.0 if weather.is_dome else 0.0

        add_differences(row)
        return row
