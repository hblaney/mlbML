"""Download and normalize a free SportsBookReview-derived MLB odds dataset.

Dataset source:
https://github.com/ArnavSaraogi/mlb-odds-scraper/releases/tag/dataset

The release contains real historical MLB moneyline, spread, totals, scores, and
bookmaker odds from SportsBookReview. This script converts it into a compact
JSONL file the model can join against by date/team.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from urllib.request import urlretrieve

DATASET_URL = "https://github.com/ArnavSaraogi/mlb-odds-scraper/releases/download/dataset/mlb_odds_dataset.json"
ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = ROOT / "data" / "raw" / "mlb_odds_dataset.json"
NORMALIZED_PATH = ROOT / "data" / "historical_odds.jsonl"


def download_dataset() -> None:
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    if RAW_PATH.exists() and RAW_PATH.stat().st_size > 1_000_000:
        print(f"raw_dataset_exists={RAW_PATH}")
        return

    print(f"downloading={DATASET_URL}")
    urlretrieve(DATASET_URL, RAW_PATH)
    print(f"downloaded={RAW_PATH}")


def avg(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def normalize_game(game: dict) -> dict | None:
    game_view = game.get("gameView", {})
    odds = game.get("odds", {})
    away = game_view.get("awayTeam", {})
    home = game_view.get("homeTeam", {})

    if not away.get("shortName") or not home.get("shortName"):
        return None

    opening_home_ml: list[float] = []
    opening_away_ml: list[float] = []
    closing_home_ml: list[float] = []
    closing_away_ml: list[float] = []
    totals: list[float] = []
    over_prices: list[float] = []
    under_prices: list[float] = []
    books: set[str] = set()

    for line in odds.get("moneyline", []):
        book = line.get("sportsbook")
        if book:
            books.add(str(book))
        opening = line.get("openingLine") or {}
        current = line.get("currentLine") or {}
        if opening.get("homeOdds") is not None:
            opening_home_ml.append(float(opening["homeOdds"]))
        if opening.get("awayOdds") is not None:
            opening_away_ml.append(float(opening["awayOdds"]))
        if current.get("homeOdds") is not None:
            closing_home_ml.append(float(current["homeOdds"]))
        if current.get("awayOdds") is not None:
            closing_away_ml.append(float(current["awayOdds"]))

    for line in odds.get("totals", []):
        book = line.get("sportsbook")
        if book:
            books.add(str(book))
        current = line.get("currentLine") or {}
        opening = line.get("openingLine") or {}
        total = current.get("total", opening.get("total"))
        if total is not None:
            totals.append(float(total))
        if current.get("overOdds") is not None:
            over_prices.append(float(current["overOdds"]))
        if current.get("underOdds") is not None:
            under_prices.append(float(current["underOdds"]))

    return {
        "start_date": game_view.get("startDate"),
        "game_type": game_view.get("gameType"),
        "away_team": away.get("fullName"),
        "away_abbr": away.get("shortName"),
        "home_team": home.get("fullName"),
        "home_abbr": home.get("shortName"),
        "away_score": game_view.get("awayTeamScore"),
        "home_score": game_view.get("homeTeamScore"),
        "venue": game_view.get("venueName"),
        "opening_home_moneyline": avg(opening_home_ml),
        "opening_away_moneyline": avg(opening_away_ml),
        "closing_home_moneyline": avg(closing_home_ml),
        "closing_away_moneyline": avg(closing_away_ml),
        "closing_total": avg(totals),
        "closing_over_price": avg(over_prices),
        "closing_under_price": avg(under_prices),
        "sportsbook_count": len(books),
        "sportsbooks": sorted(books),
    }


def normalize_dataset() -> None:
    payload = json.loads(RAW_PATH.read_text())
    if isinstance(payload, dict) and "games" in payload:
        games = payload["games"]
    elif isinstance(payload, dict):
        games = [game for day_games in payload.values() for game in day_games]
    elif isinstance(payload, list):
        games = payload
    else:
        games = []
    NORMALIZED_PATH.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with NORMALIZED_PATH.open("w") as handle:
        for game in games:
            row = normalize_game(game)
            if row is None:
                continue
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            written += 1

    print(f"normalized_rows={written}")
    print(f"normalized_path={NORMALIZED_PATH}")


def main() -> None:
    download_dataset()
    normalize_dataset()


if __name__ == "__main__":
    main()
