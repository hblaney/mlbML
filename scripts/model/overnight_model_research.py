"""Overnight MODEL improvement — hyperparameter + calibration sweeps on walk-forward."""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

import trained_edge_model as v21
from backtest_parlays import odds_backtest_range
from daily_auto_model import walk_forward_history
from historical_odds import HistoricalOddsStore
from mlb_api import load_or_fetch_games, load_team_abbreviations
from team_tracker import LeagueState

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "data" / "overnight-model-state.json"
LOG_PATH = ROOT / "data" / "overnight-model-research.jsonl"
REPORT_PATH = ROOT / "public" / "overnight-model-research.json"
IDEAS_PATH = ROOT / "public" / "overnight-model-ideas.json"

BASELINE = 0.6066
SHIPPED_BASELINE = "daily-auto-v2.5-base6066"


@dataclass(frozen=True)
class ModelConfig:
    name: str
    market_blend: float | None = None
    refit_every: int | None = None
    current_weight: float | None = None
    series_penalty: float | None = None  # shrink pick prob when lost last 2 vs opponent
    max_depth: int | None = None
    learning_rate: float | None = None


# Queue of hypotheses to test one per cycle — no repeats.
HYPOTHESIS_QUEUE: list[ModelConfig] = [
    ModelConfig("baseline_current"),
    ModelConfig("market_blend_0.08", market_blend=0.08),
    ModelConfig("market_blend_0.10", market_blend=0.10),
    ModelConfig("market_blend_0.03", market_blend=0.03),
    ModelConfig("refit_30", refit_every=30),
    ModelConfig("refit_90", refit_every=90),
    ModelConfig("current_weight_1.5", current_weight=1.5),
    ModelConfig("current_weight_1.0", current_weight=1.0),
    ModelConfig("series_penalty_0.10", series_penalty=0.10),
    ModelConfig("series_penalty_0.15", series_penalty=0.15),
    ModelConfig("gb_depth2", max_depth=2),
    ModelConfig("gb_lr_0.05", learning_rate=0.05),
]


RESEARCH_IDEAS = [
    {
        "idea": "Fresh retrain through yesterday",
        "why": "Model still on Jun 16; Jun 17 results change weights",
        "status": "auto on morning GitHub job",
    },
    {
        "idea": "Series probability penalty",
        "why": "ATL kept picking Braves after SF swept — shrink confidence after 2 losses vs opponent",
        "status": "testing tonight",
    },
    {
        "idea": "Market blend weight tune",
        "why": "0.05 is hand-tuned; wrong blend hurts game accuracy",
        "status": "testing tonight",
    },
    {
        "idea": "Bullpen fatigue / innings last 3 days",
        "why": "Not in feature set yet",
        "status": "backlog",
    },
    {
        "idea": "Pitcher vs opponent team OPS",
        "why": "Handedness + history not explicit",
        "status": "backlog",
    },
    {
        "idea": "HistGBM / registry 948-feature model",
        "why": "Tested — does NOT beat shallow GBM on walk-forward",
        "status": "rejected",
    },
    {
        "idea": "Statcast features",
        "why": "Tested — 60.57% vs 60.66% baseline",
        "status": "rejected",
    },
    {
        "idea": "Robust blend",
        "why": "Tested — 57.17%, much worse",
        "status": "rejected",
    },
    {
        "idea": "Ticket rules (68% legs, series fade)",
        "why": "Not model accuracy — but ticket 47-35 → 52-27",
        "status": "shipped",
    },
]


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"queue_index": 0, "best_accuracy": BASELINE, "best_config": SHIPPED_BASELINE}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def append_log(row: dict) -> None:
    row["logged_at"] = datetime.now().isoformat(timespec="seconds")
    with LOG_PATH.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


