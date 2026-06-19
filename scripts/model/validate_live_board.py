"""Hard checks: live board must use final_public_probabilities only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from daily_auto_model import MODEL_VERSION
from trained_edge_model import public_confidence_for

PUBLIC_PATH = Path(__file__).resolve().parents[2] / "public" / "predictions.json"

FORBIDDEN_EXPLANATION_FRAGMENTS = (
    "probability nudged toward",
    "probability shifted",
    "not market-blended or heuristic-adjusted",
    "internal scale",
)


def validate_live_board(payload: dict | None = None) -> list[str]:
    errors: list[str] = []
    if payload is None:
        if not PUBLIC_PATH.exists():
            return ["missing public/predictions.json"]
        payload = json.loads(PUBLIC_PATH.read_text())

    if payload.get("model_version") != MODEL_VERSION:
        errors.append(
            f"model_version mismatch: board={payload.get('model_version')!r} code={MODEL_VERSION!r}"
        )

    for row in payload.get("predictions", []):
        game_id = row.get("id", "?")
        pick = float(row.get("pickProbability", 0))
        home = float(row.get("modelHomeWinProbability", 0))
        away = float(row.get("modelAwayWinProbability", 0))
        confidence = row.get("confidence")
        expected_conf = public_confidence_for(pick)
        if confidence != expected_conf:
            errors.append(
                f"{game_id}: confidence {confidence!r} != expected {expected_conf!r} for pick {pick:.4f}"
            )
        if abs(pick - max(home, away)) > 0.0001:
            errors.append(f"{game_id}: pickProbability {pick} != max(home, away)")
        if abs(home + away - 1.0) > 0.0001:
            errors.append(f"{game_id}: home+away != 1 ({home}+{away})")
        if row.get("modelVersion") and row.get("modelVersion") != MODEL_VERSION:
            errors.append(f"{game_id}: row modelVersion {row.get('modelVersion')!r} != {MODEL_VERSION!r}")
        explanation = " ".join(row.get("explanation") or [])
        for fragment in FORBIDDEN_EXPLANATION_FRAGMENTS:
            if fragment in explanation.lower():
                errors.append(f"{game_id}: forbidden legacy explanation fragment: {fragment!r}")

    return errors


def main() -> None:
    errors = validate_live_board()
    if errors:
        print("live board validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    count = len(json.loads(PUBLIC_PATH.read_text()).get("predictions", []))
    print(f"live_board_ok games={count} model={MODEL_VERSION}")


if __name__ == "__main__":
    main()
