"""Extra pregame signals: opening lines, injuries, Statcast matchup, pitcher whiff.

All features are point-in-time safe (no closing-line lookahead in the training row).
Opening implied probs come from morning lines in historical_odds.jsonl.
Injuries are live-only (0 on historical dates until we archive snapshots).
Statcast uses rolling team metrics through yesterday.
"""

from __future__ import annotations

from datetime import date

from injuries_provider import injury_counts_for_game
from mlb_api import GameRecord, load_team_abbreviations
from odds_provider import implied_probability
from statcast_provider import StatcastTeamCache, normalize_team_abbr
from team_tracker import LeagueState

SIGNAL_FEATURE_COUNT = 10

_STATCAST_CACHE: StatcastTeamCache | None = None
_TEAM_ABBR: dict[int, str] | None = None


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _statcast_cache() -> StatcastTeamCache:
    global _STATCAST_CACHE
    if _STATCAST_CACHE is None:
        _STATCAST_CACHE = StatcastTeamCache()
    return _STATCAST_CACHE


def _team_abbr_map() -> dict[int, str]:
    global _TEAM_ABBR
    if _TEAM_ABBR is None:
        _TEAM_ABBR = load_team_abbreviations()
    return _TEAM_ABBR


def no_vig_probs(home_ml: int, away_ml: int) -> tuple[float, float]:
    home = implied_probability(home_ml)
    away = implied_probability(away_ml)
    total = home + away
    if total <= 0:
        return 0.5, 0.5
    return home / total, away / total


def opening_probs_for_game(
    game: GameRecord,
    opening_index: dict[tuple[str, str, str], tuple[int, int]] | None,
) -> tuple[float, float]:
    """Morning opening no-vig probs; 0.5/0.5 when unavailable."""
    if not opening_index:
        return 0.5, 0.5
    abbr = _team_abbr_map()
    away = abbr.get(game.away_team_id, "").upper()
    home = abbr.get(game.home_team_id, "").upper()
    if not away or not home:
        return 0.5, 0.5
    date_key = game.game_date.isoformat()
    for key in ((date_key, away, home),):
        hit = opening_index.get(key)
        if hit:
            return no_vig_probs(hit[0], hit[1])
    return 0.5, 0.5


def statcast_matchup_features(game: GameRecord) -> tuple[float, float, float, float, float]:
    """Five high-signal Statcast matchup deltas (14/30-day windows)."""
    if game.game_date.year < 2015:
        return (0.0, 0.0, 0.0, 0.0, 0.0)
    abbr = _team_abbr_map()
    home = normalize_team_abbr(abbr.get(game.home_team_id, ""))
    away = normalize_team_abbr(abbr.get(game.away_team_id, ""))
    if not home or not away:
        return (0.0, 0.0, 0.0, 0.0, 0.0)
    try:
        cache = _statcast_cache()
        feature_map = cache.feature_map(home, away, game.game_date)
    except Exception:
        return (0.0, 0.0, 0.0, 0.0, 0.0)
    return (
        float(feature_map.get("statcast_xwoba_delta_last_14", 0.0)),
        float(feature_map.get("statcast_offense_edge_last_14", 0.0)),
        float(feature_map.get("statcast_contact_edge_last_14", 0.0)),
        float(feature_map.get("statcast_whiff_rate_delta_last_14", 0.0)),
        float(feature_map.get("statcast_hard_hit_rate_delta_last_30", 0.0)),
    )


def injury_features(game: GameRecord) -> tuple[float, float, float]:
    home_count, away_count = injury_counts_for_game(
        game.home_team_id,
        game.away_team_id,
        snapshot_date=game.game_date,
    )
    home_norm = _clip(home_count / 8.0, 0.0, 1.0)
    away_norm = _clip(away_count / 8.0, 0.0, 1.0)
    return home_norm, away_norm, _clip((away_count - home_count) / 8.0, -1.0, 1.0)


def signal_feature_row(
    game: GameRecord,
    league: LeagueState,
    *,
    opening_index: dict[tuple[str, str, str], tuple[int, int]] | None = None,
) -> list[float]:
    open_home, open_away = opening_probs_for_game(game, opening_index)
    inj_home, inj_away, inj_delta = injury_features(game)
    sc_xwoba, sc_offense, sc_contact, sc_whiff, sc_hard = statcast_matchup_features(game)
    return [
        _clip(open_home, 0.05, 0.95),
        _clip(open_away, 0.05, 0.95),
        inj_home,
        inj_away,
        inj_delta,
        _clip(sc_xwoba, -0.15, 0.15),
        _clip(sc_offense, -0.15, 0.15),
        _clip(sc_contact, -0.15, 0.15),
        _clip(sc_whiff, -0.15, 0.15),
        _clip(sc_hard, -0.15, 0.15),
    ]


def build_opening_index_from_odds_store(odds_store) -> dict[tuple[str, str, str], tuple[int, int]]:
    """Build lookup from HistoricalOddsStore.opening_by_matchup."""
    index: dict[tuple[str, str, str], tuple[int, int]] = {}
    opening = getattr(odds_store, "opening_by_matchup", None)
    if not opening:
        return index
    for key, pair in opening.items():
        index[key] = pair
    return index
