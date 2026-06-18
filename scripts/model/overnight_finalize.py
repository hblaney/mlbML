"""Merge all overnight logs into final morning briefing."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def main() -> None:
    model_rows = load_jsonl(ROOT / "data" / "overnight-model-research.jsonl")
    strategy_rows = load_jsonl(ROOT / "data" / "overnight-research.jsonl")
    exhaustive_path = ROOT / "public" / "overnight-morning-report.json"

    model_best = None
    for row in model_rows:
        if row.get("beats_baseline") and row.get("accuracy", 0) >= (model_best or {}).get("accuracy", 0):
            model_best = row

    briefing = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "read_this_first": str(ROOT / "public" / "overnight-morning-report.json"),
        "model_best_found": model_best,
        "strategy_experiments_run": len(strategy_rows),
        "model_experiments_run": len(model_rows),
    }
    if exhaustive_path.exists():
        briefing["exhaustive_summary"] = json.loads(exhaustive_path.read_text()).get("executive_summary")

    out = ROOT / "public" / "overnight-briefing.json"
    out.write_text(json.dumps(briefing, indent=2))
    print(json.dumps(briefing, indent=2))


if __name__ == "__main__":
    main()
