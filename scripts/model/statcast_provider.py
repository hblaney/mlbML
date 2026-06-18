"""Real Statcast data provider with team rolling metrics."""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "statcast"

STATCAST_WINDOWS = [7, 14, 30, 45]
STATCAST_METRICS = [
    "barrel_rate",
    "hard_hit_rate",
    "avg_exit_velocity",
    "avg_launch_angle",
    "xwoba",
    "whiff_rate",
]
# Deltas the shallow v2.1 GBM can split on (raw 48 team columns are mostly ignored at max_depth=1).
STATCAST_MATCHUP_WINDOWS = [14, 30]
STATCAST_MATCHUP_METRICS = ["xwoba", "barrel_rate", "hard_hit_rate", "whiff_rate"]

_TEAM_ALIASES = {
    "AZ": "ARI",
    "ARI": "ARI",
    "ATH": "OAK",
    "OAK": "OAK",
    "CWS": "CHW",
    "CHW": "CHW",
    "TB": "TB",
    "TBR": "TB",
    "SF": "SF",
    "SFG": "SF",
    "KC": "KC",
    "KCR": "KC",
    "SD": "SD",
    "SDP": "SD",
    "WSH": "WSH",
    "WAS": "WSH",
}


def normalize_team_abbr(team_abbr: str) -> str:
    value = str(team_abbr or "").upper()
    return _TEAM_ALIASES.get(value, value)


def fetch_statcast_games(start: date, end: date) -> pd.DataFrame:
    from pybaseball import statcast

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"statcast_{start.isoformat()}_{end.isoformat()}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)

    frame = statcast(start_dt=start.isoformat(), end_dt=end.isoformat())
    if frame is None or frame.empty:
        frame = pd.DataFrame()
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


