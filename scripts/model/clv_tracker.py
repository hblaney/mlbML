"""Closing Line Value (CLV) tracker — the metric that proves a real edge.

CLV measures whether the price we picked beats the market's CLOSING price. If our
picked side's line consistently shortens (moves toward us) by first pitch, the
sharp money is agreeing with us after we're already in — that's the signature of a
genuine edge, independent of whether any single bet won or lost. Pros treat
positive CLV as the single most reliable sign a model is beating the market.

Entry price proxy: our live board is built from odds pulled in the morning, so we
use each game's OPENING moneyline as the entry and the CLOSING moneyline as the
close. CLV (in probability points) for our picked side =
    closing_implied(pick) - opening_implied(pick)
Positive = the market moved toward our pick after we'd have bet it = we beat close.

Source: data/historical_odds.jsonl (opening + closing lines, 2021-2026).
Output: public/clv.json (overall + by-confidence summary and recent rows).
"""

from __future__ import annotations

import json
from pathlib import Path

from historical_odds import TEAM_ALIASES
from odds_provider import implied_probability

ROOT = Path(__file__).resolve().parents[2]
ODDS_PATH = ROOT / "data" / "historical_odds.jsonl"
HISTORY_PATH = ROOT / "public" / "prediction-history.json"
OUTPUT_PATH = ROOT / "public" / "clv.json"

# Normalise prediction-history abbreviations to the odds-file abbreviations.
ABBR_FIX = {"CHW": "CWS", "OAK": "ATH", "ARI": "AZ", "WSN": "WSH", "SDP": "SD", "SFG": "SF", "TBR": "TB", "KCR": "KC"}


def _norm(abbr: str) -> str:
    a = (abbr or "").upper()
    return ABBR_FIX.get(a, a)


def _valid(ml) -> bool:
    if ml is None:
        return False
    try:
        return 100 <= abs(int(round(float(ml)))) <= 2000
    except (TypeError, ValueError):
        return False


def load_open_close() -> dict[tuple[str, str, str], dict]:
    """Index by (date, away, home) -> opening/closing moneylines."""
    index: dict[tuple[str, str, str], dict] = {}
    for line in ODDS_PATH.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        date = (row.get("start_date") or "")[:10]
        away = _norm(row.get("away_abbr", ""))
        home = _norm(row.get("home_abbr", ""))
        oh, oa = row.get("opening_home_moneyline"), row.get("opening_away_moneyline")
        ch, ca = row.get("closing_home_moneyline"), row.get("closing_away_moneyline")
        if not (date and away and home and _valid(oh) and _valid(oa) and _valid(ch) and _valid(ca)):
            continue
        index[(date, away, home)] = {
            "open_home": int(round(float(oh))), "open_away": int(round(float(oa))),
            "close_home": int(round(float(ch))), "close_away": int(round(float(ca))),
        }
    return index


def _lookup(index: dict, date: str, away: str, home: str) -> dict | None:
    away_opts = TEAM_ALIASES.get(_norm(away), [_norm(away)])
    home_opts = TEAM_ALIASES.get(_norm(home), [_norm(home)])
    for a in away_opts:
        for h in home_opts:
            hit = index.get((date[:10], a, h))
            if hit:
                return hit
    return None


def _no_vig_pair(home_ml: int, away_ml: int) -> tuple[float, float]:
    """De-vig the two-way market so open vs close is compared on fair probabilities."""
    h = implied_probability(home_ml)
    a = implied_probability(away_ml)
    total = h + a
    if total <= 0:
        return 0.5, 0.5
    return h / total, a / total


def compute_rows() -> list[dict]:
    index = load_open_close()
    history = json.loads(HISTORY_PATH.read_text())["predictions"]
    rows: list[dict] = []
    for r in history:
        odds = _lookup(index, r["date"], r.get("away", ""), r.get("home", ""))
        if not odds:
            continue
        pick = _norm(r.get("predicted", ""))
        home = _norm(r.get("home", ""))
        pick_home = pick == home
        open_h, open_a = _no_vig_pair(odds["open_home"], odds["open_away"])
        close_h, close_a = _no_vig_pair(odds["close_home"], odds["close_away"])
        entry = open_h if pick_home else open_a
        close = close_h if pick_home else close_a
        entry_ml = odds["open_home"] if pick_home else odds["open_away"]
        close_ml = odds["close_home"] if pick_home else odds["close_away"]
        clv = close - entry  # probability points; positive = beat the close
        rows.append({
            "date": r["date"],
            "pick": pick,
            "confidence": r.get("confidence"),
            "correct": r.get("correct"),
            "entry_ml": entry_ml,
            "close_ml": close_ml,
            "entry_prob": round(entry, 4),
            "close_prob": round(close, 4),
            "clv": round(clv, 4),
            "beat_close": clv > 0,
        })
    return rows


def _summary(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    beat = sum(1 for r in rows if r["beat_close"])
    avg_clv = sum(r["clv"] for r in rows) / n
    graded = [r for r in rows if r["correct"] in (0, 1)]
    win = (sum(int(r["correct"]) for r in graded) / len(graded)) if graded else None
    # Win rate split by whether we beat the close — validates that CLV predicts wins.
    beat_g = [r for r in graded if r["beat_close"]]
    miss_g = [r for r in graded if not r["beat_close"]]
    return {
        "n": n,
        "beat_close_rate": round(beat / n, 4),
        "avg_clv": round(avg_clv, 4),
        "avg_clv_pct_points": round(avg_clv * 100, 2),
        "win_rate": round(win, 4) if win is not None else None,
        "win_rate_when_beat_close": round(sum(int(r["correct"]) for r in beat_g) / len(beat_g), 4) if beat_g else None,
        "win_rate_when_missed_close": round(sum(int(r["correct"]) for r in miss_g) / len(miss_g), 4) if miss_g else None,
    }


def build() -> dict:
    rows = compute_rows()
    by_conf = {}
    for tier in ("Elite", "High", "Medium", "Low"):
        by_conf[tier] = _summary([r for r in rows if r["confidence"] == tier])
    payload = {
        "generated_from": "data/historical_odds.jsonl (opening=entry, closing=close), de-vigged",
        "note": "Positive CLV = our picked side's price shortened by first pitch = we beat the closing line.",
        "overall": _summary(rows),
        "by_confidence": by_conf,
        "recent": sorted(rows, key=lambda r: r["date"], reverse=True)[:40],
    }
    return payload


def main() -> None:
    payload = build()
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    o = payload["overall"]
    print(f"CLV matched {o['n']} picks")
    print(f"  beat-close rate : {o['beat_close_rate']:.1%}")
    print(f"  avg CLV         : {o['avg_clv_pct_points']:+.2f} pct points")
    print(f"  win rate        : {o['win_rate']:.1%}" if o.get("win_rate") is not None else "")
    print(f"  win | beat close: {o['win_rate_when_beat_close']}")
    print(f"  win | miss close: {o['win_rate_when_missed_close']}")
    print("by confidence:")
    for tier, s in payload["by_confidence"].items():
        if s.get("n"):
            print(f"  {tier:7s} n={s['n']:4d} beat={s['beat_close_rate']:.1%} avgCLV={s['avg_clv_pct_points']:+.2f}pp win={s.get('win_rate')}")


if __name__ == "__main__":
    main()
