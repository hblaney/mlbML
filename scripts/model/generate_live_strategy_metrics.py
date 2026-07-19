"""Honest live-strategy metrics — flat ROI and hit rate, not compound fantasy."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from backtest_parlays import season_start_for
from exhaustive_strategy_search import flat_stats_for_snapshots, load_moneyline_by_day
from strategy_next_tests import build_snapshots, enrich_moneyline
from strategy_research import compound

LIVE_STRATEGY = "market_agree_parlay"
STAKE_TIERED = {1: 0.35, 2: 0.45, 3: 0.10}
OUTPUT = Path(__file__).resolve().parents[2] / "public" / "live-strategy-metrics.json"


def _ticket_breakdown(snaps: list[dict]) -> dict:
    singles = parlays = single_w = par_w = 0
    bet_days = 0
    for snap in snaps:
        if snap.get("bets"):
            bet_days += 1
        for bet in snap["bets"]:
            legs = bet.get("legs") or []
            if legs:
                parlays += 1
                if bet["won"]:
                    par_w += 1
            else:
                singles += 1
                if bet["won"]:
                    single_w += 1
    total = singles + parlays
    return {
        "bet_days": bet_days,
        "total_bets": total,
        "parlay_days": parlays,
        "single_days": bet_days if singles else 0,
        "parlay_share": round(parlays / total, 4) if total else 0.0,
        "ticket_hit_rate": round((single_w + par_w) / total, 4) if total else 0.0,
        "parlay_hit_rate": round(par_w / parlays, 4) if parlays else None,
        "single_hit_rate": round(single_w / singles, 4) if singles else None,
        "record": f"{single_w + par_w}-{total - single_w - par_w}",
    }


def main() -> None:
    start = date(2026, 3, 20)
    end = date.today()
    prior = (season_start_for(2025), date(2025, 8, 17))
    ml, _ = load_moneyline_by_day(start, end, prior[0], prior[1])
    ml = {day: cands for day, cands in ml.items() if date.fromisoformat(day) <= end}

    from daily_auto_model import walk_forward_history
    from mlb_api import load_or_fetch_games, load_team_abbreviations

    rows = walk_forward_history(
        load_or_fetch_games(start, end),
        load_team_abbreviations(),
        prior_games=load_or_fetch_games(*prior),
    )
    ml = enrich_moneyline(ml, rows)

    snaps = build_snapshots(ml, LIVE_STRATEGY)
    flat = flat_stats_for_snapshots(snaps)
    c10 = compound(snaps, 10.0, STAKE_TIERED)
    c100 = compound(snaps, 100.0, STAKE_TIERED)
    breakdown = _ticket_breakdown(snaps)

    payload = {
        "generated_at": date.today().isoformat(),
        "strategy": LIVE_STRATEGY,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "stakes": STAKE_TIERED,
        "headline": breakdown,
        "flat_per_100_staked": {
            "roi": round(flat["flat_roi"], 4),
            "profit_units": round(flat["flat_profit"], 2),
            "hit_rate": round(flat["hit_rate"], 4),
        },
        "compound_reference": {
            "from_10": {
                "end": c10["end"],
                "min_bankroll": c10["min_bankroll"],
                "record": c10["record"],
            },
            "from_100": {
                "end": c100["end"],
                "min_bankroll": c100["min_bankroll"],
                "record": c100["record"],
            },
            "note": "Compound paths assume full re-stake; use flat ROI for realistic edge sizing.",
        },
        "note": (
            "Primary KPIs: ticket hit rate and flat ROI per $100 staked at fixed unit size. "
            "Parlay share shows how often the strategy compounds vs elite-single fallback."
        ),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2))
    h = breakdown
    print(
        f"{LIVE_STRATEGY}: {h['record']} hit={h['ticket_hit_rate']:.1%} "
        f"flat={flat['flat_roi']:.1%} par={h['parlay_days']}/{h['bet_days']} "
        f"par_hit={h['parlay_hit_rate']} -> {OUTPUT.name}"
    )


if __name__ == "__main__":
    main()