def _batting_rows(frame: pd.DataFrame, team_abbr: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    team = normalize_team_abbr(team_abbr)
    if "home_team" not in frame.columns or "inning_topbot" not in frame.columns:
        return pd.DataFrame()
    home_rows = frame[(frame["home_team"] == team) & (frame["inning_topbot"] == "Bot")]
    away_rows = frame[(frame["away_team"] == team) & (frame["inning_topbot"] == "Top")]
    return pd.concat([home_rows, away_rows], ignore_index=True)


def _metric_from_rows(rows: pd.DataFrame, metric: str) -> float:
    if rows.empty:
        return 0.0
    batted = rows[rows["type"] == "X"] if "type" in rows.columns else rows
    if metric == "avg_exit_velocity":
        if "launch_speed" not in batted.columns:
            return 0.0
        values = batted["launch_speed"].dropna()
        return float(values.mean()) if len(values) else 0.0
    if metric == "avg_launch_angle":
        if "launch_angle" not in batted.columns:
            return 0.0
        values = batted["launch_angle"].dropna()
        return float(values.mean()) if len(values) else 0.0
    if metric == "hard_hit_rate":
        if "launch_speed" not in batted.columns:
            return 0.0
        values = batted["launch_speed"].dropna()
        return float((values >= 95).mean()) if len(values) else 0.0
    if metric == "barrel_rate":
        if "launch_speed_angle" in batted.columns:
            values = batted["launch_speed_angle"].dropna()
            return float((values == 6).mean()) if len(values) else 0.0
        if "launch_speed" in batted.columns and "launch_angle" in batted.columns:
            speeds = batted["launch_speed"].fillna(0)
            angles = batted["launch_angle"].fillna(0)
            barrels = (speeds >= 98) & (angles.between(26, 30))
            return float(barrels.mean()) if len(batted) else 0.0
        return 0.0
    if metric == "xwoba":
        column = "estimated_woba_using_speedangle"
        if column not in batted.columns:
            return 0.0
        values = batted[column].dropna()
        return float(values.mean()) if len(values) else 0.0
    if metric == "whiff_rate":
        pitches = rows[rows["type"] == "P"] if "type" in rows.columns else rows
        if pitches.empty or "description" not in pitches.columns:
            return 0.0
        descriptions = pitches["description"].astype(str)
        swings = descriptions.str.contains("swinging_strike|foul|in play", case=False, regex=True)
        whiffs = descriptions.str.contains("swinging_strike", case=False, regex=True)
        swing_count = int(swings.sum())
        return float(whiffs.sum() / swing_count) if swing_count else 0.0
    return 0.0


class StatcastTeamCache:
    """Cache Statcast chunks and serve team rolling metrics through yesterday."""

    def __init__(self) -> None:
        self._chunks: dict[tuple[str, str], pd.DataFrame] = {}

    def preload_season(self, year: int) -> None:
        start = date(year, 3, 1)
        end = min(date(year, 11, 15), date.today())
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=13), end)
            self._ensure_chunk(cursor, chunk_end)
            cursor = chunk_end + timedelta(days=1)

    def _ensure_chunk(self, start: date, end: date) -> None:
        key = (start.isoformat(), end.isoformat())
        if key in self._chunks:
            return
        try:
            self._chunks[key] = fetch_statcast_games(start, end)
        except Exception:
            self._chunks[key] = pd.DataFrame()

    def _rows_for_team(self, team_abbr: str, start: date, end: date) -> pd.DataFrame:
        """Filter preloaded season chunks — avoids thousands of redundant Savant downloads."""
        frames: list[pd.DataFrame] = []
        for (chunk_start_iso, chunk_end_iso), chunk in self._chunks.items():
            if chunk.empty or "game_date" not in chunk.columns:
                continue
            chunk_start = date.fromisoformat(chunk_start_iso)
            chunk_end = date.fromisoformat(chunk_end_iso)
            if chunk_end < start or chunk_start > end:
                continue
            dated = chunk.copy()
            dated["game_date"] = pd.to_datetime(dated["game_date"]).dt.date
            window = dated[(dated["game_date"] >= start) & (dated["game_date"] <= end)]
            batting = _batting_rows(window, team_abbr)
            if not batting.empty:
                frames.append(batting)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def team_metrics(self, team_abbr: str, as_of: date, window: int) -> dict[str, float]:
        return self._team_metrics_cached(normalize_team_abbr(team_abbr), as_of.isoformat(), window)

    @lru_cache(maxsize=4096)
    def _team_metrics_cached(self, team_abbr: str, as_of_iso: str, window: int) -> dict[str, float]:
        as_of = date.fromisoformat(as_of_iso)
        end = as_of - timedelta(days=1)
        if end.year < 2015:
            return {metric: 0.0 for metric in STATCAST_METRICS}
        start = end - timedelta(days=max(window, 3))
        try:
            rows = self._rows_for_team(team_abbr, start, end)
        except Exception:
            rows = pd.DataFrame()
        return {metric: _metric_from_rows(rows, metric) for metric in STATCAST_METRICS}

    def feature_map(self, home_abbr: str, away_abbr: str, as_of: date) -> dict[str, float]:
        values: dict[str, float] = {}
        for side, abbr in (("home", home_abbr), ("away", away_abbr)):
            for window in STATCAST_WINDOWS:
                metrics = self.team_metrics(abbr, as_of, window)
                for metric in STATCAST_METRICS:
                    values[f"{side}_statcast_{metric}_last_{window}"] = float(metrics.get(metric, 0.0))
        for window in STATCAST_MATCHUP_WINDOWS:
            home_metrics = self.team_metrics(home_abbr, as_of, window)
            away_metrics = self.team_metrics(away_abbr, as_of, window)
            for metric in STATCAST_MATCHUP_METRICS:
                home_val = float(home_metrics.get(metric, 0.0))
                away_val = float(away_metrics.get(metric, 0.0))
                values[f"statcast_{metric}_delta_last_{window}"] = home_val - away_val
                if metric == "whiff_rate":
                    values[f"statcast_contact_edge_last_{window}"] = away_val - home_val
                else:
                    values[f"statcast_offense_edge_last_{window}"] = home_val - away_val
        return values


def statcast_feature_vector(cache: StatcastTeamCache, home_abbr: str, away_abbr: str, as_of: date) -> list[float]:
    from feature_registry import zero_statcast_feature_map

    values = cache.feature_map(home_abbr, away_abbr, as_of)
    template = zero_statcast_feature_map()
    return [float(values.get(key, 0.0)) for key in template]
