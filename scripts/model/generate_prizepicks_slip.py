"""Build PrizePicks 3-leg slips from prop-leans.json (K + hitter FS)."""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROPS_PATH = REPO / "public" / "prop-leans.json"
OUT_PATH = REPO / "public" / "prizepicks-slip.json"

LEGS = 3


def _edge(lean: dict) -> float:
    if lean.get("lean") not in ("Over", "Under"):
        return 0.0
    stored = lean.get("edge")
    if stored is not None and float(stored) > 0:
        return float(stored)
    proj = float(lean.get("projection", 0))
    line = float(lean.get("line", 0))
    direction = 1 if lean["lean"] == "Over" else -1
    return max(0.0, (proj - line) * direction)


def _game_id(lean: dict) -> str:
    return lean.get("gameId") or lean.get("matchup", "")


def _score_combo(legs: list[dict], *, penalize_same_game: bool) -> float:
    games = [_game_id(l) for l in legs]
    unique_games = len(set(games))
    edge_sum = sum(_edge(l) for l in legs)
    penalty = 0.0
    if penalize_same_game and unique_games < LEGS:
        penalty = (LEGS - unique_games) * 1.25
    types = len({l.get("prop") for l in legs})
    type_bonus = 0.4 * (types - 1)
    conf_bonus = sum(0.15 for l in legs if l.get("confidence") == "high")
    return edge_sum + type_bonus + conf_bonus - penalty


def build_slip(leans: list[dict], n_legs: int = LEGS) -> dict | None:
    candidates = [l for l in leans if _edge(l) > 0 and l.get("confidence") != "pass"]
    if len(candidates) < n_legs:
        return None

    candidates.sort(key=_edge, reverse=True)
    pool = candidates[: min(18, len(candidates))]

    best_legs: list[dict] | None = None
    best_score = -1.0
    best_same_game = False

    for penalize in (True, False):
        for combo in combinations(pool, n_legs):
            sc = _score_combo(list(combo), penalize_same_game=penalize)
            if sc > best_score:
                best_score = sc
                best_legs = list(combo)
                best_same_game = len({_game_id(c) for c in combo}) < n_legs

    if best_legs is None:
        return None

    return {
        "legs": [
            {
                "player": l["player"],
                "prop": l["prop"],
                "line": l["line"],
                "pick": l["lean"],
                "projection": l.get("projection"),
                "matchup": l.get("matchup"),
                "confidence": l.get("confidence"),
                "edge": round(_edge(l), 2),
            }
            for l in best_legs
        ],
        "score": round(best_score, 2),
        "same_game_warning": best_same_game,
    }


def main() -> None:
    if not PROPS_PATH.exists():
        print("prizepicks_slip_skip run generate_prop_leans first")
        return

    data = json.loads(PROPS_PATH.read_text())
    leans = data.get("leans", [])
    slip = build_slip(leans)

    out = {
        "generated_at": data.get("generated_at"),
        "source": "prizepicks-slip-v2",
        "disclaimer": (
            "Verify posted lines on PrizePicks before playing. "
            "Estimated lines used when posted line unknown."
        ),
        "slip": slip,
        "top_plays": data.get("top_plays", []),
        "all_actionable": [
            {k: l[k] for k in ("player", "prop", "line", "lean", "projection", "edge", "confidence", "matchup") if k in l}
            for l in sorted(leans, key=_edge, reverse=True)
            if _edge(l) > 0
        ][:20],
    }

    OUT_PATH.write_text(json.dumps(out, indent=2))

    if slip is None:
        print("prizepicks_slip_skip not enough qualifying legs")
        return

    print(f"prizepicks_slip_ok legs={len(slip['legs'])} score={slip['score']}")
    for i, leg in enumerate(slip["legs"], 1):
        prop_label = "K" if leg["prop"] == "strikeouts" else "Hitter FS"
        print(f"  {i}. {leg['player']} — {prop_label} {leg['pick']} {leg['line']} (proj {leg['projection']}, {leg['confidence']})")
    if slip.get("same_game_warning"):
        print("  NOTE: correlated same-game legs")


if __name__ == "__main__":
    main()
