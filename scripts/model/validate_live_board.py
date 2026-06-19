"""Hard checks: live board must use final_public_probabilities only."""

from __future__ import annotations

import sys

from prediction_integrity import run_all


def main() -> None:
    errors = run_all(recompute=False, ticket=False, accuracy=False)
    if errors:
        print("live board validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    print("live_board_ok")


if __name__ == "__main__":
    main()
