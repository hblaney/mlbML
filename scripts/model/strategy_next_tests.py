"""Next strategy tests — min-edge gates, correlation-aware parlays, selective hybrids (2026 focus)."""

from __future__ import annotations

import itertools
import json
from datetime import date, datetime
from pathlib import Path

from backtest_daily_recommendations import (
    model_pick_candidates,
    pick_best_daily_ticket,
    pick_best_moneyline,
    pick_best_parlay,
)
from backtest_parlays import season_start_for, settle_parlay
from backtest_strategy_optimizer import leg_score_for_parlay, pick_forced_top_legs
from exhaustive_strategy_search import (
    STAKE,
    DayAction,
    action_to_bet,
    day_actions_for_rule,
    flat_stats_for_snapshots,
    load_moneyline_by_day,
    pick_always_n,
    pick_filtered,
)
from strategy_research import compound, filter_candidates

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "public" / "strategy-next-tests.json"
STAKE_TIERED = {1: 0.35, 2: 0.45, 3: 0.10}
CONF_OK = {"Medium", "High", "Elite"}
LIVE_PARLAY_MIN_MODEL_PROBABILITY = 0.68

TEAM_DIVISION = {
    "bal": "AL_E",
    "bos": "AL_E",
    "nyy": "AL_E",
    "tb": "AL_E",
    "tor": "AL_E",
    "cws": "AL_C",
    "cle": "AL_C",
    "det": "AL_C",
    "kc": "AL_C",
    "min": "AL_C",
    "hou": "AL_W",
    "laa": "AL_W",
    "ath": "AL_W",
    "sea": "AL_W",
    "tex": "AL_W",
    "atl": "NL_E",
    "mia": "NL_E",
    "nym": "NL_E",
    "phi": "NL_E",
    "wsh": "NL_E",
    "chc": "NL_C",
    "cin": "NL_C",
    "mil": "NL_C",
    "pit": "NL_C",
    "stl": "NL_C",
    "ari": "NL_W",
    "col": "NL_W",
    "lad": "NL_W",
    "sd": "NL_W",
    "sf": "NL_W",
}


def parse_start_minutes(value: str | None) -> int | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalized).timestamp() // 60)
    except ValueError:
        return None


def enrich_moneyline(ml: dict[str, list[dict]], rows: list[dict]) -> dict[str, list[dict]]:
    by_pk = {row["gamePk"]: row for row in rows}
    enriched: dict[str, list[dict]] = {}
    for day, candidates in ml.items():
        day_rows = []
        for candidate in candidates:
            row = by_pk.get(candidate["gamePk"], {})
            team = str(candidate["team"]).lower()
            item = {
                **candidate,
                "division": TEAM_DIVISION.get(team),
                "startsAt": row.get("startsAt"),
                "start_minutes": parse_start_minutes(row.get("startsAt")),
            }
            day_rows.append(item)
        enriched[day] = day_rows
    return enriched


def parlay_correlation_factor(legs: list[dict], *, reject_same_div: bool, reject_same_time: bool, penalty_div: float, penalty_time: float) -> float | None:
    factor = 1.0
    for left, right in itertools.combinations(legs, 2):
        left_div = left.get("division")
        right_div = right.get("division")
        if left_div and right_div and left_div == right_div:
            if reject_same_div:
                return None
            factor *= 1.0 - penalty_div

        left_min = left.get("start_minutes")
        right_min = right.get("start_minutes")
        if left_min is not None and right_min is not None and abs(left_min - right_min) <= 60:
            if reject_same_time:
                return None
            factor *= 1.0 - penalty_time
    return factor


def pick_corr_parlay(
    candidates: list[dict],
    leg_count: int,
    *,
    reject_same_div: bool = False,
    reject_same_time: bool = False,
    penalty_div: float = 0.0,
    penalty_time: float = 0.0,
) -> dict | None:
    pool = [c for c in model_pick_candidates(candidates) if c["ev"] > 0]
    pool.sort(key=lambda leg: leg["ev"] * leg["model_probability"], reverse=True)
    pool = pool[:8]
    if len(pool) < leg_count:
        return None

    best = None
    for combo in itertools.combinations(pool, leg_count):
        if len({leg["gamePk"] for leg in combo}) != leg_count:
            continue
        legs = list(combo)
        factor = parlay_correlation_factor(
            legs,
            reject_same_div=reject_same_div,
            reject_same_time=reject_same_time,
            penalty_div=penalty_div,
            penalty_time=penalty_time,
        )
        if factor is None:
            continue
        settled = settle_parlay(legs)
        if settled["ev"] <= 0:
            continue
        score = leg_score_for_parlay(legs) * factor
        ticket = {"legs": legs, "score": score, "strategy": f"corr_{leg_count}", **settled}
        if best is None or ticket["score"] > best["score"]:
            best = ticket
    return best


