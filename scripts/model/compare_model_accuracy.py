"""Compare v2.1 (187-feature) vs v3 (full registry) walk-forward accuracy."""

from __future__ import annotations

from datetime import date

from backtest_parlays import build_single_candidates, odds_backtest_range
from exhaustive_strategy_search import action_to_bet
from historical_odds import HistoricalOddsStore
from mlb_api import GameRecord, load_or_fetch_games, load_team_abbreviations
from sklearn.pipeline import Pipeline
from strategy_next_tests import day_actions_for_test, enrich_moneyline
from team_tracker import LeagueState

import trained_edge_model as v21
import full_registry_model as v3
from daily_auto_model import no_vig_market_probabilities

LIVE_STRATEGY = "corr_nl_reject_both"


def _result_row(
    game: GameRecord,
    *,
    home_abbr: str,
    away_abbr: str,
    prediction,
    home_probability: float,
    pick_probability: float,
    predicted_home: bool,
    odds_available: bool,
    model_version: str,
) -> dict:
    predicted_winner = home_abbr if predicted_home else away_abbr
    actual_winner = home_abbr if game.home_won else away_abbr
    return {
        "gamePk": game.game_pk,
        "date": game.game_date.isoformat(),
        "startsAt": game.game_datetime_iso,
        "home": home_abbr,
        "away": away_abbr,
        "internalHomeProbability": round(prediction.home_probability, 4),
        "probability": round(home_probability, 4),
        "pickProbability": round(pick_probability, 4),
        "confidence": v21.confidence_for(
            pick_probability,
            market_backed=odds_available,
            internal_pick_probability=prediction.pick_probability,
            internal_agrees=prediction.predicted_home == predicted_home,
        ),
        "marketBacked": odds_available,
        "predicted": predicted_winner,
        "actual": actual_winner,
        "correct": int(predicted_winner == actual_winner),
        "modelVersion": model_version,
    }


def walk_forward_v21(
    games: list[GameRecord],
    team_abbr: dict[int, str],
    prior_games: list[GameRecord] | None = None,
) -> list[dict]:
    league = LeagueState()
    examples: list[v21.TrainingExample] = []
    weights: list[float] = []
    model: Pipeline | None = None
    last_fit_index = -v21.REFIT_EVERY
    rows: list[dict] = []
    odds = HistoricalOddsStore()

    def ingest(game: GameRecord, weight: float) -> None:
        examples.append(
            v21.TrainingExample(features=v21.feature_row(game, league), label=1 if game.home_won else 0)
        )
        weights.append(weight)
        league.apply_result(
            game.game_date,
            game.home_team_id,
            game.away_team_id,
            game.home_score,
            game.away_score,
        )

    for game in prior_games or []:
        ingest(game, v21.PRIOR_SEASON_SAMPLE_WEIGHT)

    for index, game in enumerate(games):
        if len(examples) >= v21.WARMUP_GAMES and (model is None or index - last_fit_index >= v21.REFIT_EVERY):
            model = v21.fit_model(examples, weights)
            last_fit_index = index

        if len(examples) >= v21.WARMUP_GAMES and model is not None:
            prediction = v21.predict_with_model(game, league, model)
            home_abbr = team_abbr.get(game.home_team_id, str(game.home_team_id))
            away_abbr = team_abbr.get(game.away_team_id, str(game.away_team_id))
            market = odds.for_game(game.game_date.isoformat(), away_abbr, home_abbr)
            odds_available = market.source_count > 0 and market.home_moneyline != 0 and market.away_moneyline != 0
            home_probability = prediction.home_probability
            if odds_available:
                market_probs = no_vig_market_probabilities(market.home_moneyline, market.away_moneyline)
                if market_probs is not None:
                    market_home, _ = market_probs
                    home_probability = v21.blend_with_market(prediction.home_probability, market_home)
            home_probability = v21.sharpen_public_probability(home_probability)
            pick_probability = max(home_probability, 1.0 - home_probability)
            predicted_home = home_probability >= 0.5
            rows.append(
                _result_row(
                    game,
                    home_abbr=home_abbr,
                    away_abbr=away_abbr,
                    prediction=prediction,
                    home_probability=home_probability,
                    pick_probability=pick_probability,
                    predicted_home=predicted_home,
                    odds_available=odds_available,
                    model_version="daily-auto-v2.1",
                )
            )

        ingest(game, v21.CURRENT_SEASON_SAMPLE_WEIGHT)

    return rows


