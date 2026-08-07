"""Odds provider for market features and best-bet edges.

Set ODDS_API_KEY to use The Odds API. Without a key, the model uses neutral
market priors so local development still works.
"""

from __future__ import annotations

import json
import os
import ssl
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import certifi

from context import MarketSnapshot
from mlb_api import GameRecord, load_team_names

ODDS_API_BASE = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
ODDS_HISTORICAL_API_BASE = "https://api.the-odds-api.com/v4/historical/sports/baseball_mlb/odds"
ESPN_SCOREBOARD_API = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ODDS_CACHE_PATH = PROJECT_ROOT / "data" / "odds_live_cache.json"
ODDS_CACHE_TTL_SECONDS = int(os.getenv("ODDS_CACHE_TTL_SECONDS", "21600"))
LAST_ODDS_ERROR: str | None = None
LAST_ODDS_SOURCE: str | None = None

_LIVE_MARKET_CACHE: dict[tuple[str, str], MarketSnapshot] | None = None


def _urlopen(url: str, *, timeout: int = 30):
    context = ssl.create_default_context(cafile=certifi.where())
    return urlopen(url, timeout=timeout, context=context)
_LIVE_MARKET_CACHE_AT: float | None = None


def _load_env_file() -> None:
    for env_path in (PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.local"):
        if not env_path.exists():
            continue

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


def _serialize_market(market: dict[tuple[str, str], MarketSnapshot]) -> dict:
    rows = []
    for (away, home), snapshot in market.items():
        rows.append(
            {
                "away": away,
                "home": home,
                "home_moneyline": snapshot.home_moneyline,
                "away_moneyline": snapshot.away_moneyline,
                "home_implied_probability": snapshot.home_implied_probability,
                "away_implied_probability": snapshot.away_implied_probability,
                "market_total": snapshot.market_total,
                "over_price": snapshot.over_price,
                "under_price": snapshot.under_price,
                "home_runline": snapshot.home_runline,
                "away_runline": snapshot.away_runline,
                "home_runline_price": snapshot.home_runline_price,
                "away_runline_price": snapshot.away_runline_price,
                "source_count": snapshot.source_count,
            }
        )
    return {"fetched_at": time.time(), "events": rows}


def _deserialize_market(payload: dict) -> dict[tuple[str, str], MarketSnapshot]:
    market: dict[tuple[str, str], MarketSnapshot] = {}
    for row in payload.get("events", []):
        market[(row["away"], row["home"])] = MarketSnapshot(
            home_moneyline=row["home_moneyline"],
            away_moneyline=row["away_moneyline"],
            home_implied_probability=row["home_implied_probability"],
            away_implied_probability=row["away_implied_probability"],
            market_total=row.get("market_total", 8.5),
            over_price=row.get("over_price", 0),
            under_price=row.get("under_price", 0),
            home_runline=row.get("home_runline", -1.5),
            away_runline=row.get("away_runline", 1.5),
            home_runline_price=row.get("home_runline_price", 0),
            away_runline_price=row.get("away_runline_price", 0),
            source_count=row.get("source_count", 0),
        )
    return market


def _read_cached_market(max_age_seconds: int = ODDS_CACHE_TTL_SECONDS) -> dict[tuple[str, str], MarketSnapshot] | None:
    global _LIVE_MARKET_CACHE, _LIVE_MARKET_CACHE_AT

    if _LIVE_MARKET_CACHE is not None and _LIVE_MARKET_CACHE_AT is not None:
        if time.time() - _LIVE_MARKET_CACHE_AT <= max_age_seconds:
            return _LIVE_MARKET_CACHE

    if not ODDS_CACHE_PATH.exists():
        return None

    try:
        payload = json.loads(ODDS_CACHE_PATH.read_text())
        fetched_at = float(payload.get("fetched_at", 0))
        if time.time() - fetched_at > max_age_seconds:
            return None
        market = _deserialize_market(payload)
        _LIVE_MARKET_CACHE = market
        _LIVE_MARKET_CACHE_AT = fetched_at
        return market
    except Exception:
        return None


def _write_cached_market(market: dict[tuple[str, str], MarketSnapshot]) -> None:
    global _LIVE_MARKET_CACHE, _LIVE_MARKET_CACHE_AT

    _LIVE_MARKET_CACHE = market
    _LIVE_MARKET_CACHE_AT = time.time()
    ODDS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ODDS_CACHE_PATH.write_text(json.dumps(_serialize_market(market), indent=2))


def get_last_odds_error() -> str | None:
    return LAST_ODDS_ERROR


def get_last_odds_source() -> str | None:
    return LAST_ODDS_SOURCE


def _parse_american(raw: object) -> int:
    if raw is None:
        return 0
    text = str(raw).strip().replace("−", "-").replace("–", "-")
    if not text or text in {"EVEN", "even"}:
        return 100 if text else 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _espn_close_odds(side: dict | None) -> int:
    if not side:
        return 0
    close = side.get("close") if isinstance(side, dict) else None
    if isinstance(close, dict):
        return _parse_american(close.get("odds"))
    return _parse_american(side.get("odds"))


def _espn_close_line(side: dict | None) -> float | None:
    if not side:
        return None
    close = side.get("close") if isinstance(side, dict) else None
    raw = None
    if isinstance(close, dict):
        raw = close.get("line")
    if raw is None and isinstance(side, dict):
        raw = side.get("line")
    if raw is None:
        return None
    text = str(raw).strip().lower().lstrip("ou")
    try:
        return float(text)
    except ValueError:
        return None


def fetch_espn_moneyline_market(*, game_date: str | None = None) -> dict[tuple[str, str], MarketSnapshot]:
    """Free fallback: DraftKings lines via ESPN's public scoreboard API (no key)."""
    global LAST_ODDS_ERROR, LAST_ODDS_SOURCE

    from datetime import datetime
    from zoneinfo import ZoneInfo

    day = game_date or datetime.now(ZoneInfo("America/Chicago")).strftime("%Y%m%d")
    url = f"{ESPN_SCOREBOARD_API}?dates={day}"
    try:
        with _urlopen(url, timeout=25) as response:
            payload = json.load(response)
    except Exception as error:
        LAST_ODDS_ERROR = f"ESPN odds fallback failed: {error}"
        print(LAST_ODDS_ERROR)
        return {}

    market: dict[tuple[str, str], MarketSnapshot] = {}
    for event in payload.get("events") or []:
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        competition = competitions[0]
        competitors = competition.get("competitors") or []
        home_name = ""
        away_name = ""
        for team in competitors:
            display = ((team.get("team") or {}).get("displayName") or "").strip()
            if team.get("homeAway") == "home":
                home_name = display
            elif team.get("homeAway") == "away":
                away_name = display
        if not home_name or not away_name:
            continue

        odds_rows = competition.get("odds") or []
        if not odds_rows:
            continue
        row = odds_rows[0]
        moneyline = row.get("moneyline") or {}
        home_ml = _espn_close_odds(moneyline.get("home"))
        away_ml = _espn_close_odds(moneyline.get("away"))
        if not home_ml or not away_ml:
            continue

        point_spread = row.get("pointSpread") or {}
        home_rl = _espn_close_line(point_spread.get("home"))
        away_rl = _espn_close_line(point_spread.get("away"))
        home_rl_price = _espn_close_odds(point_spread.get("home"))
        away_rl_price = _espn_close_odds(point_spread.get("away"))

        total_block = row.get("total") or {}
        over_side = total_block.get("over") if isinstance(total_block, dict) else None
        under_side = total_block.get("under") if isinstance(total_block, dict) else None
        over_price = _espn_close_odds(over_side)
        under_price = _espn_close_odds(under_side)
        market_total = _espn_close_line(over_side)
        if market_total is None:
            ou = row.get("overUnder")
            try:
                market_total = float(ou) if ou is not None else 8.5
            except (TypeError, ValueError):
                market_total = 8.5

        if home_rl is None:
            try:
                home_rl = float(row.get("spread")) if row.get("spread") is not None else -1.5
            except (TypeError, ValueError):
                home_rl = -1.5
        if away_rl is None:
            away_rl = -home_rl if home_rl is not None else 1.5

        market[(away_name.lower(), home_name.lower())] = MarketSnapshot(
            home_moneyline=home_ml,
            away_moneyline=away_ml,
            home_implied_probability=implied_probability(home_ml),
            away_implied_probability=implied_probability(away_ml),
            market_total=float(market_total) if market_total is not None else 8.5,
            over_price=over_price,
            under_price=under_price,
            home_runline=float(home_rl),
            away_runline=float(away_rl),
            home_runline_price=home_rl_price,
            away_runline_price=away_rl_price,
            source_count=1,
        )

    if market:
        LAST_ODDS_ERROR = None
        LAST_ODDS_SOURCE = "ESPN/DraftKings"
        _write_cached_market(market)
        print(f"espn_odds_ok games={len(market)}")
    else:
        LAST_ODDS_ERROR = "ESPN odds fallback returned no moneylines"
        print(LAST_ODDS_ERROR)
    return market


def _average_price(prices: list[int]) -> int:
    if not prices:
        return 0
    implied = [implied_probability(price) for price in prices if price]
    if not implied:
        return 0
    return probability_to_american(sum(implied) / len(implied))


def fetch_moneyline_market(*, force_refresh: bool = False) -> dict[tuple[str, str], MarketSnapshot]:
    global LAST_ODDS_ERROR, LAST_ODDS_SOURCE

    if not force_refresh:
        cached = _read_cached_market()
        if cached is not None:
            return cached

    _load_env_file()
    api_key = os.getenv("ODDS_API_KEY")
    prefer_espn = os.getenv("ODDS_PREFER_ESPN", "").strip().lower() in {"1", "true", "yes"}

    def _fallback_espn_or_cache(reason: str) -> dict[tuple[str, str], MarketSnapshot]:
        LAST_ODDS_ERROR = reason
        print(reason)
        espn = fetch_espn_moneyline_market()
        if espn:
            return espn
        cached = _read_cached_market(max_age_seconds=7 * 24 * 60 * 60)
        if cached:
            LAST_ODDS_SOURCE = LAST_ODDS_SOURCE or "cache"
            return cached
        return {}

    if prefer_espn or not api_key:
        if not api_key and not prefer_espn:
            print("ODDS_API_KEY is not set — trying ESPN odds fallback")
        espn = fetch_espn_moneyline_market()
        if espn:
            return espn
        if not api_key:
            LAST_ODDS_ERROR = LAST_ODDS_ERROR or "ODDS_API_KEY is not set"
            return {}

    params = urlencode(
        {
            "apiKey": api_key,
            "regions": os.getenv("ODDS_REGIONS", "us"),
            "markets": os.getenv("ODDS_MARKETS", "h2h,spreads,totals"),
            "oddsFormat": "american",
        }
    )

    try:
        with _urlopen(f"{ODDS_API_BASE}?{params}") as response:
            events = json.load(response)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return _fallback_espn_or_cache(f"The Odds API HTTP {error.code}: {body[:240]}")
    except Exception as error:
        return _fallback_espn_or_cache(f"The Odds API request failed: {error}")

    LAST_ODDS_ERROR = None

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

    if market:
        LAST_ODDS_SOURCE = "The Odds API"
        _write_cached_market(market)
        return market

    return _fallback_espn_or_cache("The Odds API returned no events")


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
        with _urlopen(f"{ODDS_HISTORICAL_API_BASE}?{params}") as response:
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
