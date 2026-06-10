"""Load normalized historical MLB odds from local JSONL."""

from __future__ import annotations

import json
from pathlib import Path

from context import MarketSnapshot
from odds_provider import implied_probability

ROOT = Path(__file__).resolve().parents[2]
ODDS_PATH = ROOT / "data" / "historical_odds.jsonl"


def _date_part(value: str | None) -> str:
    return (value or "")[:10]


def _valid_american_odds(value: int) -> bool:
    """Reject malformed imported prices before they create fake ROI."""
    return 100 <= abs(value) <= 2000


class HistoricalOddsStore:
    def __init__(self, path: Path = ODDS_PATH) -> None:
        self.by_matchup: dict[tuple[str, str, str], MarketSnapshot] = {}
        if path.exists():
            self.load(path)

    def date_range(self) -> tuple[str | None, str | None]:
        dates = [key[0] for key in self.by_matchup]
        if not dates:
            return None, None
        return min(dates), max(dates)

    def load(self, path: Path) -> None:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            date_key = _date_part(row.get("start_date"))
            away = str(row.get("away_abbr", "")).upper()
            home = str(row.get("home_abbr", "")).upper()
            home_ml = row.get("closing_home_moneyline")
            away_ml = row.get("closing_away_moneyline")
            if not date_key or not away or not home or home_ml is None or away_ml is None:
                continue
            home_moneyline = int(round(float(home_ml)))
            away_moneyline = int(round(float(away_ml)))
            if not _valid_american_odds(home_moneyline) or not _valid_american_odds(away_moneyline):
                continue

            over_price = int(round(float(row["closing_over_price"]))) if row.get("closing_over_price") is not None else 0
            under_price = int(round(float(row["closing_under_price"]))) if row.get("closing_under_price") is not None else 0
            if not _valid_american_odds(over_price):
                over_price = 0
            if not _valid_american_odds(under_price):
                under_price = 0

            self.by_matchup[(date_key, away, home)] = MarketSnapshot(
                home_moneyline=home_moneyline,
                away_moneyline=away_moneyline,
                home_implied_probability=implied_probability(home_moneyline),
                away_implied_probability=implied_probability(away_moneyline),
                market_total=float(row["closing_total"]) if row.get("closing_total") is not None else 8.5,
                over_price=over_price,
                under_price=under_price,
                source_count=int(row.get("sportsbook_count") or 0),
            )

    def for_game(self, game_date: str, away_abbr: str, home_abbr: str) -> MarketSnapshot:
        return self.by_matchup.get(
            (game_date[:10], away_abbr.upper(), home_abbr.upper()),
            MarketSnapshot(),
        )
