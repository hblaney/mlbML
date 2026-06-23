"""Rolling strategy guard — validate live plan on 2026-to-date; only recommend switches after sustained outperformance."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from backtest_parlays import season_start_for
from exhaustive_strategy_search import STAKE, flat_stats_for_snapshots, load_moneyline_by_day
from strategy_next_tests import build_snapshots, enrich_moneyline
from strategy_research import DAILY_CAP, compound

LIVE_STRATEGY = "best_ticket"
CHALLENGERS = [
    "best_ticket",  # max-score selector — useful reference point
]
STAKE_TIERED = {1: 0.35, 2: 0.45, 3: 0.10}
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


def compound_checkpoints(snaps: list[dict], start: float, stake_map: dict[int, float]) -> dict:
    bankroll = start
    min_br = start
    wins = losses = 0
    checkpoints: list[dict] = []

    for snap in snaps:
        prev = bankroll
        day_won = True
        leg_count = 1
        raw = [stake_map.get(len(b.get("legs", [])) or 1, 0.25) for b in snap["bets"]]
        total = sum(raw)
        scale = DAILY_CAP / total if total > DAILY_CAP else 1.0
        for bet, pct in zip(snap["bets"], [r * scale for r in raw]):
            leg_count = len(bet.get("legs", [])) or 1
            bankroll += bet["profit"] * (bankroll * pct / STAKE)
            if not bet["won"]:
                day_won = False
        min_br = min(min_br, bankroll)
        if day_won:
            wins += 1
        else:
            losses += 1
        checkpoints.append(
            {
                "date": snap["date"],
                "profit": round(bankroll - prev, 4),
                "balance": round(bankroll, 4),
                "return_pct": round((bankroll - start) / start, 4) if start else 0.0,
                "won": day_won,
                "leg_count": leg_count,
            }
        )

    flat = flat_stats_for_snapshots(snaps)
    return {
        "starting_bankroll": start,
        "end": round(bankroll, 4),
        "profit": round(bankroll - start, 4),
        "min_bankroll": round(min_br, 4),
        "record": f"{wins}-{losses}",
        "days": wins + losses,
        "flat_roi": flat["flat_roi"],
        "flat_profit": flat["flat_profit"],
        "checkpoints": checkpoints,
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
    for rule in [LIVE_STRATEGY, *CHALLENGERS]:
        comparisons[rule] = {
            "season_to_date": window_stats(ml, rule, start_day, end_day),
            "rolling_14d": window_stats(ml, rule, d14, end_day),
        }

    season_ranked = sorted(
        CHALLENGERS,
        key=lambda rule: comparisons[rule]["season_to_date"]["end"],
        reverse=True,
    )
    ranked_14d = sorted(
        CHALLENGERS,
        key=lambda rule: (
            comparisons[rule]["rolling_14d"]["end"],
            comparisons[rule]["season_to_date"]["end"],
        ),
        reverse=True,
    )
    leader_14d = ranked_14d[0]
    season_leader = season_ranked[0]

    state = load_state()
    if leader_14d != LIVE_STRATEGY and leader_14d != state.get("leader_strategy"):
        state["leader_streak_days"] = 1
        state["leader_strategy"] = leader_14d
    elif leader_14d != LIVE_STRATEGY and leader_14d == state.get("leader_strategy"):
        state["leader_streak_days"] = int(state.get("leader_streak_days", 0)) + 1
    else:
        state["leader_streak_days"] = 0
        state["leader_strategy"] = LIVE_STRATEGY if leader_14d == LIVE_STRATEGY else leader_14d

    switch_recommended = leader_14d != LIVE_STRATEGY and state["leader_streak_days"] >= SWITCH_SIGNAL_DAYS
    state["signals"] = (state.get("signals") or [])[-30:]
    state["signals"].append(
        {
            "date": today.isoformat(),
            "leader_14d": leader_14d,
            "season_leader": season_leader,
            "leader_streak_days": state["leader_streak_days"],
            "switch_recommended": switch_recommended,
        }
    )
    save_state(state)

    live_season_end = comparisons[LIVE_STRATEGY]["season_to_date"]["end"]
    if season_leader == LIVE_STRATEGY and leader_14d != LIVE_STRATEGY:
        guard_message = (
            f"Keep {LIVE_STRATEGY} — #1 full season (${live_season_end:,.0f} from $100 compound). "
            f"{leader_14d} leads last 14 days only "
            f"({state['leader_streak_days']}/{SWITCH_SIGNAL_DAYS} daily signals toward switch)."
        )
    elif season_leader == LIVE_STRATEGY:
        guard_message = f"Keep {LIVE_STRATEGY} — leads both full season and last 14 days."
    elif leader_14d == LIVE_STRATEGY:
        guard_message = (
            f"Keep {LIVE_STRATEGY} — leads last 14 days; "
            f"{season_leader} still ahead on full season."
        )
    elif switch_recommended:
        guard_message = (
            f"Switch to {leader_14d} — beat live on rolling 14d compound "
            f"for {SWITCH_SIGNAL_DAYS}+ consecutive daily signals."
        )
    else:
        guard_message = (
            f"{leader_14d} leads rolling 14d ({state['leader_streak_days']}/{SWITCH_SIGNAL_DAYS} "
            f"daily signals toward switch). Full-season leader: {season_leader}."
        )

    season_snaps = build_snapshots(
        {day: cands for day, cands in ml.items() if start_day <= day <= end_day},
        LIVE_STRATEGY,
    )
    live_from_10 = compound_checkpoints(season_snaps, 10.0, STAKE_TIERED)
    live_from_100 = compound_checkpoints(season_snaps, 100.0, STAKE_TIERED)

    output = {
        "generated_at": today.isoformat(),
        "live_strategy": LIVE_STRATEGY,
        "period": {"season_start": start_day, "end": end_day, "rolling_14d_start": d14},
        "stakes": STAKE_TIERED,
        "comparisons": comparisons,
        "ranked_by_season_compound": season_ranked,
        "ranked_by_rolling_14d_compound": ranked_14d,
        "guard": {
            "season_leader": season_leader,
            "leader_14d": leader_14d,
            "leader_streak_days": state["leader_streak_days"],
            "switch_signal_days_required": SWITCH_SIGNAL_DAYS,
            "switch_recommended": switch_recommended,
            "message": guard_message,
        },
        "live_compound": {
            "strategy": LIVE_STRATEGY,
            "stakes": STAKE_TIERED,
            "daily_exposure_cap": DAILY_CAP,
            "from_10": live_from_10,
            "from_100": live_from_100,
        },
        "execution_rules": [
            "One ticket per day, all legs same calendar day",
            "Stake 45% single / 35% two-leg / 50% three-leg of current bankroll",
            "Keep betting through losing streaks unless minimum bet size cannot be placed",
        ],
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print(f"Live: {LIVE_STRATEGY}")
    print(f"Season leader: {season_leader} | 14d leader: {leader_14d} (streak {state['leader_streak_days']}/{SWITCH_SIGNAL_DAYS})")
    for rule in season_ranked:
        s = comparisons[rule]["season_to_date"]
        r = comparisons[rule]["rolling_14d"]
        print(f"  {rule:<24} season flat {s['flat_roi']:.1%} ({s['record']}) | 14d flat {r['flat_roi']:.1%}")


if __name__ == "__main__":
    main()
