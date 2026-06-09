"""Odds provider for market features and best-bet edges.

Set ODDS_API_KEY to use The Odds API. Without a key, the model uses neutral
market priors so local development still works.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from context import MarketSnapshot
from mlb_api import GameRecord, load_team_names

ODDS_API_BASE = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
ODDS_HISTORICAL_API_BASE = "https://api.the-odds-api.com/v4/historical/sports/baseball_mlb/odds"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def implied_probability(american_odds: int) -> float:
    if american_odds == 0:
        return 0.5
    if american_odds < 0:
        return abs(american_odds) / (abs(american_odds) + 100)
    return 100 / (american_odds + 100)


def probability_to_american(probability: float) -> int:
    probability = max(0.01, min(0.99, probability))
    if probability >= 0.5:
        return int(round(-(probability / (1 - probability)) * 100))
    return int(round(((1 - probability) / probability) * 100))


def _average_price(prices: list[int]) -> int:
    if not prices:
        return 0
    implied = [implied_probability(price) for price in prices if price]
    if not implied:
        return 0
    return probability_to_american(sum(implied) / len(implied))


def fetch_moneyline_market() -> dict[tuple[str, str], MarketSnapshot]:
    _load_env_file()
    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        return {}

    params = urlencode(
        {
            "apiKey": api_key,
            "regions": os.getenv("ODDS_REGIONS", "us"),
            "markets": "h2h,spreads,totals",
            "oddsFormat": "american",
        }
    )

    try:
        with urlopen(f"{ODDS_API_BASE}?{params}", timeout=30) as response:
            events = json.load(response)
    except Exception:
        return {}

    market: dict[tuple[str, str], MarketSnapshot] = {}
    for event in events:
        home_name = event.get("home_team", "")
        away_name = event.get("away_team", "")
        home_prices: list[int] = []
        away_prices: list[int] = []
        totals: list[float] = []
        over_prices: list[int] = []
        under_prices: list[int] = []
        home_runlines: list[float] = []
        away_runlines: list[float] = []
        home_runline_prices: list[int] = []
        away_runline_prices: list[int] = []
        over_prices: list[int] = []
        under_prices: list[int] = []
        home_runlines: list[float] = []
        away_runlines: list[float] = []
        home_runline_prices: list[int] = []
        away_runline_prices: list[int] = []

        for book in event.get("bookmakers", []):
            for line in book.get("markets", []):
                if line.get("key") == "h2h":
                    for outcome in line.get("outcomes", []):
                        if outcome.get("name") == home_name:
                            home_prices.append(int(outcome.get("price", 0)))
                        elif outcome.get("name") == away_name:
                            away_prices.append(int(outcome.get("price", 0)))
                elif line.get("key") == "totals":
                    for outcome in line.get("outcomes", []):
                        if outcome.get("point") is not None:
                            totals.append(float(outcome["point"]))
                        if outcome.get("name") == "Over":
                            over_prices.append(int(outcome.get("price", 0)))
                        elif outcome.get("name") == "Under":
                            under_prices.append(int(outcome.get("price", 0)))
                elif line.get("key") == "spreads":
                    for outcome in line.get("outcomes", []):
                        if outcome.get("name") == home_name:
                            home_runlines.append(float(outcome.get("point", 0)))
                            home_runline_prices.append(int(outcome.get("price", 0)))
                        elif outcome.get("name") == away_name:
                            away_runlines.append(float(outcome.get("point", 0)))
                            away_runline_prices.append(int(outcome.get("price", 0)))
                        if outcome.get("name") == "Over":
                            over_prices.append(int(outcome.get("price", 0)))
                        elif outcome.get("name") == "Under":
                            under_prices.append(int(outcome.get("price", 0)))
                elif line.get("key") == "spreads":
                    for outcome in line.get("outcomes", []):
                        if outcome.get("name") == home_name:
                            home_runlines.append(float(outcome.get("point", 0)))
                            home_runline_prices.append(int(outcome.get("price", 0)))
                        elif outcome.get("name") == away_name:
                            away_runlines.append(float(outcome.get("point", 0)))
                            away_runline_prices.append(int(outcome.get("price", 0)))

        home_price = _average_price(home_prices)
        away_price = _average_price(away_prices)
        market[(away_name.lower(), home_name.lower())] = MarketSnapshot(
            home_moneyline=home_price,
            away_moneyline=away_price,
            home_implied_probability=implied_probability(home_price),
            away_implied_probability=implied_probability(away_price),
            market_total=sum(totals) / len(totals) if totals else 8.5,
            over_price=_average_price(over_prices),
            under_price=_average_price(under_prices),
            home_runline=sum(home_runlines) / len(home_runlines) if home_runlines else -1.5,
            away_runline=sum(away_runlines) / len(away_runlines) if away_runlines else 1.5,
            home_runline_price=_average_price(home_runline_prices),
            away_runline_price=_average_price(away_runline_prices),
            source_count=max(len(home_prices), len(away_prices)),
        )

    return market


def _parse_market_events(events: list[dict]) -> dict[tuple[str, str], MarketSnapshot]:
    market: dict[tuple[str, str], MarketSnapshot] = {}
    for event in events:
        home_name = event.get("home_team", "")
        away_name = event.get("away_team", "")
        home_prices: list[int] = []
        away_prices: list[int] = []
        totals: list[float] = []

        for book in event.get("bookmakers", []):
            for line in book.get("markets", []):
                if line.get("key") == "h2h":
                    for outcome in line.get("outcomes", []):
                        if outcome.get("name") == home_name:
                            home_prices.append(int(outcome.get("price", 0)))
                        elif outcome.get("name") == away_name:
                            away_prices.append(int(outcome.get("price", 0)))
                elif line.get("key") == "totals":
                    for outcome in line.get("outcomes", []):
                        if outcome.get("point") is not None:
                            totals.append(float(outcome["point"]))

        home_price = _average_price(home_prices)
        away_price = _average_price(away_prices)
        market[(away_name.lower(), home_name.lower())] = MarketSnapshot(
            home_moneyline=home_price,
            away_moneyline=away_price,
            home_implied_probability=implied_probability(home_price),
            away_implied_probability=implied_probability(away_price),
            market_total=sum(totals) / len(totals) if totals else 8.5,
            over_price=_average_price(over_prices),
            under_price=_average_price(under_prices),
            home_runline=sum(home_runlines) / len(home_runlines) if home_runlines else -1.5,
            away_runline=sum(away_runlines) / len(away_runlines) if away_runlines else 1.5,
            home_runline_price=_average_price(home_runline_prices),
            away_runline_price=_average_price(away_runline_prices),
            source_count=max(len(home_prices), len(away_prices)),
        )
    return market


def fetch_historical_moneyline_market(iso_datetime: str) -> dict[tuple[str, str], MarketSnapshot]:
    """Fetch historical odds snapshot from The Odds API.

    Historical odds are not freely available from MLB itself. This requires an
    `ODDS_API_KEY` with historical access, or the caller must import a local
    historical odds file instead.
    """
    _load_env_file()
    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        return {}

    params = urlencode(
        {
            "apiKey": api_key,
            "regions": os.getenv("ODDS_REGIONS", "us"),
            "markets": "h2h,spreads,totals",
            "oddsFormat": "american",
            "date": iso_datetime,
        }
    )

    try:
        with urlopen(f"{ODDS_HISTORICAL_API_BASE}?{params}", timeout=30) as response:
            payload = json.load(response)
    except Exception:
        return {}

    events = payload.get("data", payload if isinstance(payload, list) else [])
    return _parse_market_events(events)


def market_for_game(game: GameRecord, market: dict[tuple[str, str], MarketSnapshot] | None = None) -> MarketSnapshot:
    if not market:
        return MarketSnapshot()

    names = load_team_names()
    away = names.get(game.away_team_id, "").lower()
    home = names.get(game.home_team_id, "").lower()

    return market.get((away, home), MarketSnapshot())
