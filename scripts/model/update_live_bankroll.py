"""Track live system-ticket replay — one med60_force2_223s ticket per day from archived boards."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from backtest_parlays import STAKE, decimal_odds, season_start_for, settle_parlay
from exhaustive_strategy_search import load_moneyline_by_day
from strategy_next_tests import build_snapshots, enrich_moneyline
from strategy_research import DAILY_CAP

LIVE_STRATEGY = "med60_force2_223s"
STAKE_TIERED = {1: 0.35, 2: 0.45, 3: 0.10}
FLAT_PROVE_OUT_USD = 5.0
PROVE_OUT_TICKETS = 5
LIVE_STAKE_MODE = "flat_5"  # flat_5 until live proves out; then compound_tiered
DEFAULT_STARTING_BALANCE = 25.0
DEFAULT_STARTED_AT = "2026-06-13"
TRACKING_DISCLAIMER = (
    "Tracks the Best Bets system ticket — bet this exact card on Robinhood. "
    f"Currently ${FLAT_PROVE_OUT_USD:.0f} flat per ticket."
)
REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = REPO_ROOT / "data" / "live-bankroll-state.json"
OUTPUT_PATH = REPO_ROOT / "public" / "live-bankroll.json"


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
    if legs and isinstance(legs[0], str):
        return [str(leg).upper() for leg in legs]
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


def find_archived_board_commit(day_iso: str) -> str | None:
    grep = subprocess.run(
        [
            "git",
            "log",
            "--all",
            "--format=%H",
            f"--grep=Update daily MLB model outputs for {day_iso}",
            "-1",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    commit = grep.stdout.strip()
    if commit:
        return commit

    matches: list[tuple[str, str]] = []
    proc = subprocess.run(
        ["git", "log", "--all", "--format=%H", "--", "public/predictions.json"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    for commit in proc.stdout.splitlines()[:120]:
        show = subprocess.run(
            ["git", "show", f"{commit}:public/predictions.json"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )
        if show.returncode != 0:
            continue
        try:
            payload = json.loads(show.stdout)
        except json.JSONDecodeError:
            continue
        if payload.get("generated_at") != day_iso:
            continue
        predictions = payload.get("predictions", [])
        if not any(str(row.get("date", "")).startswith(day_iso) for row in predictions):
            continue
        board_at = str(payload.get("board_generated_at", ""))
        matches.append((board_at, commit))

    if not matches:
        return None

    same_day = [match for match in matches if match[0].startswith(day_iso)]
    if same_day:
        return sorted(same_day, key=lambda item: item[0])[0][1]
    return sorted(matches, key=lambda item: item[0])[0][1]


def load_archived_board(day_iso: str) -> dict | None:
    commit = find_archived_board_commit(day_iso)
    if not commit:
        return None
    show = subprocess.run(
        ["git", "show", f"{commit}:public/predictions.json"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    )
    return json.loads(show.stdout)


def ticket_from_archived_board(board_path: Path) -> dict | None:
    script_path = REPO_ROOT / "scripts" / "model" / "_ticket_from_board.mjs"
    script_path.write_text(
        "import { readFileSync } from 'fs';\n"
        "import { getBestDailyTicket } from '../../lib/data.ts';\n"
        "const board = JSON.parse(readFileSync(process.argv.at(-1), 'utf8')).predictions;\n"
        "const ticket = getBestDailyTicket(board);\n"
        "if (!ticket) { console.log('null'); process.exit(0); }\n"
        "if (ticket.kind === 'single') {\n"
        "  const bet = ticket.bet;\n"
        "  console.log(JSON.stringify({ kind: 'single', label: `${bet.team.abbreviation} ML`, legs: [bet.team.abbreviation], leg_count: 1, odds: bet.odds, model_probability: bet.modelProbability }));\n"
        "} else {\n"
        "  const legs = ticket.parlay.legs;\n"
        "  console.log(JSON.stringify({ kind: 'parlay', label: legs.map((leg) => `${leg.team.abbreviation} ML`).join(' + '), legs: legs.map((leg) => leg.team.abbreviation), leg_count: legs.length, odds: ticket.parlay.americanOdds, model_probability: ticket.parlay.probability }));\n"
        "}\n"
    )
    try:
        proc = subprocess.run(
            ["npx", "--yes", "tsx", str(script_path), str(board_path)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    raw = proc.stdout.strip()
    if not raw or raw == "null":
        return None
    return json.loads(raw)


def team_won_on_day(team_abbr: str, day: date, games, team_abbr_map: dict[int, str]) -> bool | None:
    team = team_abbr.lower()
    for game in games:
        if game.game_date != day:
            continue
        home = team_abbr_map.get(game.home_team_id, "").lower()
        away = team_abbr_map.get(game.away_team_id, "").lower()
        if team not in {home, away}:
            continue
        if not game.is_final or game.home_score is None or game.away_score is None:
            return None
        winner = home if game.home_score > game.away_score else away
        return team == winner


def team_leg_status_on_day(team_abbr: str, day: date, team_abbr_map: dict[int, str]) -> str | None:
    """Return won | lost | void | pending for a team's game on a date."""
    import ssl
    from urllib.request import urlopen
    import certifi

    team = team_abbr.lower()
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={day.isoformat()}&hydrate=team"
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urlopen(url, timeout=30, context=ctx) as response:
        payload = json.loads(response.read())

    for day_block in payload.get("dates", []):
        for game in day_block.get("games", []):
            home = game["teams"]["home"]["team"]["abbreviation"].lower()
            away = game["teams"]["away"]["team"]["abbreviation"].lower()
            if team not in {home, away}:
                continue
            status = str(game.get("status", {}).get("detailedState", "")).lower()
            if "postpon" in status or "cancel" in status:
                return "void"
            abstract = game.get("status", {}).get("abstractGameState")
            if abstract != "Final":
                return "pending"
            hs = game["teams"]["home"].get("score")
            aw = game["teams"]["away"].get("score")
            if hs is None or aw is None:
                return "pending"
            winner = home if hs > aw else away
            return "won" if team == winner else "lost"
    return None


