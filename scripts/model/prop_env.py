"""Game run/HR environment: park factors combined with live weather.

Turns the ballpark (run/HR park factors) and the forecast (temperature, wind
out/in) into two multipliers that scale hitter production:
  - run_mult: overall offense (hits, TB, RBI, runs)
  - hr_mult:  home-run specific (temperature + wind matter much more for HR)

Domes and missing forecasts return neutral (1.0) so the pipeline never breaks.
"""

from __future__ import annotations

from functools import lru_cache

from park_factors import park_for_team


@lru_cache(maxsize=512)
def env_multipliers(home_team_id: int | None, game_datetime_iso: str | None) -> tuple[float, float]:
    if home_team_id is None:
        return 1.0, 1.0

    park = park_for_team(home_team_id)
    run_mult = float(getattr(park, "park_factor_runs", 1.0) or 1.0)
    hr_mult = float(getattr(park, "park_factor_hr", 1.0) or 1.0)

    # Weather is best-effort; any failure leaves the park-only environment.
    try:
        from weather import fetch_weather
        wx = fetch_weather(home_team_id, game_datetime_iso) if game_datetime_iso else None
    except Exception:
        wx = None

    if wx is not None and not getattr(wx, "is_dome", False):
        temp = float(getattr(wx, "temperature_f", 72.0) or 72.0)
        speed = float(getattr(wx, "wind_speed_mph", 0.0) or 0.0)
        out = float(getattr(wx, "wind_out_to_center", 0.0) or 0.0)

        # Temperature: warm air carries the ball; ~0.6%/°F on HR, ~0.4% on runs.
        temp_hr = 1.0 + (temp - 70.0) * 0.006
        temp_run = 1.0 + (temp - 70.0) * 0.004
        hr_mult *= max(0.90, min(1.12, temp_hr))
        run_mult *= max(0.94, min(1.08, temp_run))

        # Wind past ~5 mph: blowing out helps, blowing in hurts (HR most).
        gust = max(0.0, min(speed - 5.0, 20.0))
        if gust > 0:
            if out >= 0.5:
                hr_mult *= 1.0 + gust * 0.010
                run_mult *= 1.0 + gust * 0.004
            else:
                hr_mult *= 1.0 - gust * 0.008
                run_mult *= 1.0 - gust * 0.003

    run_mult = max(0.85, min(1.25, run_mult))
    hr_mult = max(0.75, min(1.40, hr_mult))
    return round(run_mult, 4), round(hr_mult, 4)