def pick_always_n_corr(candidates: list[dict], leg_count: int, **corr_kwargs) -> dict | None:
    return pick_corr_parlay(candidates, leg_count, **corr_kwargs) or pick_forced_top_legs(candidates, leg_count)


def no_low_pool(candidates: list[dict]) -> list[dict]:
    return [c for c in candidates if c.get("confidence") in CONF_OK]


def live_parlay_pool(candidates: list[dict]) -> list[dict]:
    return [
        c
        for c in no_low_pool(model_pick_candidates(candidates))
        if c["model_probability"] >= LIVE_PARLAY_MIN_MODEL_PROBABILITY
    ]


def pick_two_or_three_or_single_custom(
    candidates: list[dict],
    *,
    pool: list[dict] | None = None,
    p2_ticket: dict | None = None,
    p3_ticket: dict | None = None,
    min_score: float | None = None,
    skip_forced: bool = False,
) -> list[DayAction]:
    from backtest_daily_recommendations import pick_best_moneyline

    base_pool = pool if pool is not None else candidates
    p2 = p2_ticket if p2_ticket is not None else pick_always_n(base_pool, 2)
    p3 = p3_ticket if p3_ticket is not None else pick_filtered(base_pool, 3)
    if skip_forced and p2 and p2.get("strategy", "").startswith("forced_top"):
        p2 = pick_filtered(base_pool, 2)

    single_pick, _ = pick_best_moneyline(candidates)
    opts: list[tuple[float, dict, str, bool]] = []
    if p2:
        opts.append((p2["score"], p2, "p2", False))
    if p3:
        opts.append((p3["score"], p3, "p3", False))
    if single_pick:
        opts.append((single_pick["ev"] * single_pick["model_probability"], single_pick, "single", True))
    if not opts:
        return []

    score, ticket, tag, is_single = max(opts, key=lambda item: item[0])
    if min_score is not None and score < min_score:
        return []
    if is_single:
        return [DayAction(legs=None, single=ticket, label="single")]
    return [DayAction(legs=ticket["legs"], single=None, label=tag)]


def day_actions_for_test(candidates: list[dict], rule: str) -> list[DayAction]:
    if rule == "no_low_parlay_223s":
        return day_actions_for_rule(candidates, rule)

    if rule == "best_ticket":
        return day_actions_for_rule(candidates, rule)

    if rule.startswith("no_low_min_edge"):
        edge = float(rule.replace("no_low_min_edge", "")) / 100.0
        pool = filter_candidates(candidates, min_conf="no_low", min_edge=edge)
        return pick_two_or_three_or_single_custom(candidates, pool=pool)

    if rule.startswith("no_low_min_score"):
        threshold = float(rule.replace("no_low_min_score", "")) / 100.0
        return pick_two_or_three_or_single_custom(no_low_pool(candidates), min_score=threshold)

    if rule == "no_low_best_ticket":
        pool = no_low_pool(candidates)
        ticket, _ = pick_best_daily_ticket(pool)
        if ticket is None:
            return []
        if ticket.get("ticket_kind") == "single":
            return [DayAction(legs=None, single=ticket, label="single")]
        return [DayAction(legs=ticket["legs"], single=None, label="best_ticket")]

    if rule == "no_low_skip_forced":
        return pick_two_or_three_or_single_custom(candidates, pool=no_low_pool(candidates), skip_forced=True)

    if rule == "no_low_selective_best":
        pool = no_low_pool(candidates)
        filtered_2, _ = pick_best_parlay(pool, 2)
        filtered_3, _ = pick_best_parlay(pool, 3)
        single, _ = pick_best_moneyline(candidates)
        opts = []
        if filtered_2:
            opts.append((filtered_2["score"], filtered_2, "f2", False))
        if filtered_3:
            opts.append((filtered_3["score"], filtered_3, "f3", False))
        if single:
            opts.append((single["ev"] * single["model_probability"], single, "single", True))
        if not opts:
            return []
        _, ticket, tag, is_single = max(opts, key=lambda item: item[0])
        if is_single:
            return [DayAction(legs=None, single=ticket, label="single")]
        return [DayAction(legs=ticket["legs"], single=None, label=tag)]

    if rule.startswith("corr_nl_"):
        suffix = rule.replace("corr_nl_", "")
        corr_kwargs: dict = {}
        if suffix == "reject_div":
            corr_kwargs = {"reject_same_div": True}
        elif suffix == "reject_time":
            corr_kwargs = {"reject_same_time": True}
        elif suffix == "reject_both":
            corr_kwargs = {"reject_same_div": True, "reject_same_time": True}
        elif suffix == "penalize_div15":
            corr_kwargs = {"penalty_div": 0.15}
        elif suffix == "penalize_time10":
            corr_kwargs = {"penalty_time": 0.10}
        elif suffix == "penalize_both":
            corr_kwargs = {"penalty_div": 0.15, "penalty_time": 0.10}
        else:
            raise ValueError(rule)
        live_candidates = model_pick_candidates(candidates)
        pool = live_parlay_pool(live_candidates)
        p2 = pick_always_n_corr(pool, 2, **corr_kwargs)
        p3 = pick_corr_parlay(pool, 3, **corr_kwargs)
        return pick_two_or_three_or_single_custom(live_candidates, pool=pool, p2_ticket=p2, p3_ticket=p3)

    raise ValueError(rule)


