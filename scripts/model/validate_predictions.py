"""Create a compact validation report from walk-forward prediction history."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable

PUBLIC_DIR = Path(__file__).resolve().parents[2] / "public"
HISTORY_PATH = PUBLIC_DIR / "prediction-history.json"
OUTPUT_PATH = PUBLIC_DIR / "model-validation.json"


def summarize(rows: Iterable[dict]) -> dict:
    rows = list(rows)
    total = len(rows)
    correct = sum(int(row.get("correct", 0)) for row in rows)
    return {
        "games": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
    }


def confidence_buckets(predictions: list[dict]) -> dict[str, dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in predictions:
        buckets[str(row.get("confidence", "Unknown"))].append(row)
    order = ["Elite", "High", "Medium", "Low", "Unknown"]
    return {name: summarize(buckets.get(name, [])) for name in order if buckets.get(name)}


def probability_buckets(predictions: list[dict]) -> dict[str, dict]:
    ranges = [
        ("50-54.9%", 0.50, 0.55),
        ("55-59.9%", 0.55, 0.60),
        ("60-64.9%", 0.60, 0.65),
        ("65-69.9%", 0.65, 0.70),
        ("70%+", 0.70, 1.01),
    ]
    output: dict[str, dict] = {}
    for label, lower, upper in ranges:
        rows = [row for row in predictions if lower <= float(row.get("pickProbability", 0.0)) < upper]
        if rows:
            output[label] = summarize(rows)
    return output


def main() -> None:
    payload = json.loads(HISTORY_PATH.read_text())
    predictions = payload.get("predictions", [])
    report = {
        "generated_at": payload.get("generated_at"),
        "model_version": predictions[-1].get("modelVersion") if predictions else None,
        "overall": summarize(predictions),
        "by_confidence": confidence_buckets(predictions),
        "by_pick_probability": probability_buckets(predictions),
    }
    OUTPUT_PATH.write_text(json.dumps(report, indent=2))

    print(f"games={report['overall']['games']}")
    print(f"overall_accuracy={report['overall']['accuracy']:.4f}")
    for name, bucket in report["by_confidence"].items():
        print(f"{name.lower()}_games={bucket['games']} accuracy={bucket['accuracy']:.4f}")


if __name__ == "__main__":
    main()
