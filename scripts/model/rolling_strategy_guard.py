"""Rolling strategy guard — validate live plan on 2026-to-date; only recommend switches after sustained outperformance."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from backtest_parlays import season_start_for
from exhaustive_strategy_search import flat_stats_for_snapshots, load_moneyline_by_day
from strategy_next_tests import build_snapshots, enrich_moneyline
from strategy_research import compound

LIVE_STRATEGY = "corr_nl_reject_both"
CHALLENGERS = [
    "no_low_parlay_223s",
    "corr_nl_reject_both",
    "best_ticket",
    "no_low_skip_forced",
]
STAKE_TIERED = {1: 0.45, 2: 0.35, 3: 0.50}
SWITCH_SIGNAL_DAYS = 14
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "strategy-guard.json"
STATE_PATH = Path(__file__).resolve().parents[2] / "data" / "strategy-guard-state.json"


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"leader_streak_days": 0, "leader_strategy": None, "signals": []}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def window_stats(ml: dict, rule: str, start_day: str, end_day: str, bankroll: float = 100.0) -> dict:
    subset = {day: cands for day, cands in ml.items() if start_day <= day <= end_day}
    snaps = build_snapshots(subset, rule)
    if not snaps:
        return {"days": 0, "flat_roi": 0.0, "end": bankroll, "record": "0-0"}
    flat = flat_stats_for_snapshots(snaps)
    comp = compound(snaps, bankroll, STAKE_TIERED)
    return {
        "days": len(snaps),
        "flat_roi": flat["flat_roi"],
        "flat_profit": flat["flat_profit"],
        "end": comp["end"],
        "record": comp["record"],
    }


def main() -> None:
    today = date.today()
    season_start = season_start_for(today.year)
    prior = (season_start_for(today.year - 1), date(today.year - 1, 8, 17))
    ml, _ = load_moneyline_by_day(season_start, today, prior[0], prior[1])
    ml = {day: cands for day, cands in ml.items() if date.fromisoformat(day) <= today}

    from daily_auto_model import walk_forward_history
    from mlb_api import load_or_fetch_games, load_team_abbreviations

    rows = walk_forward_history(
        load_or_fetch_games(season_start, today),
        load_team_abbreviations(),
        prior_games=load_or_fetch_games(prior[0], prior[1]),
    )
    ml = enrich_moneyline(ml, rows)

    end_day = max(ml) if ml else today.isoformat()
    start_day = season_start.isoformat()
    d14 = (today - timedelta(days=14)).isoformat()

    comparisons: dict[str, dict] = {}
    for rule in CHALLENGERS:
        comparisons[rule] = {
            "season_to_date": window_stats(ml, rule, start_day, end_day),
            "rolling_14d": window_stats(ml, rule, d14, end_day),
        }

    live = comparisons[LIVE_STRATEGY]
    ranked = sorted(
        CHALLENGERS,
        key=lambda rule: (
            comparisons[rule]["rolling_14d"]["flat_roi"],
            comparisons[rule]["season_to_date"]["flat_roi"],
            comparisons[rule]["season_to_date"]["end"],
        ),
        reverse=True,
    )
    leader = ranked[0]

    state = load_state()
    if leader != LIVE_STRATEGY and leader != state.get("leader_strategy"):
        state["leader_streak_days"] = 1
        state["leader_strategy"] = leader
    elif leader != LIVE_STRATEGY and leader == state.get("leader_strategy"):
        state["leader_streak_days"] = int(state.get("leader_streak_days", 0)) + 1
    else:
        state["leader_streak_days"] = 0
        state["leader_strategy"] = LIVE_STRATEGY if leader == LIVE_STRATEGY else leader

    switch_recommended = leader != LIVE_STRATEGY and state["leader_streak_days"] >= SWITCH_SIGNAL_DAYS
    state["signals"] = (state.get("signals") or [])[-30:]
    state["signals"].append(
        {
            "date": today.isoformat(),
            "leader": leader,
            "leader_streak_days": state["leader_streak_days"],
            "switch_recommended": switch_recommended,
        }
    )
    save_state(state)

    output = {
        "generated_at": today.isoformat(),
        "live_strategy": LIVE_STRATEGY,
        "period": {"season_start": start_day, "end": end_day, "rolling_14d_start": d14},
        "stakes": STAKE_TIERED,
        "comparisons": comparisons,
        "ranked_by_rolling_14d_flat_roi": ranked,
        "guard": {
            "leader": leader,
            "leader_streak_days": state["leader_streak_days"],
            "switch_signal_days_required": SWITCH_SIGNAL_DAYS,
            "switch_recommended": switch_recommended,
            "message": (
                f"Keep {LIVE_STRATEGY}."
                if leader == LIVE_STRATEGY
                else (
                    f"{leader} leads rolling 14d ({state['leader_streak_days']}/{SWITCH_SIGNAL_DAYS} days toward switch)."
                    if not switch_recommended
                    else f"Switch to {leader} — beat live on rolling windows for {SWITCH_SIGNAL_DAYS}+ daily signals."
                )
            ),
        },
        "execution_rules": [
            "One ticket per day, all legs same calendar day",
            "Stake 45% single / 35% two-leg / 50% three-leg of current bankroll",
            "Keep betting through losing streaks unless minimum bet size cannot be placed",
        ],
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print(f"Live: {LIVE_STRATEGY}")
    print(f"Leader: {leader} (streak {state['leader_streak_days']}/{SWITCH_SIGNAL_DAYS})")
    for rule in ranked:
        s = comparisons[rule]["season_to_date"]
        r = comparisons[rule]["rolling_14d"]
        print(f"  {rule:<24} season flat {s['flat_roi']:.1%} ({s['record']}) | 14d flat {r['flat_roi']:.1%}")


if __name__ == "__main__":
    main()