def build_snapshots(ml: dict[str, list[dict]], rule: str) -> list[dict]:
    snaps = []
    for day in sorted(ml):
        actions = day_actions_for_test(ml[day], rule)
        if not actions:
            continue
        snaps.append({"date": day, "bets": [action_to_bet(a, day) for a in actions]})
    return snaps


def summarize(rule: str, snaps: list[dict], start: float = 100.0) -> dict:
    stats = compound(snaps, start, STAKE_TIERED)
    return {
        "strategy": rule,
        "bet_days": stats["days"],
        "skip_days": None,
        **stats,
    }


def run_suite_2026(ml: dict[str, list[dict]], total_days: int) -> dict:
    baseline_rule = "no_low_parlay_223s"
    baseline_snaps = build_snapshots(ml, baseline_rule)
    baseline = summarize(baseline_rule, baseline_snaps)

    suites: dict[str, dict] = {
        "baseline": baseline,
        "min_edge_gates": [],
        "correlation_parlays": [],
        "selective_hybrids": [],
    }

    for edge_pct in (5, 6, 7, 8, 9, 10, 12):
        rule = f"no_low_min_edge{edge_pct}"
        snaps = build_snapshots(ml, rule)
        row = summarize(rule, snaps)
        row["skip_days"] = total_days - row["bet_days"]
        row["vs_baseline_flat_roi"] = round(row["flat_roi"] - baseline["flat_roi"], 4)
        suites["min_edge_gates"].append(row)

    corr_rules = [
        "corr_nl_reject_div",
        "corr_nl_reject_time",
        "corr_nl_reject_both",
        "corr_nl_penalize_div15",
        "corr_nl_penalize_time10",
        "corr_nl_penalize_both",
    ]
    for rule in corr_rules:
        snaps = build_snapshots(ml, rule)
        row = summarize(rule, snaps)
        row["skip_days"] = total_days - row["bet_days"]
        row["vs_baseline_flat_roi"] = round(row["flat_roi"] - baseline["flat_roi"], 4)
        suites["correlation_parlays"].append(row)

    selective_rules = [
        "best_ticket",
        "no_low_best_ticket",
        "no_low_skip_forced",
        "no_low_selective_best",
        "no_low_min_score025",
        "no_low_min_score050",
        "no_low_min_score075",
        "no_low_min_score100",
    ]
    for rule in selective_rules:
        snaps = build_snapshots(ml, rule)
        row = summarize(rule, snaps)
        row["skip_days"] = total_days - row["bet_days"]
        row["vs_baseline_flat_roi"] = round(row["flat_roi"] - baseline["flat_roi"], 4)
        suites["selective_hybrids"].append(row)

    def rank(rows: list[dict]) -> list[dict]:
        return sorted(rows, key=lambda row: (row["flat_roi"], row["end"]), reverse=True)

    suites["min_edge_gates"] = rank(suites["min_edge_gates"])
    suites["correlation_parlays"] = rank(suites["correlation_parlays"])
    suites["selective_hybrids"] = rank(suites["selective_hybrids"])

    winners = {
        "min_edge_gates": suites["min_edge_gates"][0] if suites["min_edge_gates"] else None,
        "correlation_parlays": suites["correlation_parlays"][0] if suites["correlation_parlays"] else None,
        "selective_hybrids": suites["selective_hybrids"][0] if suites["selective_hybrids"] else None,
    }

    beats_baseline = [
        row
        for group in (suites["min_edge_gates"], suites["correlation_parlays"], suites["selective_hybrids"])
        for row in group
        if row["flat_roi"] > baseline["flat_roi"] and row["bet_days"] >= baseline["bet_days"] - 5
    ]
    beats_baseline.sort(key=lambda row: (row["flat_roi"], row["end"]), reverse=True)

    return {
        "baseline": baseline,
        "suites": suites,
        "suite_winners": winners,
        "beats_baseline_on_2026": beats_baseline[:10],
        "verdicts": build_verdicts(baseline, suites),
    }