def settle_parlay_with_voids(leg_rows: list[dict]) -> dict:
    """Robinhood-style: void legs drop off; all remaining must win."""
    active = [leg for leg in leg_rows if not leg.get("void")]
    if not active:
        return {"won": True, "profit": 0.0, "odds": None, "void_legs": len(leg_rows)}
    if any(not leg["won"] for leg in active):
        return {"won": False, "profit": -STAKE, "odds": None, "void_legs": len(leg_rows) - len(active)}

    if len(active) == 1:
        leg = active[0]
        profit = STAKE * (decimal_odds(int(leg["odds"])) - 1) if leg["won"] else -STAKE
        return {"won": True, "profit": profit, "odds": leg["odds"], "void_legs": len(leg_rows) - len(active)}

    settled = settle_parlay(active)
    settled["void_legs"] = len(leg_rows) - len(active)
    return settled


def grade_archived_ticket(ticket: dict, day_iso: str, board: dict) -> dict | None:
    from mlb_api import load_team_abbreviations

    day = date.fromisoformat(day_iso)
    abbr_map = load_team_abbreviations()
    predictions = board.get("predictions", [])
    pred_by_team: dict[str, dict] = {}
    for row in predictions:
        pick = str(row.get("predictedTeam", "")).lower()
        if pick:
            pred_by_team[pick] = row

    leg_rows = []
    for leg in ticket["legs"]:
        row = pred_by_team.get(str(leg).lower())
        if not row:
            return None
        pick_home = str(row.get("predictedTeam", "")).lower() == str(row.get("homeTeam", "")).lower()
        odds = row.get("homeMoneyline") if pick_home else row.get("awayMoneyline")
        status = team_leg_status_on_day(str(leg), day, abbr_map)
        if status is None or status == "pending" or odds is None:
            return None
        if status == "void":
            leg_rows.append(
                {
                    "team": str(leg).upper(),
                    "odds": odds,
                    "won": True,
                    "void": True,
                    "model_probability": row.get("pickProbability"),
                }
            )
            continue
        leg_rows.append(
            {
                "team": str(leg).upper(),
                "odds": odds,
                "won": status == "won",
                "void": False,
                "model_probability": row.get("pickProbability"),
            }
        )

    if ticket["leg_count"] == 1:
        leg = leg_rows[0]
        if leg.get("void"):
            return {
                "label": ticket["label"],
                "legs": ticket["legs"],
                "won": True,
                "profit": 0.0,
                "odds": leg["odds"],
                "model_probability": ticket.get("model_probability"),
                "void": True,
            }
        profit = STAKE * (decimal_odds(int(leg["odds"])) - 1) if leg["won"] else -STAKE
        return {
            "label": ticket["label"],
            "legs": ticket["legs"],
            "won": leg["won"],
            "profit": profit,
            "odds": leg["odds"],
            "model_probability": ticket.get("model_probability"),
        }

    settled = settle_parlay_with_voids(leg_rows)
    return {
        "label": ticket["label"],
        "legs": ticket["legs"],
        "won": settled["won"],
        "profit": settled["profit"],
        "odds": settled.get("odds") or ticket.get("odds"),
        "model_probability": ticket.get("model_probability"),
        "void_legs": settled.get("void_legs", 0),
    }


