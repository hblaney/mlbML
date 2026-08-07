"""Lock the official daily system ticket at first publish.

The live board refreshes hourly (new odds, model retrains, confidence relabels).
Without a lock, what you see at 2 PM can disagree with what was published by 11 AM —
exactly the failure mode where a bet was placed on one card and the site later showed another.

Rules:
  - First *real* lock of the calendar day wins. Never overwrite a ticket that already
    has legs.
  - A morning SKIP (odds missing / no High yet) MAY be upgraded once a qualifying
    High ticket appears later the same day — otherwise the site lies all afternoon.
  - Written to data/locked-tickets/{date}.json (grading) and public/locked-ticket.json (site).
  - Includes each leg's confidence + probability at lock time so labels can't drift retroactively.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_DIR = REPO_ROOT / "data" / "locked-tickets"
PUBLIC_PATH = REPO_ROOT / "public" / "locked-ticket.json"
BOARD_PATH = REPO_ROOT / "public" / "predictions.json"
TICKET_SCRIPT = REPO_ROOT / "scripts" / "model" / "_lock_ticket_from_board.mjs"


def _today() -> str:
    return date.today().isoformat()


def locked_path(day_iso: str) -> Path:
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    return LOCK_DIR / f"{day_iso}.json"


def load_lock(day_iso: str) -> dict | None:
    path = locked_path(day_iso)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def ticket_from_board(board_path: Path) -> dict | None:
    TICKET_SCRIPT.write_text(
        "import { readFileSync } from 'fs';\n"
        "import { getBestDailyTicket } from '../../lib/data.ts';\n"
        "const payload = JSON.parse(readFileSync(process.argv.at(-1), 'utf8'));\n"
        "const board = payload.predictions ?? [];\n"
        "const ticket = getBestDailyTicket(board);\n"
        "if (!ticket) { console.log('null'); process.exit(0); }\n"
        "const legDetail = (bet) => ({\n"
        "  team: bet.team.abbreviation,\n"
        "  matchup: bet.matchup,\n"
        "  confidence: bet.game.confidence,\n"
        "  pickProbability: bet.modelProbability,\n"
        "  edge: bet.edge,\n"
        "  odds: bet.odds,\n"
        "  startsAt: bet.game.startsAt,\n"
        "});\n"
        "if (ticket.kind === 'single') {\n"
        "  const bet = ticket.bet;\n"
        "  console.log(JSON.stringify({\n"
        "    kind: 'single',\n"
        "    label: `${bet.team.abbreviation} ML`,\n"
        "    legs: [bet.team.abbreviation],\n"
        "    leg_count: 1,\n"
        "    odds: bet.odds,\n"
        "    model_probability: ticket.bet.modelProbability,\n"
        "    leg_details: [legDetail(bet)],\n"
        "  }));\n"
        "} else if (ticket.kind === 'multi_single') {\n"
        "  const bets = ticket.bets;\n"
        "  console.log(JSON.stringify({\n"
        "    kind: 'multi_single',\n"
        "    label: bets.map((bet) => `${bet.team.abbreviation} ML`).join(' + '),\n"
        "    legs: bets.map((bet) => bet.team.abbreviation),\n"
        "    leg_count: bets.length,\n"
        "    odds: null,\n"
        "    model_probability: null,\n"
        "    leg_details: bets.map(legDetail),\n"
        "  }));\n"
        "} else {\n"
        "  const legs = ticket.parlay.legs;\n"
        "  console.log(JSON.stringify({\n"
        "    kind: 'parlay',\n"
        "    label: legs.map((leg) => `${leg.team.abbreviation} ML`).join(' + '),\n"
        "    legs: legs.map((leg) => leg.team.abbreviation),\n"
        "    leg_count: legs.length,\n"
        "    odds: ticket.parlay.americanOdds,\n"
        "    model_probability: ticket.parlay.probability,\n"
        "    leg_details: legs.map(legDetail),\n"
        "  }));\n"
        "}\n"
    )
    proc = subprocess.run(
        ["npx", "--yes", "tsx", str(TICKET_SCRIPT), str(board_path)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return None
    raw = proc.stdout.strip()
    if not raw or raw == "null":
        return None
    return json.loads(raw)


def build_lock(day_iso: str, ticket: dict, board: dict, *, source: str) -> dict:
    return {
        "date": day_iso,
        "locked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "board_generated_at": board.get("board_generated_at"),
        "model_version": board.get("model_version"),
        "pipeline_version": board.get("pipeline_version"),
        "source": source,
        "note": "Official daily ticket — frozen at first publish. Later board refreshes do not change this.",
        "ticket": ticket,
    }


def publish(lock: dict) -> None:
    day_iso = lock["date"]
    locked_path(day_iso).write_text(json.dumps(lock, indent=2))
    PUBLIC_PATH.write_text(json.dumps(lock, indent=2))
    t = lock["ticket"]
    print(
        f"locked_ticket_ok date={day_iso} kind={t.get('kind')} "
        f"legs={'+'.join(t.get('legs', []))} locked_at={lock['locked_at']}"
    )


def _is_skip_ticket(ticket: dict | None) -> bool:
    if not ticket:
        return True
    kind = ticket.get("kind")
    legs = ticket.get("legs") or []
    leg_count = int(ticket.get("leg_count") or 0)
    return kind == "skip" or leg_count == 0 or len(legs) == 0


def main() -> None:
    day_iso = _today()
    existing = load_lock(day_iso)
    if existing and not _is_skip_ticket(existing.get("ticket")):
        PUBLIC_PATH.write_text(json.dumps(existing, indent=2))
        t = existing["ticket"]
        print(
            f"locked_ticket_exists date={day_iso} kind={t.get('kind')} "
            f"legs={'+'.join(t.get('legs', []))} — not overwriting"
        )
        return

    if not BOARD_PATH.exists():
        print("locked_ticket_skip: no public/predictions.json", file=sys.stderr)
        sys.exit(0)

    board = json.loads(BOARD_PATH.read_text())
    if board.get("generated_at") != day_iso:
        print(
            f"locked_ticket_skip: board generated_at={board.get('generated_at')} != today {day_iso}",
            file=sys.stderr,
        )
        sys.exit(0)

    ticket = ticket_from_board(BOARD_PATH)
    if not ticket:
        if existing and _is_skip_ticket(existing.get("ticket")):
            PUBLIC_PATH.write_text(json.dumps(existing, indent=2))
            print(f"locked_ticket_exists date={day_iso} kind=skip — still no qualifying ticket")
            return
        print(f"locked_ticket_skip: no qualifying system ticket for {day_iso}")
        # Still write an explicit skip lock so the site knows "official = no bet" for now.
        # Later publishes may upgrade this skip once Highs clear.
        lock = build_lock(
            day_iso,
            {"kind": "skip", "label": "No bet today", "legs": [], "leg_count": 0},
            board,
            source="lock_daily_ticket.py",
        )
        lock["note"] = (
            "Provisional skip — may upgrade to a High ticket later today if odds/gates clear."
        )
        publish(lock)
        return

    if existing and _is_skip_ticket(existing.get("ticket")):
        lock = build_lock(day_iso, ticket, board, source="lock_daily_ticket.py")
        lock["note"] = (
            "Upgraded from morning skip once a qualifying High ticket appeared "
            "(odds/gates were not ready at first publish)."
        )
        lock["upgraded_from_skip"] = True
        lock["previous_locked_at"] = existing.get("locked_at")
        publish(lock)
        return

    publish(build_lock(day_iso, ticket, board, source="lock_daily_ticket.py"))


if __name__ == "__main__":
    main()