@contextmanager
def config_context(config: ModelConfig) -> Iterator[None]:
  orig_blend = v21.MARKET_BLEND_WEIGHT
  orig_refit = v21.REFIT_EVERY
  orig_weight = v21.CURRENT_SEASON_SAMPLE_WEIGHT
  orig_build = v21.build_model
  series_penalty = config.series_penalty or 0.0

  if config.market_blend is not None:
    v21.MARKET_BLEND_WEIGHT = config.market_blend
  if config.refit_every is not None:
    v21.REFIT_EVERY = config.refit_every
  if config.current_weight is not None:
    v21.CURRENT_SEASON_SAMPLE_WEIGHT = config.current_weight

  if config.max_depth is not None or config.learning_rate is not None:

    def custom_build():
      from sklearn.ensemble import GradientBoostingClassifier
      from sklearn.pipeline import Pipeline

      return Pipeline(
        [
          (
            "model",
            GradientBoostingClassifier(
              n_estimators=140,
              learning_rate=config.learning_rate or 0.035,
              max_depth=config.max_depth if config.max_depth is not None else 1,
              subsample=0.90,
              random_state=42,
            ),
          ),
        ]
      )

    v21.build_model = custom_build

  # Patch walk_forward series penalty via predict path
  orig_predict = v21.predict_with_model

  def predict_with_series_penalty(game, league, model):
    pred = orig_predict(game, league, model)
    if series_penalty <= 0:
      return pred
    pick_id = game.home_team_id if pred.predicted_home else game.away_team_id
    opp_id = game.away_team_id if pred.predicted_home else game.home_team_id
    if not league.pick_lost_last_two_in_series(pick_id, opp_id, game.game_date):
      return pred
    pick_p = pred.pick_probability
    new_pick = pick_p * (1 - series_penalty) + 0.5 * series_penalty
    if pred.predicted_home:
      hp = new_pick
    else:
      hp = 1.0 - new_pick
    from fast_edge_model import FastPrediction

    pick_p = max(hp, 1 - hp)
    return FastPrediction(
      home_probability=hp,
      away_probability=1 - hp,
      predicted_home=hp >= 0.5,
      pick_probability=pick_p,
      confidence=pred.confidence,
      notes=[*pred.notes, f"series_penalty={series_penalty}"],
    )

  if series_penalty > 0:
    v21.predict_with_model = predict_with_series_penalty

  try:
    yield
  finally:
    v21.MARKET_BLEND_WEIGHT = orig_blend
    v21.REFIT_EVERY = orig_refit
    v21.CURRENT_SEASON_SAMPLE_WEIGHT = orig_weight
    v21.build_model = orig_build
    v21.predict_with_model = orig_predict


def evaluate_config(config: ModelConfig) -> dict:
  store = HistoricalOddsStore()
  start, end, odds_meta = odds_backtest_range(store)
  team_abbr = load_team_abbreviations()
  prior = load_or_fetch_games(date(start.year - 1, 3, 20), date(start.year - 1, 10, 5))
  games = load_or_fetch_games(start, end)

  with config_context(config):
    rows = walk_forward_history(games, team_abbr, prior_games=prior)

  correct = sum(int(r["correct"]) for r in rows)
  total = len(rows)
  acc = correct / total if total else 0.0
  high = [r for r in rows if r.get("confidence") in ("High", "Elite")]
  med = [r for r in rows if r.get("confidence") == "Medium"]
  return {
    "config": config.name,
    "games": total,
    "accuracy": round(acc, 4),
    "delta_vs_baseline": round(acc - BASELINE, 4),
    "record": f"{correct}-{total - correct}",
    "high_conf_accuracy": round(sum(int(r["correct"]) for r in high) / len(high), 4) if high else 0.0,
    "high_conf_games": len(high),
    "medium_accuracy": round(sum(int(r["correct"]) for r in med) / len(med), 4) if med else 0.0,
    "medium_games": len(med),
    "period": {"start": start.isoformat(), "end": end.isoformat()},
    "beats_baseline": acc > BASELINE + 0.0001,
  }


def write_ideas() -> None:
  IDEAS_PATH.write_text(json.dumps({"generated_at": datetime.now().isoformat(), "ideas": RESEARCH_IDEAS}, indent=2))


def update_report(state: dict, result: dict) -> None:
  history = []
  if REPORT_PATH.exists():
    try:
      history = json.loads(REPORT_PATH.read_text()).get("results", [])
    except json.JSONDecodeError:
      pass
  history.append(result)
  history = history[-30:]
  if result.get("beats_baseline"):
    state["best_accuracy"] = result["accuracy"]
    state["best_config"] = result["config"]
  REPORT_PATH.write_text(
    json.dumps(
      {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "shipped_model": SHIPPED_BASELINE,
        "baseline_accuracy": BASELINE,
        "best_found": {
          "config": state.get("best_config"),
          "accuracy": state.get("best_accuracy"),
        },
        "queue_remaining": max(0, len(HYPOTHESIS_QUEUE) - state.get("queue_index", 0)),
        "latest": result,
        "results": history,
      },
      indent=2,
    )
  )


def main() -> None:
  parser = argparse.ArgumentParser()
  parser.add_argument("--cycle", type=int, default=1)
  args = parser.parse_args()

  state = load_state()
  idx = state.get("queue_index", 0)
  if idx >= len(HYPOTHESIS_QUEUE):
    idx = idx % len(HYPOTHESIS_QUEUE)

  config = HYPOTHESIS_QUEUE[idx]
  state["queue_index"] = idx + 1
  write_ideas()

  print(f"model_research cycle={args.cycle} config={config.name}", flush=True)
  result = evaluate_config(config)
  result["experiment"] = "model_hypothesis"
  append_log(result)
  update_report(state, result)
  save_state(state)

  flag = " *** BEATS BASELINE ***" if result["beats_baseline"] else ""
  print(
    f"{config.name}: {result['accuracy']*100:.2f}% ({result['delta_vs_baseline']*100:+.2f}pts) "
    f"high={result['high_conf_accuracy']*100:.1f}% med={result['medium_accuracy']*100:.1f}%{flag}",
    flush=True,
  )


if __name__ == "__main__":
  main()
