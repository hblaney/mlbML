"""Focused combo tests using real historical odds/weather/park/MLB data."""

from __future__ import annotations

import json
import argparse
from datetime import date
from pathlib import Path

from feature_lab import build_dataset, evaluate_columns
from mlb_api import load_or_fetch_games

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "real-combo-test.json"

COMBOS = {
    "market_only": [
        "market_home_implied_probability",
        "market_away_implied_probability",
        "closing_line_home",
        "closing_line_away",
        "market_total",
        "market_source_count",
    ],
    "weather_park": [
        "park_factor_runs",
        "park_factor_hr",
        "park_altitude_ft",
        "park_left_field_ft",
        "park_center_field_ft",
        "park_right_field_ft",
        "weather_temperature_f",
        "weather_wind_speed_mph",
        "weather_wind_direction_degrees",
        "weather_humidity_pct",
        "weather_precipitation_probability",
        "weather_pressure_hpa",
        "weather_is_dome",
    ],
    "starter_realish": [
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
    ],
    "team_form_real": [
        "home_team_elo",
        "away_team_elo",
        "elo_difference",
        "home_field_advantage",
        "home_rest_days",
        "away_rest_days",
        "home_win_pct",
        "away_win_pct",
        "home_run_differential",
        "away_run_differential",
    ],
    "real_team_stats": [
        "home_batting_avg_asof",
        "away_batting_avg_asof",
        "home_obp_asof",
        "away_obp_asof",
        "home_slg_asof",
        "away_slg_asof",
        "home_ops_asof",
        "away_ops_asof",
        "home_runs_per_game_asof",
        "away_runs_per_game_asof",
        "home_hr_per_game_asof",
        "away_hr_per_game_asof",
        "home_k_rate_asof",
        "away_k_rate_asof",
        "home_bb_rate_asof",
        "away_bb_rate_asof",
        "home_pitching_era_asof",
        "away_pitching_era_asof",
        "home_pitching_whip_asof",
        "away_pitching_whip_asof",
        "home_ops_allowed_asof",
        "away_ops_allowed_asof",
        "home_pitching_k9_asof",
        "away_pitching_k9_asof",
        "home_pitching_bb9_asof",
        "away_pitching_bb9_asof",
        "matchup_ops_vs_pitching_ops_allowed",
        "matchup_slg_vs_pitching_slg_allowed",
        "matchup_obp_vs_pitching_obp_allowed",
        "matchup_run_creation_gap",
        "game_hour_utc",
        "is_day_game",
    ],
}


def indices_for(feature_names: list[str], names: list[str]) -> list[int]:
    mapping = {name: index for index, name in enumerate(feature_names)}
    return [mapping[name] for name in names if name in mapping]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-04-01")
    parser.add_argument("--end", default="2025-08-16")
    args = parser.parse_args()

    games = load_or_fetch_games(date.fromisoformat(args.start), date.fromisoformat(args.end))
    dataset = build_dataset(games)
    results = []

    for combo_name, names in COMBOS.items():
        indices = indices_for(dataset.feature_names, names)
        metrics = evaluate_columns(dataset, indices, model_type="gbm")
        results.append({"combo": combo_name, "features": len(indices), "feature_names": names, **metrics})
        print(f"{combo_name} accuracy={metrics['accuracy']:.4f} auc={metrics['auc']:.4f} brier={metrics['brier']:.4f}")

    combined_sets = {
        "market_plus_team_form": COMBOS["market_only"] + COMBOS["team_form_real"],
        "market_plus_real_team_stats": COMBOS["market_only"] + COMBOS["real_team_stats"],
        "real_team_stats_plus_starter": COMBOS["real_team_stats"] + COMBOS["starter_realish"],
        "market_plus_starter": COMBOS["market_only"] + COMBOS["starter_realish"],
        "market_weather_park": COMBOS["market_only"] + COMBOS["weather_park"],
        "market_team_stats_starter_weather_park": (
            COMBOS["market_only"]
            + COMBOS["team_form_real"]
            + COMBOS["real_team_stats"]
            + COMBOS["starter_realish"]
            + COMBOS["weather_park"]
        ),
    }

    for combo_name, names in combined_sets.items():
        indices = indices_for(dataset.feature_names, names)
        metrics = evaluate_columns(dataset, indices, model_type="gbm")
        results.append({"combo": combo_name, "features": len(indices), "feature_names": names, **metrics})
        print(f"{combo_name} accuracy={metrics['accuracy']:.4f} auc={metrics['auc']:.4f} brier={metrics['brier']:.4f}")

    results.sort(key=lambda item: (item["accuracy"], item["auc"]), reverse=True)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "generated_at": date.today().isoformat(),
                "games": int(dataset.y.shape[0]),
                "best": results[0] if results else None,
                "results": results,
            },
            indent=2,
        )
    )

    if results:
        print(f"best_combo={results[0]['combo']}")
        print(f"best_accuracy={results[0]['accuracy']:.4f}")


if __name__ == "__main__":
    main()