def build_verdicts(baseline: dict, suites: dict) -> dict:
    best_edge = suites["min_edge_gates"][0]
    best_corr = suites["correlation_parlays"][0]
    best_sel = suites["selective_hybrids"][0]

    def verdict(winner: dict, label: str) -> str:
        if winner["flat_roi"] > baseline["flat_roi"] + 0.005:
            return f"{label}: {winner['strategy']} improves 2026 flat ROI to {winner['flat_roi']:.1%} ({winner['record']}, {winner['bet_days']} bet days)."
        if winner["flat_roi"] >= baseline["flat_roi"] - 0.005 and winner["end"] > baseline["end"]:
            return f"{label}: {winner['strategy']} ties flat ROI but compounds higher on 2026."
        return f"{label}: nothing beat baseline {baseline['strategy']} on 2026 flat ROI; best variant was {winner['strategy']} at {winner['flat_roi']:.1%}."

    return {
        "min_edge_gates": verdict(best_edge, "Min-edge + no-Low"),
        "correlation_parlays": verdict(best_corr, "Correlation-aware parlays"),
        "selective_hybrids": verdict(best_sel, "Selective skip hybrids"),
    }


def main() -> None:
    start = date(2026, 3, 20)
    end = date(2026, 6, 16)
    prior = (season_start_for(2025), date(2025, 8, 17))
    ml, meta = load_moneyline_by_day(start, end, prior[0], prior[1])
    ml = {day: cands for day, cands in ml.items() if date.fromisoformat(day) <= end}

    from daily_auto_model import walk_forward_history
    from mlb_api import load_or_fetch_games, load_team_abbreviations

    rows = walk_forward_history(load_or_fetch_games(start, end), load_team_abbreviations(), prior_games=load_or_fetch_games(*prior))
    ml = enrich_moneyline(ml, rows)
    total_days = len(ml)

    results = run_suite_2026(ml, total_days)
    output = {
        "generated_at": date.today().isoformat(),
        "method": "strategy_next_tests_2026",
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "game_days_with_odds": total_days,
        "stakes": STAKE_TIERED,
        "starting_bankrolls_reported": [100.0, 0.13],
        **results,
    }

    # add micro bankroll for continuity
    for group_name in ("min_edge_gates", "correlation_parlays", "selective_hybrids"):
        for row in output["suites"][group_name]:
            snaps = build_snapshots(ml, row["strategy"])
            row["end_13c"] = compound(snaps, 0.13, STAKE_TIERED)["end"]

    output["baseline"]["end_13c"] = compound(build_snapshots(ml, "no_low_parlay_223s"), 0.13, STAKE_TIERED)["end"]

    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    base = output["baseline"]
    print(f"2026 baseline {base['strategy']}: flat {base['flat_roi']:.1%} | $100 -> ${base['end']:,.2f} | {base['record']} | {base['bet_days']} bet days\n")

    for title, key in [
        ("MIN-EDGE + NO-LOW", "min_edge_gates"),
        ("CORRELATION-AWARE PARLAYS", "correlation_parlays"),
        ("SELECTIVE SKIP HYBRIDS", "selective_hybrids"),
    ]:
        print(title)
        for row in output["suites"][key][:6]:
            print(
                f"  {row['strategy']:<26} flat {row['flat_roi']:>6.1%}  $100=${row['end']:>12,.0f}  "
                f"{row['record']}  days={row['bet_days']} skip={row['skip_days']}  dROI={row['vs_baseline_flat_roi']:+.1%}"
            )
        print(f"  -> {output['verdicts'][key]}\n")


if __name__ == "__main__":
    main()
