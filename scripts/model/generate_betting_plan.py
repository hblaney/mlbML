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

LIVE_STRATEGY = "daily_high_two_leg"
# Prefer 2-leg High stacks; single stake when only one High clears.
STAKE_BY_LEG = {"1": 0.18, "2": 0.12, "3": 0.10}


def main() -> None:
    metrics = json.loads(METRICS_PATH.read_text()) if METRICS_PATH.exists() else {}
    health = json.loads(HEALTH_PATH.read_text()) if HEALTH_PATH.exists() else {}
    headline = metrics.get("headline", {})
    flat = metrics.get("flat_per_100_staked", {})
    period = metrics.get("period", {})
    trend = health.get("recent_trend", {})
    last100 = health.get("windows", {}).get("last100", {})

    ticket_hit = headline.get("ticket_hit_rate")
    record = headline.get("record", "?")
    season_acc = trend.get("season_accuracy")
    last100_acc = last100.get("accuracy")
    last100_auc = last100.get("auc")

    rules = [
        "Official bet = 2-leg High moneyline parlay when 2+ High/Elite legs clear; else one High single; else skip.",
        "Gates (per leg): model p ≥ 55%, form ≥ 0.1, ERA edge ≥ 0.5, edge ≥ 2%, market agrees, +EV, odds better than -250, confirmed starter.",
        "Never pad with Medium/Low. Never force a 3-leg.",
        "Do not hand-build tickets off the research board — the locked ticket is the only official slip.",
        "Model retrains daily through yesterday; REFIT_EVERY=30 (walk-forward validated).",
        f"Walk-forward ticket ({LIVE_STRATEGY}): {record} ({ticket_hit:.1%} hit)"
        if ticket_hit
        else "Walk-forward hit: see live-strategy-metrics.json",
        f"Model season pick accuracy: {season_acc:.1%}" if season_acc else "Model season accuracy: see model-health.json",
        f"Last-100 form: {last100_acc:.1%} acc, AUC {last100_auc:.2f}"
        if last100_acc is not None and last100_auc is not None
        else "",
    ]
    rules = [r for r in rules if r]

    payload = {
        "generated_at": date.today().isoformat(),
        "strategy": LIVE_STRATEGY,
        "mode": "high_two_leg_stack",
        "achieved_ticket_hit_rate": ticket_hit,
        "model_version": MODEL_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "strategy_rules": rules,
        "stake_by_leg_count": {str(k): v for k, v in STAKE_BY_LEG.items()},
        "daily_high_two_leg_gates": {
            "min_probability": 0.55,
            "min_edge": 0.02,
            "min_era_diff": 0.5,
            "min_form_edge": 0.1,
            "min_odds": -250,
            "require_market_agrees": True,
            "require_positive_ev": True,
            "require_starter_certain": True,
            "require_high_confidence": True,
            "prefer_leg_count": 2,
            "max_leg_count": 2,
        },
        "walk_forward": {
            "record": record,
            "ticket_hit_rate": ticket_hit,
            "flat_roi_per_100": flat.get("roi"),
            "bet_days": headline.get("bet_days"),
        },
        "backtest_period": {
            "start": period.get("start", "2026-03-20"),
            "end": period.get("end", date.today().isoformat()),
        },
        "retuned_from": f"Prefer 2-leg High stacks (daily_high_two_leg) ({date.today().isoformat()})",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2))
    print(
        f"betting_plan_ok strategy={LIVE_STRATEGY} record={record} "
        f"hit={ticket_hit} model={MODEL_VERSION}"
    )


if __name__ == "__main__":
    main()
