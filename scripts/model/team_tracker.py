"""Rolling team state used to build pre-game features."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from elo import DEFAULT_ELO, update_elo, win_probability


@dataclass
class HeadToHeadGame:
    game_date: date
    home_id: int
    away_id: int
    home_score: int
    away_score: int

    @property
    def home_won(self) -> bool:
        return self.home_score > self.away_score


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
        self.head_to_head: list[HeadToHeadGame] = []

    def team(self, team_id: int) -> TeamTracker:
        if team_id not in self.teams:
            self.teams[team_id] = TeamTracker(team_id=team_id)
        return self.teams[team_id]

    def recent_head_to_head(
        self,
        home_id: int,
        away_id: int,
        before: date,
        *,
        window_days: int = 21,
        max_games: int = 5,
    ) -> list[HeadToHeadGame]:
        cutoff = before.toordinal() - window_days
        pair = {home_id, away_id}
        matches = [
            game
            for game in self.head_to_head
            if game.game_date.toordinal() >= cutoff
            and game.game_date < before
            and {game.home_id, game.away_id} == pair
        ]
        return matches[-max_games:]

    def head_to_head_features(self, home_id: int, away_id: int, game_date: date) -> list[float]:
        """Recent same-opponent series signal (e.g. SF owning ATL in a 3-game set)."""
        recent = self.recent_head_to_head(home_id, away_id, game_date)
        if not recent:
            return [0.0, 0.0, 0.0, 0.0, 0.0, 1.0]

        home_wins = 0
        away_wins = 0
        home_runs = 0
        away_runs = 0
        for game in recent:
            if game.home_id == home_id:
                home_runs += game.home_score
                away_runs += game.away_score
                home_wins += int(game.home_won)
                away_wins += int(not game.home_won)
            else:
                home_runs += game.away_score
                away_runs += game.home_score
                home_wins += int(not game.home_won)
                away_wins += int(game.home_won)

        games = len(recent)
        home_win_pct = home_wins / games
        run_diff = (home_runs - away_runs) / games
        last = recent[-1]
        home_won_last = (last.home_won if last.home_id == home_id else not last.home_won)
        home_lost_last_two = int(
            games >= 2
            and not (recent[-1].home_won if recent[-1].home_id == home_id else not recent[-1].home_won)
            and not (recent[-2].home_won if recent[-2].home_id == home_id else not recent[-2].home_won)
        )
        days_since = float((game_date - recent[-1].game_date).days)
        return [
            max(0.0, min(1.0, home_win_pct)),
            max(0.0, min(1.0, games / 5.0)),
            max(-5.0, min(5.0, run_diff)),
            max(0.0, min(1.0, away_wins / games)),
            1.0 if home_lost_last_two else 0.0,
            max(0.0, min(14.0, days_since)) / 14.0,
        ]

    def team_won_in_h2h(self, team_id: int, game: HeadToHeadGame) -> bool:
        if game.home_id == team_id:
            return game.home_won
        if game.away_id == team_id:
            return not game.home_won
        raise ValueError(f"Team {team_id} not in head-to-head game")

    def pick_lost_last_two_in_series(self, pick_id: int, opponent_id: int, before: date) -> bool:
        recent = self.recent_head_to_head(pick_id, opponent_id, before, max_games=5)
        if len(recent) < 2:
            return False
        return not self.team_won_in_h2h(pick_id, recent[-1]) and not self.team_won_in_h2h(pick_id, recent[-2])

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
        self.head_to_head.append(
            HeadToHeadGame(
                game_date=game_date,
                home_id=home_id,
                away_id=away_id,
                home_score=home_score,
                away_score=away_score,
            )
        )
