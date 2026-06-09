"""Rolling team state used to build pre-game features."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from elo import DEFAULT_ELO, update_elo, win_probability


@dataclass
class PlayedGame:
    game_date: date
    runs_scored: int
    runs_allowed: int
    won: bool


@dataclass
class TeamTracker:
    team_id: int
    elo: float = DEFAULT_ELO
    games: list[PlayedGame] = field(default_factory=list)

    def last_game_date(self) -> date | None:
        return self.games[-1].game_date if self.games else None

    def rest_days(self, game_date: date) -> float:
        last = self.last_game_date()
        if last is None:
            return 3.0
        return float(max((game_date - last).days, 0))

    def wins(self, window: int | None = None) -> int:
        sample = self.games[-window:] if window else self.games
        return sum(1 for game in sample if game.won)

    def losses(self, window: int | None = None) -> int:
        sample = self.games[-window:] if window else self.games
        return len(sample) - self.wins(window)

    def win_pct(self, window: int | None = None) -> float:
        sample = self.games[-window:] if window else self.games
        if not sample:
            return 0.5
        return self.wins(window) / len(sample)

    def avg_runs_scored(self, window: int) -> float:
        sample = self.games[-window:]
        if not sample:
            return 4.5
        return sum(game.runs_scored for game in sample) / len(sample)

    def avg_runs_allowed(self, window: int) -> float:
        sample = self.games[-window:]
        if not sample:
            return 4.5
        return sum(game.runs_allowed for game in sample) / len(sample)

    def run_differential(self, window: int | None = None) -> float:
        sample = self.games[-window:] if window else self.games
        if not sample:
            return 0.0
        return sum(game.runs_scored - game.runs_allowed for game in sample) / len(sample)

    def streak(self) -> int:
        if not self.games:
            return 0
        streak = 0
        current = self.games[-1].won
        for game in reversed(self.games):
            if game.won == current:
                streak += 1 if current else -1
            else:
                break
        return streak

    def record_game(self, game_date: date, runs_scored: int, runs_allowed: int) -> None:
        self.games.append(
            PlayedGame(
                game_date=game_date,
                runs_scored=runs_scored,
                runs_allowed=runs_allowed,
                won=runs_scored > runs_allowed,
            )
        )


class LeagueState:
    def __init__(self) -> None:
        self.teams: dict[int, TeamTracker] = {}

    def team(self, team_id: int) -> TeamTracker:
        if team_id not in self.teams:
            self.teams[team_id] = TeamTracker(team_id=team_id)
        return self.teams[team_id]

    def predict_home_win_probability(self, home_id: int, away_id: int) -> float:
        home = self.team(home_id)
        away = self.team(away_id)
        return win_probability(home.elo, away.elo)

    def apply_result(
        self,
        game_date: date,
        home_id: int,
        away_id: int,
        home_score: int,
        away_score: int,
    ) -> None:
        home = self.team(home_id)
        away = self.team(away_id)
        home_won = home_score > away_score
        home.elo, away.elo = update_elo(home.elo, away.elo, home_won)
        home.record_game(game_date, home_score, away_score)
        away.record_game(game_date, away_score, home_score)
