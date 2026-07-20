"""Build per-game Monte Carlo inputs and publish calibrated win probabilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from bullpen_provider import bullpen_stats_as_of
from game_sim import (
    DEFAULT_N_SIMS,
    DEFAULT_STARTER_TBF,
    SimResult,
    TeamSide,
    make_team_side,
    simulate_game,
)
from hitter_stats_provider import hitter_stats_as_of
from lineup_provider import confirmed_lineup_by_team, projected_lineup
from mlb_api import GameRecord
from park_factors import park_for_team
from pitcher_stats_provider import pitcher_stats_as_of

REPO_ROOT = Path(__file__).resolve().parents[2]
PARAMS_PATH = REPO_ROOT / "data" / "model" / "game_sim_params.json"


@dataclass(frozen=True)
class GameSimPublish:
    home_win_prob: float
    away_win_prob: float
    raw_home_win_prob: float
    raw_away_win_prob: float
    mean_home_runs: float
    mean_away_runs: float
    n_sims: int
    lineup_source: str  # confirmed | projected | mixed
    confidence: str
    ok: bool
    note: str = ""


def load_sim_params() -> dict:
    if not PARAMS_PATH.exists():
        return {
            "calibration": "identity",
            "x": [0.0, 0.5, 1.0],
            "y": [0.0, 0.5, 1.0],
            "n_sims_default": DEFAULT_N_SIMS,
        }
    try:
        return json.loads(PARAMS_PATH.read_text())
    except json.JSONDecodeError:
        return {"calibration": "identity", "x": [0.0, 0.5, 1.0], "y": [0.0, 0.5, 1.0]}


def calibrate_home_prob(raw_home: float, params: dict | None = None) -> float:
    """Piecewise-linear isotonic map from raw sim P(home) → calibrated."""
    params = params or load_sim_params()
    xs = params.get("x") or [0.0, 0.5, 1.0]
    ys = params.get("y") or [0.0, 0.5, 1.0]
    if len(xs) < 2 or len(xs) != len(ys):
        return max(0.01, min(0.99, float(raw_home)))
    x = max(0.0, min(1.0, float(raw_home)))
    if x <= xs[0]:
        return float(ys[0])
    if x >= xs[-1]:
        return float(ys[-1])
    for i in range(1, len(xs)):
        if x <= xs[i]:
            x0, x1 = xs[i - 1], xs[i]
            y0, y1 = ys[i - 1], ys[i]
            if x1 <= x0:
                return float(y1)
            t = (x - x0) / (x1 - x0)
            return float(y0 + t * (y1 - y0))
    return float(ys[-1])


def _lineup_ids(game: GameRecord, team_id: int) -> tuple[list[int], str]:
    confirmed = confirmed_lineup_by_team(game.game_pk)
    ids = confirmed.get(team_id) or []
    if len(ids) >= 9:
        return ids[:9], "confirmed"
    projected = projected_lineup(team_id, game.game_date)
    if len(ids) > 0:
        # Partial confirmed — fill remaining slots from projection.
        fill = [p for p in projected if p not in ids]
        merged = (ids + fill)[:9]
        return merged, "mixed"
    return projected[:9], "projected"


def _starter_tbf(starter_stats: dict[str, float]) -> int:
    ip = float(starter_stats.get("innings_pitched", 0.0) or 0.0)
    gs = float(starter_stats.get("games_started", 0.0) or 0.0)
    if gs >= 3 and ip > 0:
        ip_per_gs = ip / gs
        # ~4.15 PA per inning
        return int(max(18, min(32, round(ip_per_gs * 4.15))))
    return DEFAULT_STARTER_TBF


def build_sides(game: GameRecord) -> tuple[TeamSide, TeamSide, str] | None:
    """Return (home TeamSide, away TeamSide, lineup_source) or None on failure."""
    park = park_for_team(game.home_team_id)
    park_hr = float(getattr(park, "park_factor_hr", 1.0) or 1.0)

    home_ids, home_src = _lineup_ids(game, game.home_team_id)
    away_ids, away_src = _lineup_ids(game, game.away_team_id)
    if len(home_ids) < 9 or len(away_ids) < 9:
        return None

    home_bat = [hitter_stats_as_of(pid, game.game_date) for pid in home_ids]
    away_bat = [hitter_stats_as_of(pid, game.game_date) for pid in away_ids]

    home_starter = pitcher_stats_as_of(game.home_pitcher_id, game.game_date)
    away_starter = pitcher_stats_as_of(game.away_pitcher_id, game.game_date)

    try:
        home_pen = bullpen_stats_as_of(game.home_team_id, game.game_date)
        away_pen = bullpen_stats_as_of(game.away_team_id, game.game_date)
        home_era, home_whip = home_pen.era, home_pen.whip
        away_era, away_whip = away_pen.era, away_pen.whip
    except Exception:
        home_era, home_whip = 4.10, 1.32
        away_era, away_whip = 4.10, 1.32

    home = make_team_side(
        home_bat,
        home_starter,
        home_era,
        home_whip,
        park_hr=park_hr,
        starter_tbf=_starter_tbf(home_starter),
    )
    away = make_team_side(
        away_bat,
        away_starter,
        away_era,
        away_whip,
        park_hr=park_hr,
        starter_tbf=_starter_tbf(away_starter),
    )

    if home_src == away_src:
        src = home_src
    elif "confirmed" in (home_src, away_src):
        src = "mixed"
    else:
        src = "projected"
    return home, away, src


def confidence_from_sim(
    pick_prob: float,
    *,
    starter_certain: bool,
    lineup_source: str,
) -> str:
    if not starter_certain:
        if pick_prob >= 0.60:
            return "Medium"
        if pick_prob >= 0.54:
            return "Low"
        return "Low"
    if lineup_source == "projected" and pick_prob < 0.58:
        # Unconfirmed lineups → don't claim Elite.
        if pick_prob >= 0.56:
            return "High"
        if pick_prob >= 0.53:
            return "Medium"
        return "Low"
    if pick_prob >= 0.62:
        return "Elite"
    if pick_prob >= 0.57:
        return "High"
    if pick_prob >= 0.53:
        return "Medium"
    return "Low"


def simulate_game_record(
    game: GameRecord,
    *,
    n_sims: int | None = None,
    starter_certain: bool = True,
    params: dict | None = None,
) -> GameSimPublish:
    params = params or load_sim_params()
    n = int(n_sims or params.get("n_sims_default") or DEFAULT_N_SIMS)
    built = build_sides(game)
    if built is None:
        return GameSimPublish(
            home_win_prob=0.5,
            away_win_prob=0.5,
            raw_home_win_prob=0.5,
            raw_away_win_prob=0.5,
            mean_home_runs=0.0,
            mean_away_runs=0.0,
            n_sims=0,
            lineup_source="none",
            confidence="Low",
            ok=False,
            note="Could not build lineups for Monte Carlo",
        )

    home, away, lineup_source = built
    raw: SimResult = simulate_game(
        home,
        away,
        n_sims=n,
        seed=int(game.game_pk),
    )
    cal_home = calibrate_home_prob(raw.home_win_prob, params)
    cal_home = max(0.02, min(0.98, cal_home))
    cal_away = 1.0 - cal_home
    pick = max(cal_home, cal_away)
    conf = confidence_from_sim(
        pick, starter_certain=starter_certain, lineup_source=lineup_source
    )
    return GameSimPublish(
        home_win_prob=cal_home,
        away_win_prob=cal_away,
        raw_home_win_prob=raw.home_win_prob,
        raw_away_win_prob=raw.away_win_prob,
        mean_home_runs=raw.mean_home_runs,
        mean_away_runs=raw.mean_away_runs,
        n_sims=raw.n_sims,
        lineup_source=lineup_source,
        confidence=conf,
        ok=True,
        note=f"PA Monte Carlo ({raw.n_sims} sims, lineup={lineup_source})",
    )
