"""Track the user's live bankroll from a fixed start date — compound % stakes on settled daily tickets."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

from backtest_parlays import season_start_for
from exhaustive_strategy_search import STAKE, load_moneyline_by_day
from strategy_next_tests import build_snapshots, enrich_moneyline
from strategy_research import DAILY_CAP

LIVE_STRATEGY = "corr_nl_reject_both"
STAKE_TIERED = {1: 0.45, 2: 0.35, 3: 0.50}
STARTING_BALANCE = 10.0
STATE_PATH = Path(__file__).resolve().parents[2] / "data" / "live-bankroll-state.json"
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "live-bankroll.json"


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def default_state(start_day: str) -> dict:
    return {
        "started_at": start_day,
        "starting_balance": STARTING_BALANCE,
        "balance": STARTING_BALANCE,
        "record": {"wins": 0, "losses": 0},
        "last_settled_date": None,
        "checkpoints": [],
    }


def apply_day(bankroll: float, bets: list[dict]) -> tuple[float, float, bool, int]:
    prev = bankroll
    day_won = True
    leg_count = 1
    raw = [STAKE_TIERED.get(len(bet.get("legs", [])) or 1, 0.25) for bet in bets]
    total = sum(raw)
    scale = DAILY_CAP / total if total > DAILY_CAP else 1.0
    for bet, pct in zip(bets, [value * scale for value in raw]):
        leg_count = len(bet.get("legs", [])) or 1
        if bet.get("profit") is None:
            return bankroll, 0.0, False, leg_count
        bankroll += bet["profit"] * (bankroll * pct / STAKE)
        if not bet.get("won"):
            day_won = False
    return bankroll, bankroll - prev, day_won, leg_count


def bet_is_graded(bet: dict) -> bool:
    return bet.get("profit") is not None and bet.get("won") is not None


def snapshot_is_graded(snapshot: dict) -> bool:
    return bool(snapshot.get("bets")) and all(bet_is_graded(bet) for bet in snapshot["bets"])


def main() -> None:
    reset = "--reset" in sys.argv
    today = date.today()
    today_iso = today.isoformat()
    state = default_state(today_iso) if reset or not load_state() else load_state()

    season_start = season_start_for(today.year)
    prior = (season_start_for(today.year - 1), date(today.year - 1, 8, 17))
    ml, _ = load_moneyline_by_day(season_start, today, prior[0], prior[1])
    ml = {day: candidates for day, candidates in ml.items() if date.fromisoformat(day) <= today}

    from daily_auto_model import walk_forward_history
    from mlb_api import load_or_fetch_games, load_team_abbreviations

    rows = walk_forward_history(
        load_or_fetch_games(season_start, today),
        load_team_abbreviations(),
        prior_games=load_or_fetch_games(prior[0], prior[1]),
    )
    ml = enrich_moneyline(ml, rows)
    snaps_by_day = {snap["date"]: snap for snap in build_snapshots(ml, LIVE_STRATEGY)}

    started_at = state["started_at"]
    last_settled = state.get("last_settled_date")
    cursor = date.fromisoformat(last_settled) + timedelta(days=1) if last_settled else date.fromisoformat(started_at)
    yesterday = today - timedelta(days=1)

    while cursor <= yesterday:
        day_iso = cursor.isoformat()
        if day_iso < started_at:
            cursor += timedelta(days=1)
            continue

        snapshot = snaps_by_day.get(day_iso)
        if snapshot and snapshot_is_graded(snapshot):
            balance, profit, won, leg_count = apply_day(state["balance"], snapshot["bets"])
            state["balance"] = round(balance, 4)
            if won:
                state["record"]["wins"] += 1
            else:
                state["record"]["losses"] += 1
            state["checkpoints"].append(
                {
                    "date": day_iso,
                    "profit": round(profit, 4),
                    "balance": round(balance, 4),
                    "return_pct": round((balance - state["starting_balance"]) / state["starting_balance"], 4),
                    "won": won,
                    "leg_count": leg_count,
                }
            )
            state["last_settled_date"] = day_iso
        cursor += timedelta(days=1)

    today_snapshot = snaps_by_day.get(today_iso)
    today_ticket = None
    if today_snapshot and today_snapshot.get("bets"):
        bet = today_snapshot["bets"][0]
        leg_count = len(bet.get("legs", [])) or 1
        stake_pct = STAKE_TIERED.get(leg_count, 0.35)
        today_ticket = {
            "date": today_iso,
            "leg_count": leg_count,
            "stake_pct": stake_pct,
            "stake_amount": round(state["balance"] * stake_pct, 2),
            "status": "graded" if snapshot_is_graded(today_snapshot) else "pending",
        }

    wins = state["record"]["wins"]
    losses = state["record"]["losses"]
    output = {
        "generated_at": today_iso,
        "strategy": LIVE_STRATEGY,
        "stakes": STAKE_TIERED,
        "daily_exposure_cap": DAILY_CAP,
        "started_at": state["started_at"],
        "starting_balance": state["starting_balance"],
        "balance": state["balance"],
        "profit": round(state["balance"] - state["starting_balance"], 4),
        "return_pct": round((state["balance"] - state["starting_balance"]) / state["starting_balance"], 4),
        "record": f"{wins}-{losses}",
        "last_settled_date": state.get("last_settled_date"),
        "today_ticket": today_ticket,
        "checkpoints": state["checkpoints"],
    }
    save_state(state)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print(f"Live bankroll: ${state['balance']:.2f} (started ${state['starting_balance']:.2f} on {started_at})")
    print(f"Record: {wins}-{losses} · checkpoints: {len(state['checkpoints'])}")


if __name__ == "__main__":
    main()
