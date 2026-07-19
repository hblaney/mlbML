"""Daily prop predictions + PrizePicks parlay, edged against REAL market lines.

Pipeline:
  1. Pull real, de-vigged player-prop lines (prop_odds_provider).
  2. Project each prop from leakage-safe stats (prop_projections) using the real
     opposing starter + park.
  3. Compute edge = model P(side) − market P(side) on the side we lean, and EV at
     the real price.
  4. Publish every actionable lean and build a daily parlay that ALWAYS fields a
     card (no skips) from the strongest +edge legs.

Outputs public/prop-predictions.json.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from mlb_api import fetch_upcoming_games, load_team_abbreviations
from pitcher_stats_provider import pitcher_stats_as_of
from prop_odds_provider import fetch_prop_lines
from prop_projections import project_prop

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "public" / "prop-predictions.json"
ARCHIVE_DIR = REPO_ROOT / "data" / "prop-predictions"

# Only publish a lean when we genuinely disagree with the de-vigged market by this
# much probability, and only trust markets priced by >=2 books.
MIN_EDGE = 0.04
MIN_BOOK_COUNT = 2
# Parlay legs must be likely to hit AND carry real edge.
PARLAY_MIN_PROB = 0.56
PARLAY_MIN_EDGE = 0.03
PARLAY_TARGET_LEGS = 3
PARLAY_MAX_LEGS = 5
PARLAY_MIN_LEGS = 2

PRETTY = {
    "pitcher_strikeouts": "Strikeouts",
    "pitcher_outs": "Outs",
    "pitcher_earned_runs": "Earned Runs",
    "pitcher_hits_allowed": "Hits Allowed",
    "batter_hits": "Hits",
    "batter_total_bases": "Total Bases",
    "batter_home_runs": "Home Runs",
    "batter_rbis": "RBIs",
    "batter_runs_scored": "Runs",
    "batter_walks": "Walks",
    "batter_stolen_bases": "Stolen Bases",
    "batter_singles": "Singles",
    "batter_doubles": "Doubles",
    "batter_hits_runs_rbis": "Hits+Runs+RBIs",
}


def _implied(american: float) -> float:
    if american == 0:
        return 0.0
    if american < 0:
        return abs(american) / (abs(american) + 100.0)
    return 100.0 / (american + 100.0)


def _decimal(american: int) -> float:
    if american == 0:
        return 2.0
    if american < 0:
        return 1.0 + 100.0 / abs(american)
    return 1.0 + american / 100.0


def _confidence(edge: float, book_count: int) -> str:
    if edge >= 0.09 and book_count >= 3:
        return "Elite"
    if edge >= 0.06:
        return "High"
    if edge >= 0.04:
        return "Medium"
    return "Low"


def _park_hr_factor(home_team_id: int | None) -> float:
    if home_team_id is None:
        return 1.0
    try:
        from park_factors import park_for_team
        park = park_for_team(home_team_id)
        return getattr(park, "park_factor_hr", 1.0) or 1.0
    except Exception:
        return 1.0


def build_predictions(game_date: date) -> list[dict]:
    lines = fetch_prop_lines()
    if not lines:
        return []

    abbr_by_id = load_team_abbreviations()
    id_by_abbr = {v: k for k, v in abbr_by_id.items()}

    # Map (away_abbr, home_abbr) -> probable pitcher ids + park.
    games = fetch_upcoming_games(game_date, game_date)
    starters: dict[tuple[str, str], dict] = {}
    for g in games:
        ha = abbr_by_id.get(g.home_team_id)
        aa = abbr_by_id.get(g.away_team_id)
        if not ha or not aa:
            continue
        starters[(aa, ha)] = {
            "home_pitcher_id": g.home_pitcher_id,
            "away_pitcher_id": g.away_pitcher_id,
            "home_team_id": g.home_team_id,
        }

    predictions: list[dict] = []
    starter_cache: dict[int, dict] = {}

    def starter_stats(pid: int | None) -> dict | None:
        if not pid:
            return None
        if pid not in starter_cache:
            try:
                starter_cache[pid] = pitcher_stats_as_of(pid, game_date)
            except Exception:
                starter_cache[pid] = {}
        return starter_cache[pid]

    for line in lines:
        if line.player_id is None or line.book_count < MIN_BOOK_COUNT:
            continue
        game_key = (line.away_abbr, line.home_abbr)
        game_meta = starters.get(game_key, {})
        home_team_id = game_meta.get("home_team_id") or id_by_abbr.get(line.home_abbr)
        park_hr = _park_hr_factor(home_team_id)

        # Opposing starter for a hitter = probable pitcher of the OTHER team.
        opp_starter = None
        if line.prop.startswith("batter_"):
            if line.is_home is True:
                opp_starter = starter_stats(game_meta.get("away_pitcher_id"))
            elif line.is_home is False:
                opp_starter = starter_stats(game_meta.get("home_pitcher_id"))

        proj = project_prop(line, game_date, opp_starter, park_hr)
        if proj is None:
            continue

        # Decide side vs the de-vigged market.
        model_over = proj.prob_over
        market_over = line.market_prob_over
        if model_over >= market_over:
            side = "Over"
            model_p = model_over
            market_p = market_over
            price = line.over_price
        else:
            side = "Under"
            model_p = 1.0 - model_over
            market_p = 1.0 - market_over
            price = line.under_price

        edge = model_p - market_p
        if edge < MIN_EDGE:
            continue
        ev = model_p * (_decimal(price) - 1.0) - (1.0 - model_p)

        predictions.append(
            {
                "game_id": line.game_id,
                "matchup": f"{line.away_abbr} @ {line.home_abbr}",
                "commence_time": line.commence_time,
                "player": line.player,
                "player_id": line.player_id,
                "team": line.team_abbr,
                "opp": line.opp_abbr,
                "prop": line.prop,
                "prop_label": PRETTY.get(line.prop, line.prop),
                "line": line.line,
                "side": side,
                "pick": f"{side} {line.line}",
                "projection": proj.projection,
                "model_prob": round(model_p, 4),
                "market_prob": round(market_p, 4),
                "edge": round(edge, 4),
                "price": price,
                "ev": round(ev, 4),
                "confidence": _confidence(edge, line.book_count),
                "book_count": line.book_count,
                "note": proj.model_note,
            }
        )

    predictions.sort(key=lambda p: (p["edge"], p["model_prob"]), reverse=True)
    return predictions


def build_parlay(predictions: list[dict]) -> dict:
    """Always field a card: strongest +edge, likely-to-hit legs across games."""
    def leg_ok(p: dict) -> bool:
        return p["model_prob"] >= PARLAY_MIN_PROB and p["edge"] >= PARLAY_MIN_EDGE

    pool = [p for p in predictions if leg_ok(p)]
    # Rank by likelihood first (we want it to hit), then edge.
    pool.sort(key=lambda p: (p["model_prob"], p["edge"]), reverse=True)

    # Relax progressively so we NEVER skip when props exist.
    if len(pool) < PARLAY_MIN_LEGS:
        pool = sorted(
            [p for p in predictions if p["edge"] > 0],
            key=lambda p: (p["model_prob"], p["edge"]),
            reverse=True,
        )
    if len(pool) < PARLAY_MIN_LEGS:
        pool = sorted(predictions, key=lambda p: (p["model_prob"], p["edge"]), reverse=True)

    legs: list[dict] = []
    seen_players: set[str] = set()
    for p in pool:
        if len(legs) >= PARLAY_TARGET_LEGS:
            break
        key = f"{p['player']}|{p['prop']}"
        if key in seen_players:
            continue
        # avoid stacking >2 legs from the same game
        same_game = sum(1 for l in legs if l["matchup"] == p["matchup"])
        if same_game >= 2:
            continue
        seen_players.add(key)
        legs.append(p)

    if len(legs) < PARLAY_MIN_LEGS:
        for p in pool:
            key = f"{p['player']}|{p['prop']}"
            if key in seen_players:
                continue
            seen_players.add(key)
            legs.append(p)
            if len(legs) >= PARLAY_MIN_LEGS:
                break

    combined = 1.0
    for l in legs:
        combined *= l["model_prob"]

    return {
        "type": "power" if len(legs) <= 3 else "flex",
        "n_legs": len(legs),
        "combined_prob": round(combined, 4),
        "legs": legs,
    }


def main() -> None:
    game_date = date.today()
    predictions = build_predictions(game_date)
    parlay = build_parlay(predictions) if predictions else {"n_legs": 0, "legs": []}
    payload = {
        "generated_at": game_date.isoformat(),
        "board_generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "the-odds-api player props (de-vigged) + leakage-safe projections",
        "count": len(predictions),
        "min_edge": MIN_EDGE,
        "parlay": parlay,
        "predictions": predictions,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2))

    # Archive today's board once (first publish wins) so the grader can settle it
    # later against real results without being overwritten by intraday refreshes.
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = ARCHIVE_DIR / f"{game_date.isoformat()}.json"
    if not archive_path.exists():
        archive_path.write_text(json.dumps(payload, indent=2))

    print(f"prop_predictions_ok count={len(predictions)} parlay_legs={parlay.get('n_legs')}")
    for l in parlay.get("legs", []):
        print(f"  {l['player']:22s} {l['prop_label']:14s} {l['pick']:10s} "
              f"model={l['model_prob']:.2f} mkt={l['market_prob']:.2f} edge={l['edge']:+.3f} conf={l['confidence']}")


if __name__ == "__main__":
    main()
