"""Offline confidence-gate research on one walk-forward pass."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.pipeline import Pipeline

import probability_calibration as pc
import trained_edge_model as m
from daily_auto_model import walk_forward_history
from mlb_api import load_or_fetch_games, load_team_abbreviations
from model_metrics import evaluate

CACHE = Path(__file__).resolve().parents[2] / "data" / "model" / "walkforward-gate-cache.json"


def _load_rows() -> list[dict]:
    if CACHE.exists():
        return json.loads(CACHE.read_text())

    games = load_or_fetch_games(date(2026, 3, 20), date(2026, 6, 23))
    prior = load_or_fetch_games(date(2025, 3, 20), date(2025, 10, 5))
    abbr = load_team_abbreviations()
    m.SELECTED_FEATURE_INDICES = list(m.SELECTED_FEATURE_INDICES)
    m.build_model = lambda: Pipeline(
        [
            (
                "model",
                GradientBoostingClassifier(
                    n_estimators=104,
                    learning_rate=0.043,
                    max_depth=2,
                    subsample=0.90,
                    random_state=42,
                ),
            )
        ]
    )
    rows = walk_forward_history(games, abbr, prior_games=prior)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(rows))
    return rows


def _relabel(rows: list[dict], prob: float, era: float, form: float) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        pick = float(row["rawPickProbability"])
        era_diff = float(row.get("eraDiff") or 0)
        form_edge = float(row.get("formEdge") or 0)
        market_ok = bool(row.get("marketBacked"))
        market_agrees = row.get("marketAgrees")

        if not market_ok:
            tier = "Medium" if pick >= pc.UNCERTAIN_MEDIUM_MIN else "Low"
        elif (
            pick >= pc.ELITE_MIN_RAW_PICK
            and era_diff >= pc.ELITE_MIN_ERA_DIFF
            and form_edge >= pc.ELITE_MIN_FORM_EDGE
        ):
            tier = "Elite"
        elif pick >= prob and era_diff >= era and form_edge >= form:
            tier = "High"
        elif pick >= pc.MEDIUM_MIN:
            tier = "Medium"
        else:
            tier = "Low"

        if tier in ("High", "Elite") and market_agrees is False:
            tier = "Medium" if pick >= pc.MEDIUM_MIN else "Low"

        relabeled = dict(row)
        relabeled["confidence"] = tier
        out.append(relabeled)
    return out


def _score(rows: list[dict]) -> dict:
    cur = sorted([r for r in rows if r.get("correct") in (0, 1)], key=lambda r: r["date"])
    l100, l250 = cur[-100:], cur[-250:]
    he = [r for r in cur if r.get("confidence") in ("High", "Elite")]
    return {
        "acc": evaluate(cur, "rawPickProbability")["accuracy"],
        "l250": evaluate(l250, "rawPickProbability")["accuracy"],
        "l100": evaluate(l100, "rawPickProbability")["accuracy"],
        "he": evaluate(he, "rawPickProbability")["accuracy"] if he else 0.0,
        "he_n": len(he),
    }


def main() -> None:
    rows = _load_rows()
    orig = (pc.HIGH_MIN_RAW_PICK, pc.HIGH_MIN_ERA_DIFF, pc.HIGH_MIN_FORM_EDGE)
    print(f"cached_rows={len(rows)}")
    print(f"BASE {_score(rows)}")

    best = ("base", 0.0, _score(rows))
    for prob in [0.65, 0.66, 0.67, 0.68]:
        for era in [0.8, 0.9, 1.0, 1.2, 1.5]:
            for form in [0.0, 0.02, 0.05]:
                relabeled = _relabel(rows, prob, era, form)
                s = _score(relabeled)
                if s["he_n"] < 35:
                    continue
                obj = s["he"] * 0.55 + s["l250"] * 0.25 + s["l100"] * 0.20
                label = f"p{prob}_e{era}_f{form}"
                print(f"{label:18s} H/E={s['he']:.3f}({s['he_n']:2d}) l250={s['l250']:.3f} l100={s['l100']:.3f} obj={obj:.3f}")
                if obj > best[1]:
                    best = (label, obj, s)

    print(f"BEST {best}")


if __name__ == "__main__":
    main()
