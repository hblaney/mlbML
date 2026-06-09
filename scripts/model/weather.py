"""Weather provider using Open-Meteo forecast and archive APIs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import urlopen

from context import WeatherSnapshot
from park_factors import park_location


def _nearest_hour_index(times: list[str], target_iso: str) -> int:
    target = datetime.fromisoformat(target_iso.replace("Z", "+00:00"))
    best_index = 0
    best_delta = None

    for index, item in enumerate(times):
        candidate = datetime.fromisoformat(item).replace(tzinfo=timezone.utc)
        delta = abs((candidate - target).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_index = index

    return best_index


def fetch_weather(team_id: int, game_datetime_iso: str) -> WeatherSnapshot:
    lat, lon, is_dome = park_location(team_id)
    if is_dome:
        return WeatherSnapshot(is_dome=True)

    params = urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "hourly": "temperature_2m,relative_humidity_2m,precipitation_probability,surface_pressure,wind_speed_10m,wind_direction_10m",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "UTC",
            "forecast_days": 7,
        }
    )
    url = f"https://api.open-meteo.com/v1/forecast?{params}"

    try:
        with urlopen(url, timeout=20) as response:
            payload = json.load(response)
        hourly = payload["hourly"]
        index = _nearest_hour_index(hourly["time"], game_datetime_iso)
        wind_direction = float(hourly["wind_direction_10m"][index])
        # Approximation: wind from 180-360 tends to aid balls hit to CF in many parks.
        wind_out = 1.0 if 180 <= wind_direction <= 360 else 0.0
        return WeatherSnapshot(
            temperature_f=float(hourly["temperature_2m"][index]),
            wind_speed_mph=float(hourly["wind_speed_10m"][index]),
            wind_direction_degrees=wind_direction,
            wind_out_to_center=wind_out,
            humidity_pct=float(hourly["relative_humidity_2m"][index]),
            precipitation_probability=float(hourly["precipitation_probability"][index]) / 100,
            pressure_hpa=float(hourly["surface_pressure"][index]),
            is_dome=False,
        )
    except Exception:
        return WeatherSnapshot()


def fetch_historical_weather(team_id: int, game_datetime_iso: str) -> WeatherSnapshot:
    lat, lon, is_dome = park_location(team_id)
    if is_dome:
        return WeatherSnapshot(is_dome=True)

    target = datetime.fromisoformat(game_datetime_iso.replace("Z", "+00:00"))
    game_day = target.date().isoformat()
    params = urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": game_day,
            "end_date": game_day,
            "hourly": "temperature_2m,relative_humidity_2m,precipitation,surface_pressure,wind_speed_10m,wind_direction_10m",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "UTC",
        }
    )
    url = f"https://archive-api.open-meteo.com/v1/archive?{params}"

    try:
        with urlopen(url, timeout=20) as response:
            payload = json.load(response)
        hourly = payload["hourly"]
        index = _nearest_hour_index(hourly["time"], game_datetime_iso)
        wind_direction = float(hourly["wind_direction_10m"][index])
        wind_out = 1.0 if 180 <= wind_direction <= 360 else 0.0
        return WeatherSnapshot(
            temperature_f=float(hourly["temperature_2m"][index]),
            wind_speed_mph=float(hourly["wind_speed_10m"][index]),
            wind_direction_degrees=wind_direction,
            wind_out_to_center=wind_out,
            humidity_pct=float(hourly["relative_humidity_2m"][index]),
            precipitation_probability=1.0 if float(hourly["precipitation"][index]) > 0 else 0.0,
            pressure_hpa=float(hourly["surface_pressure"][index]),
            is_dome=False,
        )
    except Exception:
        return WeatherSnapshot()
