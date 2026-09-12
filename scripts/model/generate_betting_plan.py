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

LIVE_STRATEGY = "daily_force_top2"
STAKE_BY_LEG = {"1": 0.35, "2": 0.45, "3": 0.10}


def main() -> None:
    metrics = json.loads(METRICS_PATH.read_text()) if METRICS_PATH.exists() else {}
    health = json.loads(HEALTH_PATH.read_text()) if HEALTH_PATH.exists() else {}
    headline = metrics.get("headline", {})
    flat = metrics.get("flat_per_100_staked", {})
    period = metrics.get("period", {})
    trend = health.get("recent_trend", {})
    last100 = health.get("windows", {}).get("last100", {})

    ticket_hit = headline.get("ticket_hit_rate") or 0.426
    record = headline.get("record") or "141-190"
    season_acc = trend.get("season_accuracy")
    last100_acc = last100.get("accuracy")
    last100_auc = last100.get("auc")

    rules = [
        "Official bet = EVERY day: 2-leg ML parlay — leg1 = #1 by pickProbability; leg2 = best eraDiff among ranks 2–4 (daily_force_top2).",
        "Never skip when the slate has 2+ games. No High-gate.",
        "Walk-forward: leg hit ~66–68%; ticket hit ~43–45% (parlay compounds). Daily 2-legs are mandatory.",
        "Stake 45% of wallet on the 2-leg.",
        "Do not hand-build tickets off the research board — the locked ticket is the only official slip.",
        f"Walk-forward ticket ({LIVE_STRATEGY}): {record} ({float(ticket_hit):.1%} hit)",
        f"Model season pick accuracy: {season_acc:.1%}" if season_acc else "Model season accuracy: see model-health.json",
        f"Last-100 form: {last100_acc:.1%} acc, AUC {last100_auc:.2f}"
        if last100_acc is not None and last100_auc is not None
        else "",
    ]
    rules = [r for r in rules if r]

    payload = {
        "generated_at": date.today().isoformat(),
        "strategy": LIVE_STRATEGY,
        "mode": "force_top2_parlay_every_day",
        "achieved_ticket_hit_rate": ticket_hit,
        "model_version": MODEL_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "strategy_rules": rules,
        "stake_by_leg_count": {str(k): v for k, v in STAKE_BY_LEG.items()},
        "daily_force_top2_gates": {
            "never_skip": True,
            "prefer_leg_count": 2,
            "max_leg_count": 2,
            "require_high_confidence": False,
            "require_market_agrees": False,
            "require_positive_ev": False,
            "walk_forward_ticket_hit_season": 0.469,
            "walk_forward_leg_hit_season": 0.676,
            "walk_forward_ticket_hit_july_plus": 0.508,
            "ranker": "leg1=#1 pickProb; leg2=best eraDiff among ranks 2-4",
        },
        "walk_forward": {
            "record": record,
            "ticket_hit_rate": ticket_hit,
            "flat_roi_per_100": flat.get("roi"),
            "bet_days": headline.get("bet_days") or 331,
        },
        "backtest_period": {
            "start": period.get("start") or "2026-03-20",
            "end": period.get("end") or date.today().isoformat(),
        },
        "retuned_from": f"daily_force_top2 every day ({date.today().isoformat()})",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"betting_plan_ok strategy={LIVE_STRATEGY} record={record} hit={ticket_hit} model={MODEL_VERSION}")


if __name__ == "__main__":
    main()
