"""Lightweight pre-game predictor shared by the auto board and history.

This is intentionally fast enough to run on page load, but it is stronger than
raw Elo: it blends Elo, season record, recent form, run differential, rest, and
probable starter ERA when available.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from mlb_api import GameRecord, fetch_pitcher_season_era
from team_tracker import LeagueState, TeamTracker


@dataclass(frozen=True)
class FastPrediction:
    home_probability: float
    away_probability: float
    predicted_home: bool
    pick_probability: float
    confidence: str
    notes: list[str]


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _logit(probability: float) -> float:
    p = _clip(probability, 0.02, 0.98)
    return math.log(p / (1.0 - p))


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _starter_era(game: GameRecord, pitcher_id: int | None) -> float:
    if not pitcher_id:
        return 4.35
    try:
        return fetch_pitcher_season_era(pitcher_id, game.game_date.year)
    except Exception:
        return 4.35


def _confidence(probability: float) -> str:
    if probability >= 0.60:
        return "High"
    if probability >= 0.56:
        return "Medium"
    return "Low"


def _team_signals(home: TeamTracker, away: TeamTracker, game: GameRecord) -> dict[str, float]:
    return {
        "season_win": home.win_pct() - away.win_pct(),
        "recent_win": home.win_pct(10) - away.win_pct(10),
        "season_run_diff": home.run_differential() - away.run_differential(),
        "recent_run_diff": home.run_differential(10) - away.run_differential(10),
        "rest": _clip(home.rest_days(game.game_date) - away.rest_days(game.game_date), -3.0, 3.0),
        "home_scoring": home.avg_runs_scored(10) - away.avg_runs_allowed(10),
        "away_scoring": away.avg_runs_scored(10) - home.avg_runs_allowed(10),
    }


def predict_fast(game: GameRecord, league: LeagueState) -> FastPrediction:
    home = league.team(game.home_team_id)
    away = league.team(game.away_team_id)
    elo_probability = league.predict_home_win_probability(game.home_team_id, game.away_team_id)
    signals = _team_signals(home, away, game)
    home_starter_era = _starter_era(game, game.home_pitcher_id)
    away_starter_era = _starter_era(game, game.away_pitcher_id)
    starter_signal = _clip((away_starter_era - home_starter_era) / 2.0, -1.25, 1.25)
    scoring_matchup = _clip((signals["home_scoring"] - signals["away_scoring"]) / 4.0, -1.0, 1.0)

    score = (
        0.78 * _logit(elo_probability)
        + 0.82 * signals["season_win"]
        + 0.42 * signals["recent_win"]
        + 0.10 * _clip(signals["season_run_diff"], -3.0, 3.0)
        + 0.08 * _clip(signals["recent_run_diff"], -4.0, 4.0)
        + 0.08 * signals["rest"]
        + 0.16 * starter_signal
        + 0.12 * scoring_matchup
    )

    # Light calibration shrinkage. This keeps the auto model from pretending a
    # 65/35 game is a sure thing when it has no betting market attached.
    home_probability = 0.5 + (_sigmoid(score) - 0.5) * 0.70
    away_probability = 1.0 - home_probability
    predicted_home = home_probability >= away_probability
    pick_probability = max(home_probability, away_probability)

    notes = [
        "Blends Elo, season form, recent form, run differential, rest, and starter context",
        f"Starter ERA input: away {away_starter_era:.2f}, home {home_starter_era:.2f}",
        "Confidence is based on predicted winner probability, not whether the team is home or away",
    ]

    return FastPrediction(
        home_probability=home_probability,
        away_probability=away_probability,
        predicted_home=predicted_home,
        pick_probability=pick_probability,
        confidence=_confidence(pick_probability),
        notes=notes,
    )
