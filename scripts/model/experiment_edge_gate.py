"""Does an EV/edge gate on High-Elite parlay legs improve real betting results?

Compares the live strategy (no edge filter — legs picked purely by model probability)
against variants that only keep legs whose model probability beats the no-vig market
implied probability by >= a margin. Walk-forward over the 2026 season.
"""

from __future__ import annotations

from datetime import date

from backtest_parlays import season_start_for
from exhaustive_strategy_search import load_moneyline_by_day
from strategy_next_tests import (
    STAKE_TIERED,
    build_snapshots,
    compound,
    enrich_moneyline,
    summarize,
)


def main() -> None:
    start = date(2026, 3, 20)
    end = date(2026, 6, 16)
    prior = (season_start_for(2025), date(2025, 8, 17))
    ml, _ = load_moneyline_by_day(start, end, prior[0], prior[1])
    ml = {day: c for day, c in ml.items() if date.fromisoformat(day) <= end}

    from daily_auto_model import walk_forward_history
    from mlb_api import load_or_fetch_games, load_team_abbreviations

    rows = walk_forward_history(
        load_or_fetch_games(start, end),
        load_team_abbreviations(),
        prior_games=load_or_fetch_games(*prior),
    )
    ml = enrich_moneyline(ml, rows)

    rules = [
        ("baseline (no edge filter)", "high_elite_76_parlay"),
        ("ev > 0 (vig-incl rail)", "high_elite_evpos"),
        ("edge >= 0%  (drop -EV legs)", "high_elite_edge0"),
        ("edge >= 1%", "high_elite_edge1"),
        ("edge >= 2%", "high_elite_edge2"),
        ("edge >= 3%", "high_elite_edge3"),
        ("edge >= 5%", "high_elite_edge5"),
    ]

    print(f"{'strategy':30s} {'bet_days':>8s} {'record':>9s} {'flat_roi':>9s} {'$17->':>10s}")
    for label, rule in rules:
        snaps = build_snapshots(ml, rule)
        s = summarize(rule, snaps)
        end17 = compound(snaps, 17.0, STAKE_TIERED)["end"]
        print(f"{label:30s} {s['bet_days']:>8d} {s['record']:>9s} {s['flat_roi']:>8.1%} {end17:>10.2f}")


if __name__ == "__main__":
    main()
