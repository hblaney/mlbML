"""Walk-forward accuracy research runner — compare candidate configs vs the live model.

Usage:
  python3 scripts/model/accuracy_research.py
  python3 scripts/model/accuracy_research.py --quick
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.pipeline import Pipeline

import trained_edge_model as m
from daily_auto_model import walk_forward_history
from mlb_api import load_or_fetch_games, load_team_abbreviations
from model_metrics import evaluate

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "model" / "accuracy-research-latest.json"


def _score(rows: list[dict]) -> dict:
    cur = sorted([r for r in rows if r.get("correct") in (0, 1)], key=lambda r: r["date"])
    l100, l250 = cur[-100:], cur[-250:]
    he = [r for r in cur if r.get("confidence") in ("High", "Elite")]
    mb = [r for r in cur if r.get("marketBacked")]
    return {
        "acc": evaluate(cur, "rawPickProbability")["accuracy"],
        "l250": evaluate(l250, "rawPickProbability")["accuracy"],
        "l100": evaluate(l100, "rawPickProbability")["accuracy"],
        "he": evaluate(he, "rawPickProbability")["accuracy"] if he else 0.0,
        "he_n": len(he),
        "mb": evaluate(mb, "rawPickProbability")["accuracy"] if mb else 0.0,
    }


def _run(label: str, *, feats: list[int] | None = None, gbm: tuple[int, float, float] = (104, 0.043, 0.90)) -> dict:
    games = load_or_fetch_games(date(2026, 3, 20), date(2026, 6, 23))
    prior = load_or_fetch_games(date(2025, 3, 20), date(2025, 10, 5))
    abbr = load_team_abbreviations()
    m.SELECTED_FEATURE_INDICES = sorted(feats or m.SELECTED_FEATURE_INDICES)
    ne, lr, sub = gbm
    m.build_model = lambda: Pipeline(
        [
            (
                "model",
                GradientBoostingClassifier(
                    n_estimators=ne,
                    learning_rate=lr,
                    max_depth=2,
                    subsample=sub,
                    random_state=42,
                ),
            )
        ]
    )
    metrics = _score(walk_forward_history(games, abbr, prior_games=prior))
    metrics["obj"] = (
        metrics["acc"] * 0.20
        + metrics["l250"] * 0.26
        + metrics["l100"] * 0.24
        + metrics["he"] * 0.20
        + metrics["mb"] * 0.06
    )
    return {"label": label, **metrics}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="Run baseline only")
    args = parser.parse_args()

    live = list(m.SELECTED_FEATURE_INDICES)
    candidates: list[tuple[str, dict]] = [("live_v43", {})]
    if not args.quick:
        candidates.extend(
            [
                ("add_203", {"feats": sorted(set(live) | {203})}),
                ("add_217", {"feats": sorted(set(live) | {217})}),
                ("gb_100_045", {"gbm": (100, 0.045, 0.90)}),
                ("gb_106_042", {"gbm": (106, 0.042, 0.90)}),
            ]
        )

    results = [_run(label, **kw) for label, kw in candidates]
    results.sort(key=lambda row: row["obj"], reverse=True)
    payload = {"generated_at": date.today().isoformat(), "results": results}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))

    print(f"{'label':16s} {'acc':>6s} {'l250':>6s} {'l100':>6s} {'H/E':>6s} {'obj':>6s}")
    for row in results:
        print(
            f"{row['label']:16s} {row['acc']:6.3f} {row['l250']:6.3f} {row['l100']:6.3f} "
            f"{row['he']:6.3f} {row['obj']:6.3f}"
        )
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
