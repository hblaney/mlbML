"""Safety-critical checks — live predictions must match the single unified pipeline."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_PATH = ROOT / "public" / "predictions.json"
ACCURACY_PATH = ROOT / "public" / "accuracy.json"
TICKET_SCRIPT = ROOT / "scripts" / "model" / "_integrity_ticket.mjs"

FORBIDDEN_EXPLANATION_FRAGMENTS = (
    "probability nudged toward",
    "probability shifted",
    "not market-blended or heuristic-adjusted",
    "internal scale",
    "confidence capped",
)

TOLERANCE = 0.001 if os.environ.get("GITHUB_ACTIONS") == "true" else 0.0002


def _code_model_versions() -> tuple[str, str]:
    from daily_auto_model import MODEL_VERSION, PIPELINE_VERSION

    return MODEL_VERSION, PIPELINE_VERSION


def validate_board_schema(payload: dict) -> list[str]:
    errors: list[str] = []
    predictions = payload.get("predictions", [])
    if not predictions:
        errors.append("predictions: empty board")
        return errors

    for row in predictions:
        gid = row.get("id", "?")
        home = float(row.get("modelHomeWinProbability", 0))
        away = float(row.get("modelAwayWinProbability", 0))
        if abs(home + away - 1.0) > TOLERANCE:
            errors.append(f"{gid}: probabilities don't sum to 1 ({home + away:.6f})")
        text = " ".join(row.get("explanation") or []).lower()
        for frag in FORBIDDEN_EXPLANATION_FRAGMENTS:
            if frag in text:
                errors.append(f"{gid}: forbidden legacy text {frag!r}")
    return errors


def _market_probs_from_row(row: dict) -> tuple[float, float] | None:
    from odds_provider import implied_probability

    home_ml = row.get("homeMoneyline")
    away_ml = row.get("awayMoneyline")
    if home_ml is None or away_ml is None:
        return None
    if abs(int(home_ml)) > 1500 or abs(int(away_ml)) > 1500:
        return None  # corrupted odds data — treat as no market
    hi = implied_probability(int(home_ml))
    ai = implied_probability(int(away_ml))
    total = hi + ai
    if total <= 0:
        return None
    return hi / total, ai / total


def recompute_and_verify_board(payload: dict | None = None) -> list[str]:
    from daily_auto_model import ensure_trained_through
    from mlb_api import fetch_upcoming_games, load_team_abbreviations
    from trained_edge_model import final_public_probabilities

    errors: list[str] = []
    if payload is None:
        payload = json.loads(PUBLIC_PATH.read_text())

    today = date.today()
    yesterday = today - timedelta(days=1)
    bundle, _ = ensure_trained_through(yesterday)
    games = {g.game_pk: g for g in fetch_upcoming_games(today, today)}
    abbr = load_team_abbreviations()

    for row in payload.get("predictions", []):
        gid = row.get("id", "?")
        try:
            game_pk = int(str(gid).rsplit("-", 1)[-1])
        except ValueError:
            errors.append(f"{gid}: cannot parse game_pk from id")
            continue
        game = games.get(game_pk)
        if game is None:
            continue

        pred = bundle.predict(game)
        market = _market_probs_from_row(row)
        # Use all stored parameters so integrity check matches board generator exactly
        result = final_public_probabilities(
            pred,
            market_home=market[0] if market else None,
            market_away=market[1] if market else None,
            era_diff=float(row.get("eraDiff", 0.0)),
            form_edge=float(row.get("formEdge", 0.0)),
            starter_certain=bool(row.get("starterCertain", True)),
        )
        hp, ap, pick, conf = (
            result.home_probability,
            result.away_probability,
            result.pick_probability,
            result.confidence,
        )
        stored_pick = float(row.get("pickProbability", 0))
        stored_home = float(row.get("modelHomeWinProbability", 0))
        stored_conf = row.get("confidence")
        stored_team = str(row.get("predictedTeam", "")).lower()
        expected_team = abbr.get(game.home_team_id if hp >= ap else game.away_team_id, "").lower()

        if abs(stored_pick - pick) > TOLERANCE:
            errors.append(f"{gid}: pick recompute {pick:.4f} != stored {stored_pick:.4f}")
        if abs(stored_home - hp) > TOLERANCE:
            errors.append(f"{gid}: home recompute {hp:.4f} != stored {stored_home:.4f}")
        if stored_conf != conf:
            errors.append(f"{gid}: confidence recompute {conf!r} != stored {stored_conf!r}")
        if stored_team != expected_team:
            errors.append(f"{gid}: predictedTeam {stored_team!r} != recompute {expected_team!r}")

    return errors


def verify_best_bets_ticket(payload: dict | None = None) -> list[str]:
    errors: list[str] = []
    if payload is None:
        payload = json.loads(PUBLIC_PATH.read_text())

    if not TICKET_SCRIPT.exists():
        errors.append("missing _integrity_ticket.mjs")
        return errors

    temp = ROOT / "data" / "_integrity_board.json"
    temp.write_text(json.dumps(payload))
    proc = subprocess.run(
        ["npx", "--yes", "tsx", str(TICKET_SCRIPT), str(temp)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    if proc.returncode != 0:
        errors.append(f"best_bets_ticket: tsx failed: {proc.stderr.strip()[:200]}")
        return errors

    raw = proc.stdout.strip()
    if not raw or raw == "null":
        return errors

    ticket = json.loads(raw)
    by_team: dict[str, dict] = {}
    for row in payload.get("predictions", []):
        by_team[str(row.get("predictedTeam", "")).lower()] = row

    for leg, conf in zip(ticket.get("legs", []), ticket.get("confidences", [])):
        row = by_team.get(str(leg).lower())
        if not row:
            errors.append(f"best_bets_ticket: leg {leg} not on board")
            continue
        if row.get("confidence") == "Low":
            errors.append(f"best_bets_ticket: Low-confidence leg {leg} on ticket")
        if conf != row.get("confidence"):
            errors.append(f"best_bets_ticket: ticket confidence {conf!r} != board {row.get('confidence')!r} for {leg}")
    return errors


def verify_accuracy_sync(payload: dict | None = None) -> list[str]:
    errors: list[str] = []
    if payload is None:
        payload = json.loads(PUBLIC_PATH.read_text())
    if not ACCURACY_PATH.exists():
        return errors
    acc = json.loads(ACCURACY_PATH.read_text())
    board_trained = payload.get("trained_through")
    acc_trained = acc.get("trained_through")
    if board_trained and acc_trained and board_trained < acc_trained:
        errors.append(
            f"trained_through: board {board_trained} is behind accuracy audit {acc_trained}"
        )
    return errors


def run_all(*, recompute: bool = True, ticket: bool = True, accuracy: bool = True) -> list[str]:
    payload = json.loads(PUBLIC_PATH.read_text())
    errors: list[str] = []
    errors.extend(validate_board_schema(payload))
    if recompute:
        errors.extend(recompute_and_verify_board(payload))
    if ticket:
        errors.extend(verify_best_bets_ticket(payload))
    if accuracy:
        errors.extend(verify_accuracy_sync(payload))
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="ticket + accuracy checks (recompute on CI only with --strict-recompute)")
    parser.add_argument("--strict-recompute", action="store_true", help="recompute every pick (run after generate_today_board)")
    parser.add_argument("--no-recompute", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not PUBLIC_PATH.exists():
        print(f"missing {PUBLIC_PATH}")
        sys.exit(1)

    payload = json.loads(PUBLIC_PATH.read_text())
    board_model = payload.get("model_version", "unknown")
    board_pipeline = payload.get("pipeline_version", "unknown")

    if args.verbose:
        if args.full or args.strict_recompute:
            code_model, code_pipeline = _code_model_versions()
            print(f"board_model={board_model!r} code_model={code_model!r}")
            print(f"board_pipeline={board_pipeline!r} code_pipeline={code_pipeline!r}")
        else:
            print(f"board_model={board_model!r} (schema-only; skipping ML import)")

    recompute = args.strict_recompute and not args.no_recompute

    if args.full:
        errors = run_all(recompute=recompute, ticket=True, accuracy=True)
    else:
        errors = validate_board_schema(payload)

    if errors:
        print("PREDICTION INTEGRITY FAILED")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    games = len(payload.get("predictions", []))
    print(
        f"prediction_integrity_ok games={games} model={board_model} pipeline={board_pipeline}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("PREDICTION INTEGRITY CRASHED")
        traceback.print_exc()
        sys.exit(1)
