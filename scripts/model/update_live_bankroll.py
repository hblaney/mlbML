"""Track live system-ticket results automatically — one corr_nl_reject_both bet per day."""

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
STAKE_TIERED = {1: 0.35, 2: 0.40, 3: 0.30}
DEFAULT_STARTING_BALANCE = 25.0
DEFAULT_STARTED_AT = "2026-06-13"
STATE_PATH = Path(__file__).resolve().parents[2] / "data" / "live-bankroll-state.json"
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "live-bankroll.json"


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def default_state(start_day: str, starting_balance: float) -> dict:
    return {
        "started_at": start_day,
        "starting_balance": starting_balance,
        "balance": starting_balance,
        "record": {"wins": 0, "losses": 0},
        "last_settled_date": None,
        "checkpoints": [],
        "tickets": [],
    }


def stake_pct_for_bet(bet: dict) -> float:
    leg_count = len(bet.get("legs", [])) or 1
    return STAKE_TIERED.get(leg_count, 0.35)


def apply_day(bankroll: float, bets: list[dict]) -> tuple[float, float, bool, int, float]:
    """Apply the day's system ticket(s). Returns balance, profit, won, leg_count, stake_amount."""
    prev = bankroll
    day_won = True
    leg_count = 1
    stake_amount = 0.0
    raw = [STAKE_TIERED.get(len(bet.get("legs", [])) or 1, 0.25) for bet in bets]
    total = sum(raw)
    scale = DAILY_CAP / total if total > DAILY_CAP else 1.0
    for bet, pct in zip(bets, [value * scale for value in raw]):
        leg_count = len(bet.get("legs", [])) or 1
        stake_amount = bankroll * pct
        if bet.get("profit") is None:
            return bankroll, 0.0, False, leg_count, stake_amount
        bankroll += bet["profit"] * (stake_amount / STAKE)
        if not bet.get("won"):
            day_won = False
    return bankroll, bankroll - prev, day_won, leg_count, stake_amount


def bet_is_graded(bet: dict) -> bool:
    return bet.get("profit") is not None and bet.get("won") is not None


def snapshot_is_graded(snapshot: dict) -> bool:
    return bool(snapshot.get("bets")) and all(bet_is_graded(bet) for bet in snapshot["bets"])


def ticket_legs(bet: dict) -> list[str]:
    legs = bet.get("legs") or []
    if legs:
        return [str(leg.get("team", "")).upper() for leg in legs if leg.get("team")]
    team = bet.get("team")
    return [str(team).upper()] if team else []


def serialize_ticket(day_iso: str, bet: dict, *, stake_amount: float, stake_pct: float, profit: float, balance: float, won: bool) -> dict:
    leg_count = len(bet.get("legs", [])) or 1
    return {
        "date": day_iso,
        "label": bet.get("label") or bet.get("side") or "system ticket",
        "legs": ticket_legs(bet),
        "leg_count": leg_count,
        "stake_pct": round(stake_pct, 4),
        "stake_amount": round(stake_amount, 2),
        "profit": round(profit, 2),
        "balance_after": round(balance, 2),
        "won": won,
        "odds": bet.get("odds"),
        "model_probability": bet.get("model_probability"),
    }


def parse_init_args(argv: list[str]) -> tuple[str | None, float | None]:
    if "--init" not in argv:
        return None, None
    index = argv.index("--init")
    start_day = argv[index + 1] if len(argv) > index + 1 else DEFAULT_STARTED_AT
    balance = float(argv[index + 2]) if len(argv) > index + 2 else DEFAULT_STARTING_BALANCE
    return start_day, balance


def parse_wallet_balance(argv: list[str]) -> float | None:
    if "--wallet" not in argv:
        return None
    index = argv.index("--wallet")
    return float(argv[index + 1]) if len(argv) > index + 1 else None


def main() -> None:
    reset = "--reset" in sys.argv
    init_day, init_balance = parse_init_args(sys.argv)
    wallet_balance = parse_wallet_balance(sys.argv)
    today = date.today()
    today_iso = today.isoformat()

    if reset or init_day:
        start_day = init_day or DEFAULT_STARTED_AT
        starting_balance = init_balance if init_balance is not None else DEFAULT_STARTING_BALANCE
        state = default_state(start_day, starting_balance)
    elif load_state():
        state = load_state()
    else:
        state = default_state(DEFAULT_STARTED_AT, DEFAULT_STARTING_BALANCE)

    if wallet_balance is not None:
        state["wallet_balance"] = round(wallet_balance, 2)

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
            bet = snapshot["bets"][0]
            stake_pct = stake_pct_for_bet(bet)
            balance_before = state["balance"]
            balance, profit, won, leg_count, stake_amount = apply_day(state["balance"], snapshot["bets"])
            state["balance"] = round(balance, 4)
            if won:
                state["record"]["wins"] += 1
            else:
                state["record"]["losses"] += 1
            ticket = serialize_ticket(
                day_iso,
                bet,
                stake_amount=stake_amount,
                stake_pct=stake_pct,
                profit=profit,
                balance=balance,
                won=won,
            )
            checkpoint = {
                "date": day_iso,
                "profit": round(profit, 4),
                "balance": round(balance, 4),
                "return_pct": round((balance - state["starting_balance"]) / state["starting_balance"], 4),
                "won": won,
                "leg_count": leg_count,
                "label": ticket["label"],
                "legs": ticket["legs"],
                "stake_amount": ticket["stake_amount"],
            }
            state["checkpoints"].append(checkpoint)
            state.setdefault("tickets", []).append(ticket)
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
            "label": bet.get("label") or bet.get("side") or "system ticket",
            "legs": ticket_legs(bet),
            "leg_count": leg_count,
            "stake_pct": stake_pct,
            "stake_amount": round(state["balance"] * stake_pct, 2),
            "status": "graded" if snapshot_is_graded(today_snapshot) else "pending",
            "odds": bet.get("odds"),
            "model_probability": bet.get("model_probability"),
        }

    wins = state["record"]["wins"]
    losses = state["record"]["losses"]
    total = wins + losses
    output = {
        "generated_at": today_iso,
        "strategy": LIVE_STRATEGY,
        "stakes": STAKE_TIERED,
        "daily_exposure_cap": DAILY_CAP,
        "started_at": state["started_at"],
        "starting_balance": state["starting_balance"],
        "balance": state["balance"],
        "wallet_balance": state.get("wallet_balance"),
        "profit": round(state["balance"] - state["starting_balance"], 4),
        "return_pct": round((state["balance"] - state["starting_balance"]) / state["starting_balance"], 4),
        "record": f"{wins}-{losses}",
        "hit_rate": round(wins / total, 4) if total else None,
        "backtest_ticket_hit_rate": 0.58,
        "last_settled_date": state.get("last_settled_date"),
        "today_ticket": today_ticket,
        "checkpoints": state["checkpoints"],
        "tickets": state.get("tickets", []),
        "tracking_note": "corr_nl_reject_both · model pick only · stakes 35%/40%/30%. Auto-graded after games finish.",
    }
    save_state(state)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print(f"Live bankroll: ${state['balance']:.2f} (started ${state['starting_balance']:.2f} on {started_at})")
    print(f"System ticket record: {wins}-{losses} · tickets logged: {len(state.get('tickets', []))}")


if __name__ == "__main__":
    main()