def apply_day_flat(stake_usd: float, bet: dict) -> tuple[float, bool]:
    """Flat stake P/L from a graded bet (profit field is per $100)."""
    if bet.get("profit") is None or bet.get("won") is None:
        return 0.0, False
    profit = float(bet["profit"]) * (stake_usd / STAKE)
    return profit, bool(bet.get("won"))


def graded_snapshot_for_day(day_iso: str, snaps_by_day: dict[str, dict]) -> tuple[dict | None, str]:
    """Prefer the archived board ticket (what the site showed) over walk-forward rebuild."""
    board_snapshot = fallback_snapshot_for_day(day_iso)
    if board_snapshot and snapshot_is_graded(board_snapshot):
        return board_snapshot, "archived_board"
    snapshot = snaps_by_day.get(day_iso)
    if snapshot and snapshot_is_graded(snapshot):
        return snapshot, "walk_forward_rebuild"
    return None, "missing"


def fallback_snapshot_for_day(day_iso: str) -> dict | None:
    board = load_archived_board(day_iso)
    if not board:
        return None
    temp_path = REPO_ROOT / "data" / f"archived-board-{day_iso}.json"
    temp_path.write_text(json.dumps(board, indent=2))
    ticket = ticket_from_archived_board(temp_path)
    if not ticket:
        return None
    graded = grade_archived_ticket(ticket, day_iso, board)
    if not graded:
        return None
    return {"date": day_iso, "bets": [graded]}


def settle_day(
    state: dict,
    day_iso: str,
    snapshot: dict,
    *,
    source: str,
) -> None:
    bet = snapshot["bets"][0]
    tickets_done = len(state.get("tickets", []))
    use_flat = LIVE_STAKE_MODE == "flat_5" or tickets_done < PROVE_OUT_TICKETS

    if use_flat:
        stake_amount = FLAT_PROVE_OUT_USD
        stake_pct = round(stake_amount / max(state["balance"], 1.0), 4)
        profit, won = apply_day_flat(FLAT_PROVE_OUT_USD, bet)
        balance = round(state["balance"] + profit, 4)
    else:
        stake_pct = stake_pct_for_bet(bet)
        balance, profit, won, leg_count, stake_amount = apply_day(state["balance"], snapshot["bets"])
        balance = round(balance, 4)
        leg_count = len(bet.get("legs", [])) or 1

    state["balance"] = balance
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
    ticket["grade_source"] = source
    ticket["prove_out"] = use_flat

    leg_count = len(bet.get("legs", [])) or 1
    checkpoint = {
        "date": day_iso,
        "profit": round(profit, 4),
        "balance": balance,
        "return_pct": round((balance - state["starting_balance"]) / state["starting_balance"], 4),
        "won": won,
        "leg_count": leg_count,
        "label": ticket["label"],
        "legs": ticket["legs"],
        "stake_amount": ticket["stake_amount"],
        "grade_source": source,
        "prove_out": use_flat,
    }
    state["checkpoints"].append(checkpoint)
    state.setdefault("tickets", []).append(ticket)
    state["last_settled_date"] = day_iso


def rebuild_state_from_boards(state: dict, snaps_by_day: dict[str, dict], *, through: date) -> None:
    started_at = state["started_at"]
    state["balance"] = state["starting_balance"]
    state["record"] = {"wins": 0, "losses": 0}
    state["checkpoints"] = []
    state["tickets"] = []
    state["last_settled_date"] = None

    cursor = date.fromisoformat(started_at)
    while cursor <= through:
        day_iso = cursor.isoformat()
        snapshot, source = graded_snapshot_for_day(day_iso, snaps_by_day)
        if snapshot and snapshot_is_graded(snapshot):
            settle_day(state, day_iso, snapshot, source=source)
        cursor += timedelta(days=1)