def walk_forward_v3(
    games: list[GameRecord],
    team_abbr: dict[int, str],
    prior_games: list[GameRecord] | None = None,
    *,
    include_statcast: bool = False,
) -> list[dict]:
    league = LeagueState()
    examples: list[v3.TrainingExample] = []
    weights: list[float] = []
    model: Pipeline | None = None
    last_fit_index = -v3.REFIT_EVERY
    rows: list[dict] = []
    odds = HistoricalOddsStore()
    builder = v3.FullRegistryFeatureBuilder(team_abbr)

    def ingest(game: GameRecord, weight: float) -> None:
        examples.append(
            v3.TrainingExample(
                features=builder.feature_row(game, league, include_statcast=include_statcast),
                label=1 if game.home_won else 0,
            )
        )
        weights.append(weight)
        league.apply_result(
            game.game_date,
            game.home_team_id,
            game.away_team_id,
            game.home_score,
            game.away_score,
        )

    for game in prior_games or []:
        ingest(game, v3.PRIOR_SEASON_SAMPLE_WEIGHT)

    for index, game in enumerate(games):
        if len(examples) >= v3.WARMUP_GAMES and (model is None or index - last_fit_index >= v3.REFIT_EVERY):
            model = v3.fit_model(examples, weights)
            last_fit_index = index

        if len(examples) >= v3.WARMUP_GAMES and model is not None:
            prediction = v3.predict_with_model(
                game,
                league,
                model,
                builder,
                include_statcast=include_statcast,
            )
            home_abbr = team_abbr.get(game.home_team_id, str(game.home_team_id))
            away_abbr = team_abbr.get(game.away_team_id, str(game.away_team_id))
            market = odds.for_game(game.game_date.isoformat(), away_abbr, home_abbr)
            odds_available = market.source_count > 0 and market.home_moneyline != 0 and market.away_moneyline != 0
            home_probability = prediction.home_probability
            if odds_available:
                market_probs = no_vig_market_probabilities(market.home_moneyline, market.away_moneyline)
                if market_probs is not None:
                    market_home, _ = market_probs
                    home_probability = v21.blend_with_market(prediction.home_probability, market_home)
            home_probability = v21.sharpen_public_probability(home_probability)
            pick_probability = max(home_probability, 1.0 - home_probability)
            predicted_home = home_probability >= 0.5
            rows.append(
                _result_row(
                    game,
                    home_abbr=home_abbr,
                    away_abbr=away_abbr,
                    prediction=prediction,
                    home_probability=home_probability,
                    pick_probability=pick_probability,
                    predicted_home=predicted_home,
                    odds_available=odds_available,
                    model_version="daily-auto-v3.0-full-registry",
                )
            )

        ingest(game, v3.CURRENT_SEASON_SAMPLE_WEIGHT)

    return rows


def summarize_games(rows: list[dict]) -> dict:
    correct = sum(int(row["correct"]) for row in rows)
    total = len(rows)
    return {
        "games": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "record": f"{correct}-{total - correct}",
    }


def summarize_tickets(rows: list[dict], store: HistoricalOddsStore) -> dict:
  moneyline_by_day = enrich_moneyline(build_single_candidates(rows, store), rows)
  wins = losses = 0
  for day in sorted(moneyline_by_day):
      actions = day_actions_for_test(moneyline_by_day[day], LIVE_STRATEGY)
      if not actions:
          continue
      bet = action_to_bet(actions[0], day)
      if bet.get("won"):
          wins += 1
      else:
          losses += 1
  total = wins + losses
  return {
      "bet_days": total,
      "wins": wins,
      "losses": losses,
      "hit_rate": round(wins / total, 4) if total else 0.0,
      "record": f"{wins}-{losses}",
  }


def main() -> None:
    store = HistoricalOddsStore()
    start, end, _ = odds_backtest_range(store)
    team_abbr = load_team_abbreviations()
    prior = load_or_fetch_games(date(start.year - 1, 3, 20), date(start.year - 1, 10, 5))
    games = load_or_fetch_games(start, end)

    print(f"Comparing walk-forward {start} → {end}\n")

    rows_v21 = walk_forward_v21(games, team_abbr, prior_games=prior)
    game_v21 = summarize_games(rows_v21)
    ticket_v21 = summarize_tickets(rows_v21, store)
    print("v2.1 (187 features, shallow GBM):")
    print(f"  game picks: {game_v21['record']} = {game_v21['accuracy']*100:.2f}%")
    print(f"  best tickets: {ticket_v21['record']} = {ticket_v21['hit_rate']*100:.2f}%")

    print("\nRunning v3 walk-forward (may take several minutes)...")
    rows_v3 = walk_forward_v3(games, team_abbr, prior_games=prior, include_statcast=False)
    game_v3 = summarize_games(rows_v3)
    ticket_v3 = summarize_tickets(rows_v3, store)
    print("\nv3.0 (1002 features, HistGBM + robust blend, no Statcast at predict):")
    print(f"  game picks: {game_v3['record']} = {game_v3['accuracy']*100:.2f}%")
    print(f"  best tickets: {ticket_v3['record']} = {ticket_v3['hit_rate']*100:.2f}%")

    delta_games = game_v3["accuracy"] - game_v21["accuracy"]
    delta_tickets = ticket_v3["hit_rate"] - ticket_v21["hit_rate"]
    print(f"\nDelta game accuracy: {delta_games*100:+.2f} pts")
    print(f"Delta ticket hit rate: {delta_tickets*100:+.2f} pts")


if __name__ == "__main__":
    main()
