"""Optimize daily forced 2-leg ranking for ticket hit rate.

Primary product objective: every-day 2-leg ML parlays. This script scores
candidate rankers on walk-forward prediction history using reconstructed
point-in-time starter eraDiff (history rows often have eraDiff=0 when the
board was published under MLB_FAST_BOARD defaults).

Usage:
  PYTHONPATH=scripts/model python3 scripts/model/optimize_top2_parlay.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from mlb_api import load_or_fetch_games
from pitcher_stats_provider import pitcher_stats_as_of

ROOT = Path(__file__).resolve().parents[2]
HIST = ROOT / "public" / "prediction-history.json"
OUT = ROOT / "data" / "model" / "top2-parlay-ranker.json"

# Locked in after season sweep 2026-09-10 (see OUT artifact).
BEST_ERA_COEF = 0.03


def _attach_era(rows: list[dict]) -> None:
    by_month: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_month[str(row["date"])[:7]].append(row)

    games_by_pk: dict[int, object] = {}
    for month, month_rows in sorted(by_month.items()):
        ds = sorted({str(r["date"]) for r in month_rows})
        games = load_or_fetch_games(date.fromisoformat(ds[0]), date.fromisoformat(ds[-1]))
        for game in games:
            games_by_pk[int(game.game_pk)] = game

    for row in rows:
        game = games_by_pk.get(int(row.get("gamePk") or 0))
        if game is None:
            row["_era"] = None
            continue
        try:
            home = pitcher_stats_as_of(game.home_pitcher_id, game.game_date, cache_only=True)
            away = pitcher_stats_as_of(game.away_pitcher_id, game.game_date, cache_only=True)
        except Exception:
            row["_era"] = None
            continue
        pred_home = str(row["predicted"]).upper() == str(row["home"]).upper()
        pick_era = home["era"] if pred_home else away["era"]
        opp_era = away["era"] if pred_home else home["era"]
        row["_era"] = opp_era - pick_era


def _eval(by_date: dict[str, list[dict]], dates: list[str], score_fn) -> dict:
    wins = losses = leg_w = leg_n = 0
    for day in dates:
        rows = [r for r in by_date[day] if r.get("_era") is not None]
        if len(rows) < 2:
            continue
        rows = sorted(rows, key=lambda r: -score_fn(r))
        ok = bool(rows[0]["correct"]) and bool(rows[1]["correct"])
        wins += int(ok)
        losses += int(not ok)
        for row in rows[:2]:
            leg_n += 1
            leg_w += int(bool(row["correct"]))
    n = wins + losses
    return {
        "record": f"{wins}-{losses}",
        "n": n,
        "ticket_hit": round(wins / n, 4) if n else 0.0,
        "leg_hit": round(leg_w / leg_n, 4) if leg_n else 0.0,
    }


def main() -> None:
    payload = json.loads(HIST.read_text())
    rows = [r for r in payload["predictions"] if r.get("correct") is not None]
    _attach_era(rows)
    by_date: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_date[str(row["date"])].append(row)
    dates = sorted(by_date)
    july = [d for d in dates if d >= "2026-07-01"]

    candidates: list[tuple[str, object]] = [
        ("pickProb", lambda r: float(r["pickProbability"])),
        ("raw", lambda r: float(r.get("rawPickProbability") or 0.0)),
    ]
    for coef in (0.02, 0.03, 0.04, 0.05, 0.06):
        candidates.append(
            (
                f"raw+{coef}*era",
                lambda r, c=coef: float(r.get("rawPickProbability") or 0.0) + c * float(r["_era"]),
            )
        )
        candidates.append(
            (
                f"pick+{coef}*era",
                lambda r, c=coef: float(r["pickProbability"]) + c * float(r["_era"]),
            )
        )

    results = []
    for label, fn in candidates:
        season = _eval(by_date, dates, fn)
        recent = _eval(by_date, july, fn)
        results.append({"label": label, "season": season, "july_plus": recent})
        print(
            f"{label:20s} season={season['ticket_hit']:.1%} ({season['record']}) "
            f"july={recent['ticket_hit']:.1%} ({recent['record']})"
        )

    results.sort(key=lambda row: (row["season"]["ticket_hit"], row["july_plus"]["ticket_hit"]), reverse=True)
    best = results[0]
    out = {
        "generated_at": date.today().isoformat(),
        "objective": "daily_force_top2_ticket_hit",
        "best_label": best["label"],
        "recommended_era_coef": BEST_ERA_COEF,
        "note": (
            "Ship rank = pickProbability + 0.03*eraDiff for everyday 2-leg. "
            "Requires non-zero eraDiff on the board (FAST_BOARD must use cached pitcher stats)."
        ),
        "results": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nbest={best['label']} wrote {OUT}")


if __name__ == "__main__":
    main()