def pending_snapshot_from_live_board(today_iso: str) -> dict | None:
    """Today's ticket from the live predictions board (pre-grade)."""
    board_path = REPO_ROOT / "public" / "predictions.json"
    if not board_path.exists():
        return None
    board = json.loads(board_path.read_text())
    if not any(str(row.get("date", "")).startswith(today_iso) for row in board.get("predictions", [])):
        return None
    ticket = ticket_from_archived_board(board_path)
    if not ticket:
        return None
    return {
        "date": today_iso,
        "bets": [
            {
                "label": ticket["label"],
                "legs": ticket["legs"],
                "won": None,
                "profit": None,
                "odds": ticket.get("odds"),
                "model_probability": ticket.get("model_probability"),
            }
        ],
    }


def main() -> None:
    reset = "--reset" in sys.argv
    rebuild = "--rebuild" in sys.argv
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

    yesterday = today - timedelta(days=1)
    if rebuild:
        rebuild_state_from_boards(state, snaps_by_day, through=yesterday)
    else:
        started_at = state["started_at"]
        last_settled = state.get("last_settled_date")
        cursor = date.fromisoformat(last_settled) + timedelta(days=1) if last_settled else date.fromisoformat(started_at)

        while cursor <= yesterday:
            day_iso = cursor.isoformat()
            if day_iso < started_at:
                cursor += timedelta(days=1)
                continue

            snapshot, source = graded_snapshot_for_day(day_iso, snaps_by_day)
            if snapshot and snapshot_is_graded(snapshot):
                settle_day(state, day_iso, snapshot, source=source)
            cursor += timedelta(days=1)

        # Settle today when every leg is final or void (e.g. rainout + other leg won).
        if state.get("last_settled_date") != today_iso:
            today_board_snapshot, today_source = graded_snapshot_for_day(today_iso, snaps_by_day)
            if today_board_snapshot and snapshot_is_graded(today_board_snapshot):
                settle_day(state, today_iso, today_board_snapshot, source=today_source)

    today_snapshot, _ = graded_snapshot_for_day(today_iso, snaps_by_day)
    if not today_snapshot:
        today_snapshot = pending_snapshot_from_live_board(today_iso)
    if not today_snapshot:
        today_snapshot = snaps_by_day.get(today_iso)
    today_ticket = None
    if today_snapshot and today_snapshot.get("bets"):
        bet = today_snapshot["bets"][0]
        leg_count = len(bet.get("legs", [])) or 1
        tickets_done = len(state.get("tickets", []))
        in_prove_out = LIVE_STAKE_MODE == "flat_5" or tickets_done < PROVE_OUT_TICKETS
        stake_pct = STAKE_TIERED.get(leg_count, 0.35)
        stake_amount = FLAT_PROVE_OUT_USD if in_prove_out else round(state["balance"] * stake_pct, 2)
        today_ticket = {
            "date": today_iso,
            "label": bet.get("label") or bet.get("side") or "system ticket",
            "legs": ticket_legs(bet),
            "leg_count": leg_count,
            "stake_pct": stake_pct if not in_prove_out else round(stake_amount / max(state["balance"], 1.0), 4),
            "stake_amount": stake_amount,
            "status": "graded" if snapshot_is_graded(today_snapshot) else "pending",
            "odds": bet.get("odds"),
            "model_probability": bet.get("model_probability"),
            "prove_out": in_prove_out,
        }

    wins = state["record"]["wins"]
    losses = state["record"]["losses"]
    total = wins + losses
    prove_out_done = min(total, PROVE_OUT_TICKETS)
    output = {
        "generated_at": today_iso,
        "tracking_mode": "live_best_bets",
        "disclaimer": TRACKING_DISCLAIMER,
        "strategy": LIVE_STRATEGY,
        "stakes": STAKE_TIERED,
        "prove_out": {
            "flat_stake_usd": FLAT_PROVE_OUT_USD,
            "target_tickets": PROVE_OUT_TICKETS,
            "completed_tickets": prove_out_done,
            "active": LIVE_STAKE_MODE == "flat_5",
            "mode": LIVE_STAKE_MODE,
        },
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
        "tracking_note": (
            f"{LIVE_STRATEGY} · archived board ticket when available · "
            f"prove-out ${FLAT_PROVE_OUT_USD:.0f} flat × {PROVE_OUT_TICKETS} tickets"
        ),
    }
    save_state(state)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print(f"System replay balance: ${state['balance']:.2f} (started ${state['starting_balance']:.2f} on {state['started_at']})")
    print(f"System ticket record: {wins}-{losses} · tickets logged: {len(state.get('tickets', []))}")


if __name__ == "__main__":
    main()
