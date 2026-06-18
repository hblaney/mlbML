"""Batch walk-forward sweep — find configs that beat 60.66% on every game."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from backtest_parlays import odds_backtest_range
from daily_auto_model import walk_forward_history
from historical_odds import HistoricalOddsStore
from mlb_api import load_or_fetch_games, load_team_abbreviations
from overnight_model_research import config_context, evaluate_config, ModelConfig
import trained_edge_model as m

BASELINE = 0.6121
OUTPUT = Path(__file__).resolve().parents[2] / "data" / "model" / "batch-sweep-results.json"


@dataclass(frozen=True)
class SweepConfig:
    name: str
    market_blend: float | None = None
    refit_every: int | None = None
    current_weight: float | None = None
    max_depth: int | None = None
    learning_rate: float | None = None
    n_estimators: int | None = None
    statcast: bool = False
    trained_weight: float | None = None
    sharpen: float | None = None


def eval_custom(cfg: SweepConfig) -> dict:
    orig_estimators = None
    orig_trained = m.TRAINED_MODEL_WEIGHT
    orig_sharpen = m.PUBLIC_CONFIDENCE_SHARPENING
    orig_feat = m.feature_row
    orig_build = m.build_model

    if cfg.n_estimators is not None:

        def build_custom():
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.pipeline import Pipeline

            return Pipeline(
                [
                    (
                        "model",
                        GradientBoostingClassifier(
                            n_estimators=cfg.n_estimators or 140,
                            learning_rate=cfg.learning_rate or 0.035,
                            max_depth=cfg.max_depth if cfg.max_depth is not None else 1,
                            subsample=0.90,
                            random_state=42,
                        ),
                    )
                ]
            )

        m.build_model = build_custom

    if cfg.trained_weight is not None:
        m.TRAINED_MODEL_WEIGHT = cfg.trained_weight
    if cfg.sharpen is not None:
        m.PUBLIC_CONFIDENCE_SHARPENING = cfg.sharpen

    if cfg.statcast:
        if cfg.statcast:
            years = {date.today().year, date.today().year - 1}
            m.preload_statcast_years(years)

        def feat(game, league, **kwargs):
            return orig_feat(game, league, include_statcast=True)

        m.feature_row = feat

    mc = ModelConfig(
        cfg.name,
        market_blend=cfg.market_blend,
        refit_every=cfg.refit_every,
        current_weight=cfg.current_weight,
        max_depth=cfg.max_depth,
        learning_rate=cfg.learning_rate,
    )

    try:
        with config_context(mc):
            result = evaluate_config(mc)
    finally:
        m.feature_row = orig_feat
        m.build_model = orig_build
        m.TRAINED_MODEL_WEIGHT = orig_trained
        m.PUBLIC_CONFIDENCE_SHARPENING = orig_sharpen

    # recent windows
    store = HistoricalOddsStore()
    _, end, _ = odds_backtest_range(store)
    with config_context(mc):
        rows = walk_forward_history(
            load_or_fetch_games(
                date(end.year, 3, 20),
                end,
            ),
            load_team_abbreviations(),
            prior_games=load_or_fetch_games(date(end.year - 1, 3, 20), date(end.year - 1, 10, 5)),
        )

    def window(days: int) -> tuple[float | None, int]:
        since = (end - timedelta(days=days - 1)).isoformat()
        sub = [r for r in rows if r.get("marketBacked") and r["date"] >= since]
        if not sub:
            return None, 0
        return sum(int(r["correct"]) for r in sub) / len(sub), len(sub)

    w7, n7 = window(7)
    w14, n14 = window(14)
    result["last_7d_accuracy"] = round(w7, 4) if w7 is not None else None
    result["last_7d_games"] = n7
    result["last_14d_accuracy"] = round(w14, 4) if w14 is not None else None
    result["last_14d_games"] = n14
    result["beats_baseline"] = result["accuracy"] > BASELINE + 0.0001
    return result


def main() -> None:
    configs = [
        SweepConfig("baseline"),
        SweepConfig("blend_0.04", market_blend=0.04),
        SweepConfig("blend_0.06", market_blend=0.06),
        SweepConfig("blend_0.07", market_blend=0.07),
        SweepConfig("blend_0.08", market_blend=0.08),
        SweepConfig("refit_30", refit_every=30),
        SweepConfig("refit_45", refit_every=45),
        SweepConfig("current_weight_1.5", current_weight=1.5),
        SweepConfig("current_weight_1.25", current_weight=1.25),
        SweepConfig("gb_depth2_lr035", max_depth=2, learning_rate=0.035),
        SweepConfig("gb_depth2_n200", max_depth=2, n_estimators=200),
        SweepConfig("gb_n200", n_estimators=200),
        SweepConfig("gb_n200_depth2", n_estimators=200, max_depth=2),
        SweepConfig("trained_0.95", trained_weight=0.95),
        SweepConfig("trained_1.0", trained_weight=1.0),
        SweepConfig("sharpen_0.75", sharpen=0.75),
        SweepConfig("sharpen_0.85", sharpen=0.85),
        SweepConfig("combo_refit30_w125", refit_every=30, current_weight=1.25),
        SweepConfig("combo_blend06_refit30", market_blend=0.06, refit_every=30),
    ]

    results = []
    best = None
    for cfg in configs:
        print(f"sweep {cfg.name}...", flush=True)
        row = eval_custom(cfg)
        results.append(row)
        flag = " *** BEATS 60.66% ***" if row["beats_baseline"] else ""
        print(
            f"  {row['accuracy']*100:.2f}% ({row['delta_vs_baseline']*100:+.2f}pts) "
            f"7d={row.get('last_7d_accuracy')} 14d={row.get('last_14d_accuracy')}{flag}",
            flush=True,
        )
        if row["beats_baseline"] and (best is None or row["accuracy"] > best["accuracy"]):
            best = row

    payload = {
        "baseline": BASELINE,
        "best": best,
        "results": sorted(results, key=lambda r: r["accuracy"], reverse=True),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {OUTPUT}")
    if best:
        print(f"BEST: {best['config']} at {best['accuracy']*100:.2f}%")
    else:
        print("No config beat 60.66% this sweep — need new features.")


if __name__ == "__main__":
    main()
