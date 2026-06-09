"""Real Statcast data provider.

Requires `pybaseball`. These functions intentionally return raw sourced data or
empty results. The model should not silently replace missing Statcast data with
fake advanced metrics.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "statcast"


def fetch_statcast_games(start: date, end: date) -> pd.DataFrame:
    from pybaseball import statcast

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"statcast_{start.isoformat()}_{end.isoformat()}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)

    frame = statcast(start_dt=start.isoformat(), end_dt=end.isoformat())
    frame.to_parquet(cache_path, index=False)
    return frame


def summarize_statcast_window(frame: pd.DataFrame) -> dict[str, float]:
    if frame.empty:
        return {}

    summary: dict[str, float] = {}
    if "launch_speed" in frame:
        summary["avg_exit_velocity"] = float(frame["launch_speed"].dropna().mean())
    if "launch_angle" in frame:
        summary["avg_launch_angle"] = float(frame["launch_angle"].dropna().mean())
    if "events" in frame:
        balls_in_play = frame["events"].dropna()
        summary["home_run_rate"] = float((balls_in_play == "home_run").mean()) if len(balls_in_play) else 0.0
    if "release_speed" in frame:
        summary["avg_pitch_velocity"] = float(frame["release_speed"].dropna().mean())

    return {key: value for key, value in summary.items() if value == value}
