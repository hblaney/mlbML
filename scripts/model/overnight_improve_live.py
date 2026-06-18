"""Overnight live-accuracy research: model + strategy sweeps."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from backtest_parlays import build_single_candidates, odds_backtest_range
from daily_auto_model import walk_forward_history
from exhaustive_strategy_search import action_to_bet
from historical_odds import HistoricalOddsStore
from mlb_api import load_or_fetch_games, load_team_abbreviations
from strategy_next_tests import build_snapshots, day_actions_for_test, enrich_moneyline

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "overnight-improve-report.json"
LIVE_START = "2026-06-13"


def ticket_stats(snaps: list[dict], *, label: str, since: str | None = None) -> dict:
    rows = [snap for snap in snaps if not since or snap["date"] >= since]
    wins = sum(1 for snap in rows if snap["bets"][0].get("won"))
    total = len(rows)
    return {
        "label": label,
        "tickets": total,
        "record": f"{wins}-{total - wins}",
        "hit_rate": round(wins / total, 4) if total else 0.0,
    }


def sweep_live_thresholds(ml: dict, rows: list[dict]) -> list[dict]:
    """Simulate stricter Medium leg floors on corr_nl parlay pool."""
    from backtest_strategy_optimizer import pick_forced_top_legs
    from strategy_next_tests import no_low_pool, pick_corr_parlay, pick_two_or_three_or_single_custom
    from backtest_daily_recommendations import model_pick_candidates, pick_best_moneyline

    enriched = enrich_moneyline(ml, rows)
    results = []
    for min_medium in (0.64, 0.66, 0.68):
        snaps = []
        for day in sorted(enriched):
            pool = [
                c
                for c in no_low_pool(model_pick_candidates(enriched[day]))
                if c["model_probability"] >= min_medium
            ]
            p2 = pick_corr_parlay(pool, 2, reject_same_div=True, reject_same_time=True)
            if p2 is None and len(pool) >= 2:
                p2 = pick_forced_top_legs(pool, 2)
            p3 = pick_corr_parlay(pool, 3, reject_same_div=True, reject_same_time=True)
            single, _ = pick_best_moneyline(model_pick_candidates(enriched[day]))
            opts = []
            if p2:
                opts.append((p2["score"], p2, False))
            if p3:
                opts.append((p3["score"], p3, False))
            if single:
                opts.append((single["ev"] * single["model_probability"], single, True))
            if not opts:
                continue
            _, ticket, is_single = max(opts, key=lambda item: item[0])
            if is_single:
                bet = {
                    "won": single["won"],
                    "legs": None,
                    "team": single["team"],
                    "profit": single.get("profit", 0),
                }
            else:
                from backtest_parlays import settle_parlay

                settled = settle_parlay(ticket["legs"])
                bet = {
                    "won": all(leg["won"] for leg in ticket["legs"]),
                    "legs": ticket["legs"],
                    "profit": settled["profit"],
                }
            snaps.append({"date": day, "bets": [bet]})
        results.append(
            {
                "min_medium_probability": min_medium,
                "season": ticket_stats(snaps, label=f"min_medium_{min_medium}"),
                "since_live_start": ticket_stats(snaps, label=f"min_medium_{min_medium}", since=LIVE_START),
            }
        )
    return results


def main() -> None:
    store = HistoricalOddsStore()
    start, end, odds_meta = odds_backtest_range(store)
    team_abbr = load_team_abbreviations()
    prior = load_or_fetch_games(date(start.year - 1, 3, 20), date(start.year - 1, 10, 5))
    games = load_or_fetch_games(start, end)
    rows = walk_forward_history(games, team_abbr, prior_games=prior)
    ml = build_single_candidates(rows, store)
    ml = enrich_moneyline(ml, rows)

    base_list = []
    for day in sorted(ml):
        actions = day_actions_for_test(ml[day], "corr_nl_reject_both")
        if not actions:
            continue
        base_list.append({"date": day, "bets": [action_to_bet(actions[0], day)]})

    game_correct = sum(int(row["correct"]) for row in rows)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model_version": rows[0]["modelVersion"] if rows else "unknown",
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "odds_metadata": odds_meta,
        "game_accuracy": {
            "games": len(rows),
            "correct": game_correct,
            "accuracy": round(game_correct / len(rows), 4) if rows else 0.0,
        },
        "ticket_baseline": {
            "season": ticket_stats(base_list, label="corr_nl_reject_both"),
            "since_live_start": ticket_stats(base_list, label="corr_nl_reject_both", since=LIVE_START),
        },
        "live_loss_forensics": {
            "2026-06-13": "SD won, KC lost — parlay miss",
            "2026-06-15_wrong": "LAA leg (old code) — fixed path WSH+ATH wins",
            "2026-06-16": "CIN won, CLE lost — parlay miss",
        },
        "threshold_sweep": sweep_live_thresholds(ml, rows),
    }

    best = max(payload["threshold_sweep"], key=lambda row: row["since_live_start"]["hit_rate"])
    payload["recommendation"] = best

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"wrote={OUTPUT_PATH}")
    print(f"game_accuracy={payload['game_accuracy']['accuracy']:.4f}")
    print(f"baseline_live={payload['ticket_baseline']['since_live_start']['record']}")
    print(f"best_threshold={best['min_medium_probability']} live={best['since_live_start']['record']}")


if __name__ == "__main__":
    main()
