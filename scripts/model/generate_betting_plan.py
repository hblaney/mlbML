"""Write public/betting-plan.json from live walk-forward metrics — no fantasy numbers."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from daily_auto_model import MODEL_VERSION, PIPELINE_VERSION

ROOT = Path(__file__).resolve().parents[2]
METRICS_PATH = ROOT / "public" / "live-strategy-metrics.json"
HEALTH_PATH = ROOT / "public" / "model-health.json"
OUTPUT = ROOT / "public" / "betting-plan.json"

LIVE_STRATEGY = "market_agree_parlay"
STAKE_BY_LEG = {"1": 0.12, "2": 0.18, "3": 0.18}


def main() -> None:
    metrics = json.loads(METRICS_PATH.read_text()) if METRICS_PATH.exists() else {}
    health = json.loads(HEALTH_PATH.read_text()) if HEALTH_PATH.exists() else {}
    headline = metrics.get("headline", {})
    flat = metrics.get("flat_per_100_staked", {})
    period = metrics.get("period", {})
    trend = health.get("recent_trend", {})
    last100 = health.get("windows", {}).get("last100", {})

    ticket_hit = headline.get("ticket_hit_rate")
    parlay_hit = headline.get("parlay_hit_rate")
    record = headline.get("record", "?")
    season_acc = trend.get("season_accuracy")
    last100_acc = last100.get("accuracy")
    last100_auc = last100.get("auc")

    rules = [
        "Official board = PA Monte Carlo sim win%. Market is comparison only (edge = sim − book).",
        "Ticket legs: prefer High/Elite sim picks with +EV vs market; anti-market dogs allowed when sim is strong.",
        "Do not hand-build tickets off the research board — the locked ticket is the only official slip.",
        "GBM still trains daily as a diagnostic/fallback; published picks come from the game sim.",
        f"Walk-forward ticket ({LIVE_STRATEGY}): {record} ({ticket_hit:.1%} hit)" if ticket_hit else "Walk-forward hit: see live-strategy-metrics.json",
        f"Model season pick accuracy: {season_acc:.1%}" if season_acc else "Model season accuracy: see model-health.json",
        f"Last-100 form: {last100_acc:.1%} acc, AUC {last100_auc:.2f}" if last100_acc is not None and last100_auc is not None else "",
    ]
    rules = [r for r in rules if r]

    payload = {
        "generated_at": date.today().isoformat(),
        "strategy": LIVE_STRATEGY,
        "mode": "market_agree_small_edge_parlay",
        "achieved_ticket_hit_rate": ticket_hit,
        "model_version": MODEL_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "strategy_rules": rules,
        "stake_by_leg_count": {str(k): v for k, v in STAKE_BY_LEG.items()},
        "market_agree_parlay_gates": {
            "min_edge": 0.015,
            "max_edge": 0.055,
            "min_probability": 0.55,
            "require_market_agrees": True,
            "exclude_low_confidence": True,
            "prefer_legs": [3, 2],
            "allow_single_fallback": True,
        },
        "walk_forward": {
            "record": record,
            "ticket_hit_rate": ticket_hit,
            "parlay_hit_rate": parlay_hit,
            "flat_roi_per_100": flat.get("roi"),
            "bet_days": headline.get("bet_days"),
        },
        "backtest_period": {
            "start": period.get("start", "2026-03-20"),
            "end": period.get("end", date.today().isoformat()),
        },
        "retuned_from": f"Honest publish + market-agree parlays ({date.today().isoformat()})",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2))
    print(
        f"betting_plan_ok strategy={LIVE_STRATEGY} record={record} "
        f"hit={ticket_hit} model={MODEL_VERSION}"
    )


if __name__ == "__main__":
    main()
