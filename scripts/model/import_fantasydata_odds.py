"""Import visible FantasyData MLB odds rows into historical_odds.jsonl.

FantasyData exposes a public MLB odds table with current/recent consensus rows.
This importer is intentionally conservative: it only writes rows with complete
final scores and moneyline prices, then leaves existing rows untouched.
"""

from __future__ import annotations

import json
import ssl
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

import certifi
from bs4 import BeautifulSoup


def _urlopen(request: Request, *, timeout: int = 30):
    context = ssl.create_default_context(cafile=certifi.where())
    return urlopen(request, timeout=timeout, context=context)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "data" / "historical_odds.jsonl"
FANTASYDATA_URL = "https://fantasydata.com/mlb/odds"
TEAM_ODDS_PATHS = [
    "arizona-diamondbacks",
    "athletics",
    "atlanta-braves",
    "baltimore-orioles",
    "boston-red-sox",
    "chicago-cubs",
    "chicago-white-sox",
    "cincinnati-reds",
    "cleveland-guardians",
    "colorado-rockies",
    "detroit-tigers",
    "houston-astros",
    "kansas-city-royals",
    "los-angeles-angels",
    "los-angeles-dodgers",
    "miami-marlins",
    "milwaukee-brewers",
    "minnesota-twins",
    "new-york-mets",
    "new-york-yankees",
    "philadelphia-phillies",
    "pittsburgh-pirates",
    "san-diego-padres",
    "san-francisco-giants",
    "seattle-mariners",
    "st-louis-cardinals",
    "tampa-bay-rays",
    "texas-rangers",
    "toronto-blue-jays",
    "washington-nationals",
]

TEAM_ALIASES = {
    "ARI": "ARI",
    "ATH": "ATH",
    "ATL": "ATL",
    "BAL": "BAL",
    "BOS": "BOS",
    "CHC": "CHC",
    "CHW": "CHW",
    "CWS": "CWS",
    "CIN": "CIN",
    "CLE": "CLE",
    "COL": "COL",
    "DET": "DET",
    "HOU": "HOU",
    "KC": "KC",
    "LAA": "LAA",
    "LAD": "LAD",
    "MIA": "MIA",
    "MIL": "MIL",
    "MIN": "MIN",
    "NYM": "NYM",
    "NYY": "NYY",
    "OAK": "ATH",
    "PHI": "PHI",
    "PIT": "PIT",
    "SD": "SD",
    "SEA": "SEA",
    "SF": "SF",
    "STL": "STL",
    "TB": "TB",
    "TEX": "TEX",
    "TOR": "TOR",
    "WSH": "WSH",
}


def parse_price(value: str) -> int | None:
    text = value.strip().replace("+", "")
    if not text:
        return None
    try:
        price = int(text)
    except ValueError:
        return None
    if 100 <= abs(price) <= 2000:
        return price
    return None


def parse_float(value: str) -> float | None:
    try:
        return float(value.strip())
    except ValueError:
        return None


def team_abbr(cell_text: str) -> str | None:
    # FantasyData visible text is usually "TigersDET" or just "DET".
    for suffix in sorted(TEAM_ALIASES, key=len, reverse=True):
        if cell_text.strip().upper().endswith(suffix):
            return TEAM_ALIASES[suffix]
    return TEAM_ALIASES.get(cell_text.strip().upper())


def parse_date(value: str) -> str | None:
    try:
        parsed = datetime.strptime(value.strip(), "%b %d, %Y")
    except ValueError:
        return None
    return parsed.date().isoformat()


def existing_keys() -> set[tuple[str, str, str]]:
    if not OUTPUT_PATH.exists():
        return set()
    keys: set[tuple[str, str, str]] = set()
    for line in OUTPUT_PATH.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        keys.add((str(row.get("start_date", ""))[:10], str(row.get("away_abbr", "")).upper(), str(row.get("home_abbr", "")).upper()))
    return keys


def fetch_rows_for_url(url: str) -> list[dict]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with _urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")

    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for tr in soup.select("tbody tr"):
        cells = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all("td")]
        if len(cells) < 14:
            continue

        away = team_abbr(cells[0])
        home = team_abbr(cells[1])
        date_key = parse_date(cells[2])
        away_score = parse_float(cells[3])
        home_score = parse_float(cells[4])
        # The league page has moneyline at indexes 9/10. Team pages include an
        # extra empty spacer cell before moneyline, shifting these fields by 1.
        moneyline_offset = 1 if len(cells) > 14 and not cells[9].strip() else 0
        away_ml = parse_price(cells[9 + moneyline_offset])
        home_ml = parse_price(cells[10 + moneyline_offset])
        market_total = parse_float(cells[11 + moneyline_offset])
        over_price = parse_price(cells[12 + moneyline_offset])
        under_price = parse_price(cells[13 + moneyline_offset])

        if not away or not home or not date_key or away_score is None or home_score is None:
            continue
        if away_ml is None or home_ml is None:
            continue

        rows.append(
            {
                "start_date": date_key,
                "game_type": "R",
                "away_team": away,
                "away_abbr": away,
                "home_team": home,
                "home_abbr": home,
                "away_score": int(away_score),
                "home_score": int(home_score),
                "venue": None,
                "opening_home_moneyline": None,
                "opening_away_moneyline": None,
                "closing_home_moneyline": home_ml,
                "closing_away_moneyline": away_ml,
                "closing_total": market_total,
                "closing_over_price": over_price,
                "closing_under_price": under_price,
                "sportsbook_count": 1,
                "sportsbooks": ["FantasyData consensus"],
                "source": "fantasydata_visible_table",
                "source_url": url,
            }
        )
    return rows


def fetch_rows() -> list[dict]:
    by_key: dict[tuple[str, str, str], dict] = {}
    urls = [FANTASYDATA_URL, *[f"https://fantasydata.com/mlb/{slug}-odds" for slug in TEAM_ODDS_PATHS]]
    for url in urls:
        try:
            rows = fetch_rows_for_url(url)
        except Exception as error:
            print(f"fantasydata_fetch_failed={url} error={error}")
            continue
        print(f"fantasydata_url_rows={len(rows)} url={url}")
        for row in rows:
            key = (row["start_date"][:10], row["away_abbr"].upper(), row["home_abbr"].upper())
            by_key[key] = row
    return list(by_key.values())


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    keys = existing_keys()
    rows = fetch_rows()
    new_rows = [
        row
        for row in rows
        if (row["start_date"][:10], row["away_abbr"].upper(), row["home_abbr"].upper()) not in keys
    ]

    with OUTPUT_PATH.open("a") as handle:
        for row in new_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    print(f"fantasydata_rows={len(rows)}")
    print(f"fantasydata_new_rows={len(new_rows)}")
    if rows:
        dates = sorted({row["start_date"][:10] for row in rows})
        print(f"fantasydata_date_range={dates[0]}..{dates[-1]}")


if __name__ == "__main__":
    main()
