"""Out-of-sample strategy validation: 2025 holdout vs 2026 in-sample."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from backtest_parlays import odds_backtest_range, season_start_for
from exhaustive_strategy_search import (
    MAX_DAILY_EXPOSURE,
    load_moneyline_by_day,
    run_period_search,
    strategy_grid,
)
from historical_odds import HistoricalOddsStore

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "oos-strategy-validation.json"
OOS_STAKE_PCT = 0.30

FOCUS_STRATEGIES = (
    "two_or_three_best",
    "two_or_three_or_single",
    "two_or_three_plus_single",
    "two_and_single",
    "two_and_three",
    "filtered_2_and_3",
    "all_filtered_parlays",
    "always_2",
    "best_ticket",
    "max_any_combo",
    "parlay_3",
    "single",
)


def oos_grid() -> list[tuple[str, str, float | None]]:
    return strategy_grid()


def period_for_label(label: str, start: date, end: date, prior: tuple[date, date] | None) -> dict:
    print(f"Loading walk-forward {label} {start}..{end}...", flush=True)
    prior_start, prior_end = prior or (None, None)
    moneyline_by_day, walk_meta = load_moneyline_by_day(start, end, prior_start, prior_end)
    print(f"  {walk_meta['game_days_with_odds']} bet days, running {len(oos_grid())} strategies @ {OOS_STAKE_PCT:.0%}...", flush=True)
    results_raw, results_fair = run_period_search(moneyline_by_day, oos_grid(), OOS_STAKE_PCT)

    fair_10k = [r for r in results_fair if r["bankroll"] == 10000]
    fair_10 = [r for r in results_fair if r["bankroll"] == 10]
    one_bet_fair = [r for r in fair_10k if r["multi_bet_days"] == 0]

    by_id = {r["strategy_id"]: r for r in fair_10k}
    focus = {sid: by_id.get(sid) for sid in FOCUS_STRATEGIES if sid in by_id}

    return {
        "label": label,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "walk_forward": walk_meta,
        "stake_pct": OOS_STAKE_PCT,
        "strategies_tested": len(oos_grid()),
        "winner_one_bet_fair": one_bet_fair[0] if one_bet_fair else None,
        "winner_any_fair": fair_10k[0] if fair_10k else None,
        "top_fair_10k": fair_10k[:15],
        "top_fair_10": fair_10[:5],
        "focus_strategies_fair_10k": focus,
    }


def rank_of(results: list[dict], strategy_id: str) -> int | None:
    for index, row in enumerate(results):
        if row["strategy_id"] == strategy_id:
            return index + 1
    return None


def overfitting_summary(period_2025: dict, period_2026: dict) -> dict:
    focus_2025 = period_2025["focus_strategies_fair_10k"]
    focus_2026 = period_2026["focus_strategies_fair_10k"]
    top_2025 = period_2025["top_fair_10k"]
    top_2026 = period_2026["top_fair_10k"]

    candidate = "two_or_three_best"
    cand_25 = focus_2025.get(candidate)
    cand_26 = focus_2026.get(candidate)
    always_25 = focus_2025.get("always_2")
    always_26 = focus_2026.get("always_2")

    lines: list[str] = []
    if cand_25 and cand_26:
        if cand_25["flat_roi"] > 0 and cand_26["flat_roi"] > 0:
            lines.append(
                f"{candidate} flat ROI positive in both periods (2025 {cand_25['flat_roi']:.1%}, 2026 {cand_26['flat_roi']:.1%})."
            )
        elif cand_25["flat_roi"] <= 0:
            lines.append(
                f"WARNING: {candidate} flat ROI negative on 2025 holdout ({cand_25['flat_roi']:.1%}) — possible overfit."
            )
        rank_25 = rank_of(top_2025, candidate)
        rank_26 = rank_of(top_2026, candidate)
        lines.append(f"{candidate} fair rank: #{rank_25} in 2025 vs #{rank_26} in 2026.")

    if always_25 and always_26 and cand_25 and cand_26:
        if cand_25["end"] > always_25["end"] and cand_26["end"] > always_26["end"]:
            lines.append("two_or_three_best beats always_2 on fair compound in BOTH periods.")
        elif cand_25["end"] <= always_25["end"]:
            lines.append("On 2025 holdout, always_2 matches or beats two_or_three_best.")

    alt = period_2025["winner_one_bet_fair"]
    if alt and alt["strategy_id"] != candidate:
        lines.append(f"2025 one-bet winner: {alt['strategy_id']} (not {candidate}).")

    return {
        "two_or_three_best": {
            "2025": cand_25,
            "2026": cand_26,
            "2025_rank": rank_of(top_2025, candidate),
            "2026_rank": rank_of(top_2026, candidate),
        },
        "always_2": {"2025": always_25, "2026": always_26},
        "verdict": " ".join(lines) if lines else "Insufficient data for comparison.",
    }


def main() -> None:
    store = HistoricalOddsStore()
    odds_end_2025 = date(2025, 8, 17)
    start_2026, end_2026, odds_metadata = odds_backtest_range(store)

    period_2025 = period_for_label(
        "2025_holdout",
        season_start_for(2025),
        odds_end_2025,
        (season_start_for(2024), date(2024, 10, 1)),
    )
    period_2026 = period_for_label(
        "2026_in_sample",
        start_2026,
        end_2026,
        (season_start_for(2025), odds_end_2025),
    )

    output = {
        "generated_at": date.today().isoformat(),
        "method": "walk_forward_oos_validation",
        "fair_daily_exposure_cap": MAX_DAILY_EXPOSURE,
        "stake_pct": OOS_STAKE_PCT,
        "odds_metadata": odds_metadata,
        "note": (
            "2025 holdout Mar 20–Aug 17 (odds import). 2026 in-sample through latest odds. "
            "Identical rules/filters — no re-tuning on 2025. Fixed 30% fair daily cap."
        ),
        "period_2025": period_2025,
        "period_2026": period_2026,
        "overfitting_analysis": overfitting_summary(period_2025, period_2026),
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print("\n2025 holdout top fair (one-bet):")
    for row in [r for r in period_2025["top_fair_10k"] if r["multi_bet_days"] == 0][:6]:
        print(f"  {row['strategy_id']:<28} ${row['end']:>12,.0f}  flat {row['flat_roi']:>6.1%}  {row['wins']}-{row['losses']}")
    print("\n2026 in-sample top fair (one-bet):")
    for row in [r for r in period_2026["top_fair_10k"] if r["multi_bet_days"] == 0][:6]:
        print(f"  {row['strategy_id']:<28} ${row['end']:>12,.0f}  flat {row['flat_roi']:>6.1%}  {row['wins']}-{row['losses']}")
    print("\nFocus comparison (fair $10k @ 30%):")
    for sid in FOCUS_STRATEGIES:
        r25 = period_2025["focus_strategies_fair_10k"].get(sid)
        r26 = period_2026["focus_strategies_fair_10k"].get(sid)
        if r25 and r26:
            print(
                f"  {sid:<28} 2025 ${r25['end']:>10,.0f} ({r25['flat_roi']:>5.1%})  |  2026 ${r26['end']:>10,.0f} ({r26['flat_roi']:>5.1%})"
            )
    print("\n", output["overfitting_analysis"]["verdict"])


if __name__ == "__main__":
    main()
