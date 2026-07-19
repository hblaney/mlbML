"""Diagnostic: where does daily_best_single lose, and can a filter raise hit rate?

Read-only analysis. Builds the live strategy's per-bet sequence (walk-forward, real
odds) and segments by odds and model probability, then tests candidate filters.
"""

from __future__ import annotations

from datetime import date

from backtest_parlays import season_start_for
from exhaustive_strategy_search import load_moneyline_by_day
from strategy_next_tests import build_snapshots, enrich_moneyline


def main() -> None:
    start = date(2026, 3, 20)
    end = date.today()
    prior = (season_start_for(2025), date(2025, 8, 17))
    ml, _ = load_moneyline_by_day(start, end, prior[0], prior[1])
    ml = {d: c for d, c in ml.items() if date.fromisoformat(d) <= end}

    from daily_auto_model import walk_forward_history
    from mlb_api import load_or_fetch_games, load_team_abbreviations

    rows = walk_forward_history(
        load_or_fetch_games(start, end),
        load_team_abbreviations(),
        prior_games=load_or_fetch_games(*prior),
    )
    ml = enrich_moneyline(ml, rows)

    snaps = build_snapshots(ml, "daily_best_single")
    bets = []
    for snap in snaps:
        b = snap["bets"][0]
        bets.append(b)

    if bets:
        print("sample bet keys:", sorted(bets[0].keys()))

    def seg(label, sel):
        n = len(sel)
        if not n:
            print(f"  {label:22} n=  0")
            return
        w = sum(1 for b in sel if b["won"])
        profit = sum(b["profit"] for b in sel)
        roi = profit / (n * 1.0) if n else 0  # profit is per-unit-staked at STAKE
        print(f"  {label:22} n={n:3}  hit={100*w/n:5.1f}%  unit_profit={profit:+7.2f}  roi={100*roi:+6.1f}%")

    print("\n=== by ODDS bucket (american) ===")
    buckets = [(-10000, -250), (-250, -200), (-200, -160), (-160, -130), (-130, 100), (100, 10000)]
    for lo, hi in buckets:
        sel = [b for b in bets if lo <= b["odds"] < hi]
        seg(f"odds [{lo},{hi})", sel)

    print("\n=== by MODEL PROBABILITY bucket ===")
    for lo, hi in [(0.60, 0.65), (0.65, 0.70), (0.70, 0.75), (0.75, 1.01)]:
        sel = [b for b in bets if lo <= b["model_probability"] < hi]
        seg(f"prob [{lo:.2f},{hi:.2f})", sel)

    print("\n=== by EDGE bucket (model - book) ===")
    for lo, hi in [(-1, 0.0), (0.0, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, 1.0)]:
        sel = [b for b in bets if lo <= b["edge"] < hi]
        seg(f"edge [{lo:.2f},{hi:.2f})", sel)

    def filt(b):
        return b["model_probability"] >= 0.65 and b["edge"] >= 0.02 and b["odds"] > -250

    print("\n=== candidate FILTERS vs baseline (all bets) ===")
    seg("BASELINE (all)", bets)
    seg("drop odds<=-200", [b for b in bets if b["odds"] > -200])
    seg("require edge>=0.02", [b for b in bets if b["edge"] >= 0.02])
    seg("prob>=0.65", [b for b in bets if b["model_probability"] >= 0.65])
    seg("prob>=0.65 & edge>=0.02", [b for b in bets if b["model_probability"] >= 0.65 and b["edge"] >= 0.02])
    seg("CHOSEN p>=.65 e>=.02 o>-250", [b for b in bets if filt(b)])

    print("\n=== RECENT-WINDOW robustness (no overfit check) ===")
    bets_sorted = sorted(bets, key=lambda b: b["date"])
    for label, n in [("last 30 bets", 30), ("last 45 bets", 45), ("full season", len(bets_sorted))]:
        sub = bets_sorted[-n:]
        seg(f"{label} BASE", sub)
        seg(f"{label} CHOSEN", [b for b in sub if filt(b)])


if __name__ == "__main__":
    main()
