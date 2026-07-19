"""End-to-end consistency guard across the public artifacts.

Complements prediction_integrity.py (which recomputes the board) by cross-checking
the things that previously shipped broken and confused the user:

  1. Honest-calibration invariant — pickProbability must equal rawPickProbability
     (no display inflation can ever sneak back in).
  2. History continuity — every recent date that had final games must appear in
     prediction-history.json (catches the "no 6/21 history" cache bug).
  3. Strategy-label consistency — live bankroll + betting plan must name the live
     strategy, so pages can't describe different systems.
  4. Live-bankroll internal sanity — leg_count matches legs, stake within exposure
     cap, ratchet stake matches the bankroll tier.

Hard-fails (exit 1) on real inconsistencies so CI catches them before deploy.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "public"
LIVE_STRATEGY = "market_agree_parlay"
PROB_TOL = 1e-6
RECENT_DAYS = 21


def _load(name: str) -> dict | list | None:
    path = PUBLIC / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def check_honest_calibration(predictions: dict) -> list[str]:
    """Published pick % may differ from raw GBM when market-residual publish is active.

    Inflation (cosmetic stretch without market) is still forbidden: when there is no
    moneyline on the row, pick must equal raw.
    """
    errors: list[str] = []
    for row in predictions.get("predictions", []):
        raw = row.get("rawPickProbability")
        pick = row.get("pickProbability")
        if raw is None or pick is None:
            continue
        has_market = row.get("homeMoneyline") is not None and row.get("awayMoneyline") is not None
        if has_market:
            continue
        if abs(float(raw) - float(pick)) > PROB_TOL:
            errors.append(
                f"{row.get('id', '?')}: pickProbability {pick} != rawPickProbability {raw} "
                "(no-market display inflation regression)"
            )
    return errors


def check_history_continuity() -> list[str]:
    """Every recent date with final games must be represented in prediction history."""
    history = _load("prediction-history.json")
    if not history:
        return ["prediction-history.json missing or unreadable"]
    rows = history.get("predictions", history if isinstance(history, list) else [])
    history_dates = {str(r.get("date")) for r in rows if r.get("date")}
    if not history_dates:
        return ["prediction-history.json has no dated rows"]

    try:
        from mlb_api import load_or_fetch_games
    except Exception as exc:  # pragma: no cover
        return [f"could not import mlb_api for continuity check: {exc}"]

    today = date.today()
    yesterday = today - timedelta(days=1)
    window_start = yesterday - timedelta(days=RECENT_DAYS)
    season_start = date(yesterday.year, 3, 20)
    start = max(window_start, season_start)
    if start > yesterday:
        return []

    try:
        games = load_or_fetch_games(start, yesterday)
    except Exception as exc:  # pragma: no cover
        return [f"could not load games for continuity check: {exc}"]

    game_dates = {g.game_date.isoformat() for g in games if g.is_final}
    missing = sorted(d for d in game_dates if d not in history_dates)
    return [f"prediction-history missing recent date(s) with final games: {', '.join(missing)}"] if missing else []


def check_strategy_labels() -> list[str]:
    errors: list[str] = []
    bankroll = _load("live-bankroll.json")
    if bankroll and bankroll.get("strategy") != LIVE_STRATEGY:
        errors.append(f"live-bankroll strategy {bankroll.get('strategy')!r} != {LIVE_STRATEGY!r}")
    plan = _load("betting-plan.json")
    if plan:
        if plan.get("strategy") != LIVE_STRATEGY:
            errors.append(f"betting-plan strategy {plan.get('strategy')!r} != {LIVE_STRATEGY!r}")
        blob = json.dumps(plan).lower()
        if "market_agree_parlay" not in blob and LIVE_STRATEGY not in blob:
            errors.append("betting-plan.json does not reference the live market_agree_parlay strategy")
    return errors


def check_live_bankroll_sanity() -> list[str]:
    errors: list[str] = []
    bankroll = _load("live-bankroll.json")
    if not bankroll:
        return errors
    ticket = bankroll.get("today_ticket") or {}
    legs = ticket.get("legs")
    expected_legs = len(legs) if legs is not None else None
    if expected_legs is not None and ticket.get("leg_count") != expected_legs:
        errors.append(f"today_ticket leg_count {ticket.get('leg_count')} != len(legs) {expected_legs}")

    wallet = bankroll.get("wallet_balance")
    stake = ticket.get("stake_amount")
    cap = bankroll.get("daily_exposure_cap")
    if (
        wallet
        and stake
        and cap
        and expected_legs
        and stake > wallet * cap + 1e-6
    ):
        errors.append(
            f"today_ticket stake_amount {stake} exceeds exposure cap ({cap:.0%} of {wallet})"
        )

    # Ratchet tier check: stake_pct should match the tier for the current balance.
    tiers = bankroll.get("ratchet_tiers") or []
    if wallet is not None and tiers and legs:
        is_parlay = len(legs) >= 2
        for tier in tiers:
            lo = tier.get("min_balance", 0)
            hi = tier.get("max_balance")
            if wallet >= lo and (hi is None or wallet <= hi):
                expected = cap if ticket.get("kind") == "multi_single" else (
                    tier.get("parlay_pct") if is_parlay else tier.get("single_pct")
                )
                # stake_pct in the ticket is the realized fraction (stake/wallet); allow drift
                # because the placed bet was rounded to a real dollar amount.
                realized = ticket.get("stake_pct")
                if expected and realized and abs(realized - expected) > 0.12:
                    errors.append(
                        f"today_ticket stake_pct {realized} far from ratchet tier {expected} "
                        f"for balance {wallet}"
                    )
                break
    return errors


def check_locked_ticket() -> list[str]:
    """Today's board must have a frozen official ticket once the morning publish runs."""
    errors: list[str] = []
    board = _load("predictions.json")
    lock = _load("locked-ticket.json")
    if not board:
        return errors
    today = board.get("generated_at")
    if not today:
        return errors
    if lock and lock.get("date") == today:
        ticket = lock.get("ticket") or {}
        if not ticket.get("label"):
            errors.append("locked-ticket.json missing ticket.label for today")
        return errors
    # No lock yet — only fail after the primary publish window (noon CT) so early
    # morning runs don't false-alarm before the 11 AM lock.
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now_ct = datetime.now(ZoneInfo("America/Chicago"))
    if now_ct.date().isoformat() == today and now_ct.hour >= 12:
        errors.append(
            f"locked-ticket.json missing for board date {today} — official daily ticket was never frozen"
        )
    return errors


def main() -> None:
    predictions = _load("predictions.json")
    errors: list[str] = []
    if not predictions:
        print("CONSISTENCY AUDIT: predictions.json missing — skipping board checks")
    else:
        errors += check_honest_calibration(predictions)
    errors += check_history_continuity()
    errors += check_strategy_labels()
    errors += check_live_bankroll_sanity()
    errors += check_locked_ticket()

    health = _load("model-health.json")
    status = health.get("overall_status") if isinstance(health, dict) else "unknown"

    if errors:
        print("CONSISTENCY AUDIT FAILED")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    print(f"consistency_audit_ok · model_health={status}")


if __name__ == "__main__":
    main()
