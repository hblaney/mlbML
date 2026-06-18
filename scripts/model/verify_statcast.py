"""Prove Statcast features are real (non-zero) before first pitch."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from mlb_api import load_team_abbreviations
from statcast_provider import StatcastTeamCache, statcast_feature_vector

OUTPUT = Path(__file__).resolve().parents[2] / "public" / "statcast-audit.json"


def main() -> None:
    as_of = date.today()
    year = as_of.year
    cache = StatcastTeamCache()
    cache.preload_season(year)

    abbr = load_team_abbreviations()
    sample_teams = ["NYY", "LAD", "HOU", "ATL"]
    team_rows: list[dict] = []
    for code in sample_teams:
        metrics = cache.team_metrics(code, as_of, 14)
        nonzero = {key: round(value, 4) for key, value in metrics.items() if abs(value) > 1e-6}
        team_rows.append({"team": code, "window_days": 14, "metrics": nonzero})

    vector = statcast_feature_vector(cache, "NYY", "BOS", as_of)
    nonzero_count = sum(1 for value in vector if abs(value) > 1e-6)

    payload = {
        "checked_at": as_of.isoformat(),
        "season_preloaded": year,
        "sample_teams_14d": team_rows,
        "nyy_vs_bos_feature_count": len(vector),
        "nyy_vs_bos_nonzero_features": nonzero_count,
        "status": "ok" if nonzero_count >= 20 else "degraded",
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    if payload["status"] != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()
