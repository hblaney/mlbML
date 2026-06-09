"""Audit whether the model has real data sources available.

This script exists to prevent accidental training on synthetic placeholders.
Run it before feature search, backtesting, or model promotion.
"""

from __future__ import annotations

import importlib.util
import json
import os
from datetime import date, timedelta
from pathlib import Path

from mlb_api import load_or_fetch_games

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_REPORT = ROOT / "public" / "data-audit.json"


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def audit_sources() -> dict:
    odds_key = bool(os.getenv("ODDS_API_KEY"))
    local_odds = (
        any((ROOT / "data").glob("**/*odds*.csv"))
        or any((ROOT / "data").glob("**/*odds*.json"))
        or (ROOT / "data" / "historical_odds.jsonl").exists()
    )
    statcast_available = has_module("pybaseball")
    pyarrow_available = has_module("pyarrow")

    sample_games = []
    try:
        games = load_or_fetch_games(date.today() - timedelta(days=14), date.today() - timedelta(days=1))
        sample_games = games[:5]
    except Exception:
        games = []

    sources = {
        "mlb_schedule_results": {
            "status": "real" if sample_games else "missing",
            "source": "MLB Stats API",
            "sample_games": len(sample_games),
        },
        "probable_pitchers_and_pitcher_stats": {
            "status": "real" if sample_games else "missing",
            "source": "MLB Stats API people/stats",
        },
        "park_factors": {
            "status": "real_curated",
            "source": "local curated MLB park metadata",
        },
        "historical_weather": {
            "status": "real_available",
            "source": "Open-Meteo archive API",
        },
        "current_weather": {
            "status": "real_available",
            "source": "Open-Meteo forecast API",
        },
        "statcast": {
            "status": "real_available" if statcast_available and pyarrow_available else "missing_dependency",
            "source": "pybaseball / Baseball Savant Statcast",
            "requires": ["pybaseball", "pandas", "pyarrow"],
        },
        "historical_odds": {
            "status": "real_available" if odds_key or local_odds else "missing",
            "source": "The Odds API historical endpoint or imported local odds dataset",
            "requires": "ODDS_API_KEY with historical access, or data/*odds*.csv/json",
        },
        "injuries_lineups": {
            "status": "missing",
            "source": "not configured",
        },
    }

    required_for_promotion = [
        "mlb_schedule_results",
        "probable_pitchers_and_pitcher_stats",
        "park_factors",
        "historical_weather",
        "statcast",
        "historical_odds",
    ]
    missing_required = [
        name
        for name in required_for_promotion
        if not str(sources[name]["status"]).startswith("real")
    ]

    return {
        "generated_at": date.today().isoformat(),
        "promotion_allowed": len(missing_required) == 0,
        "missing_required_sources": missing_required,
        "sources": sources,
    }


def main() -> None:
    report = audit_sources()
    PUBLIC_REPORT.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_REPORT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if not report["promotion_allowed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
