"""Archive today's published board and grade completed live picks.

Walk-forward history stopped updating in early August, so the accuracy page
froze. This grades the boards that actually shipped (data/daily-boards) using
MLB finals, merges them into prediction-history.json, then rebuilds accuracy.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from generate_accuracy_output import main as write_accuracy
from mlb_api import fetch_games

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "public"
BOARDS_DIR = ROOT / "data" / "daily-boards"
HISTORY_PATH = PUBLIC / "prediction-history.json"
PREDICTIONS_PATH = PUBLIC / "predictions.json"

TEAM_ABBR = {
    "ari": "ARI",
    "ath": "ATH",
    "atl": "ATL",
    "bal": "BAL",
    "bos": "BOS",
    "chc": "CHC",
    "cws": "CWS",
    "cin": "CIN",
    "cle": "CLE",
    "col": "COL",
    "det": "DET",
    "hou": "HOU",
    "kc": "KC",
    "laa": "LAA",
    "lad": "LAD",
    "mia": "MIA",
    "mil": "MIL",
    "min": "MIN",
    "nym": "NYM",
    "nyy": "NYY",
    "phi": "PHI",
    "pit": "PIT",
    "sd": "SD",
    "sf": "SF",
    "sea": "SEA",
    "stl": "STL",
    "tb": "TB",
    "tex": "TEX",
    "tor": "TOR",
    "wsh": "WSH",
    "az": "ARI",
}


def abbr(team_id: str) -> str:
    return TEAM_ABBR.get((team_id or "").lower(), (team_id or "").upper())


def game_pk(row: dict) -> int | None:
    raw = row.get("gamePk") or row.get("id")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    if isinstance(raw, str) and "-" in raw:
        tail = raw.rsplit("-", 1)[-1]
        if tail.isdigit():
            return int(tail)
    return None


def archive_current_board() -> None:
    if not PREDICTIONS_PATH.exists():
        return
    payload = json.loads(PREDICTIONS_PATH.read_text())
    day = str(payload.get("generated_at") or "")[:10]
    if not day:
        return
    BOARDS_DIR.mkdir(parents=True, exist_ok=True)
    dest = BOARDS_DIR / f"{day}.json"
    dest.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"archived {dest.name} games={len(payload.get('predictions') or [])}")


def backfill_boards_from_git(limit: int = 400) -> None:
    BOARDS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        log = subprocess.check_output(
            ["git", "log", "--pretty=%H", "-n", str(limit), "--", "public/predictions.json"],
            cwd=ROOT,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"git backfill skipped: {exc}", file=sys.stderr)
        return

    seen: set[str] = set()
    for sha in log.split():
        try:
            blob = subprocess.check_output(
                ["/usr/bin/git", "show", f"{sha}:public/predictions.json"],
                cwd=ROOT,
                text=True,
                stderr=subprocess.DEVNULL,
            )
            payload = json.loads(blob)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        day = str(payload.get("generated_at") or "")[:10]
        if len(day) != 10 or day in seen:
            continue
        seen.add(day)
        dest = BOARDS_DIR / f"{day}.json"
        if dest.exists():
            continue
        dest.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"git backfill {dest.name}")


def grade_board(payload: dict, finals: dict[int, object]) -> list[dict]:
    rows: list[dict] = []
    day = str(payload.get("generated_at") or "")[:10]
    model_version = payload.get("model_version") or "live-board"
    for game in payload.get("predictions") or []:
        pk = game_pk(game)
        if pk is None:
            continue
        final = finals.get(pk)
        if final is None or not getattr(final, "is_final", False):
            continue
        if final.home_score is None or final.away_score is None:
            continue
        home = abbr(game.get("homeTeam") or "")
        away = abbr(game.get("awayTeam") or "")
        predicted = abbr(game.get("predictedTeam") or "")
        actual = home if final.home_won else away
        pick = float(game.get("pickProbability") or game.get("modelHomeWinProbability") or 0.5)
        home_p = float(game.get("modelHomeWinProbability") or 0.5)
        away_p = float(game.get("modelAwayWinProbability") or 0.5)
        ml_home = game.get("homeMoneyline")
        ml_away = game.get("awayMoneyline")
        odds_ok = isinstance(ml_home, (int, float)) and isinstance(ml_away, (int, float)) and ml_home and ml_away
        rows.append(
            {
                "gamePk": pk,
                "date": str(game.get("date") or day),
                "startsAt": game.get("startsAt"),
                "home": home,
                "away": away,
                "internalHomeProbability": round(home_p, 4),
                "internalPickProbability": round(pick, 4),
                "probability": round(home_p, 4),
                "pickProbability": round(pick, 4),
                "rawPickProbability": round(float(game.get("rawPickProbability") or pick), 4),
                "confidence": game.get("confidence") or "Low",
                "eraDiff": float(game.get("eraDiff") or 0.0),
                "formEdge": float(game.get("formEdge") or 0.0),
                "marketAgrees": game.get("marketAgrees"),
                "modelEdge": float(game.get("modelEdge") or 0.0),
                "marketBacked": bool(odds_ok),
                "predicted": predicted,
                "actual": actual,
                "correct": int(predicted == actual),
                "modelVersion": game.get("modelVersion") or model_version,
                "source": "live_board",
            }
        )
    return rows


def main() -> int:
    from_git = "--from-git" in sys.argv
    archive_current_board()
    if from_git:
        backfill_boards_from_git()

    board_files = sorted(BOARDS_DIR.glob("*.json"))
    if not board_files:
        print("no daily boards to grade", file=sys.stderr)
        return 0

    dates = [date.fromisoformat(path.stem) for path in board_files]
    finals = {
        game.game_pk: game
        for game in fetch_games(min(dates), max(dates), final_only=True)
    }
    live_rows: list[dict] = []
    live_dates: set[str] = set()
    for path in board_files:
        payload = json.loads(path.read_text())
        graded = grade_board(payload, finals)
        live_rows.extend(graded)
        live_dates.add(path.stem)
        print(f"graded {path.stem}: {len(graded)} finals")

    history = {"predictions": []}
    if HISTORY_PATH.exists():
        history = json.loads(HISTORY_PATH.read_text())

    kept = [
        row
        for row in history.get("predictions") or []
        if str(row.get("date") or "") not in live_dates
    ]
    merged = kept + live_rows
    merged.sort(key=lambda row: (str(row.get("date") or ""), int(row.get("gamePk") or 0)))
    yesterday = date.today() - timedelta(days=1)
    history["generated_at"] = date.today().isoformat()
    history["trained_through"] = yesterday.isoformat()
    history["method"] = "live published boards graded with MLB finals + preserved walk-forward archive"
    history["history_start"] = history.get("history_start") or (merged[0]["date"] if merged else None)
    history["predictions"] = merged
    HISTORY_PATH.write_text(json.dumps(history, indent=2) + "\n")
    print(f"history rows={len(merged)} live_days={len(live_dates)}")
    write_accuracy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
