"""PrizePicks-style prop leans — pitcher K + hitter fantasy score."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fantasy_score import estimate_prizepicks_fs_line, estimate_prizepicks_k_line, pick_vs_line, project_hitter_fs
from lineup_provider import featured_hitters
from hitter_stats_provider import hitter_stats_as_of
from mlb_api import fetch_upcoming_games, load_team_abbreviations
from pitcher_stats_provider import pitcher_stats_as_of
from team_stats_provider import team_stats_as_of

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_BOARD = REPO_ROOT / "public" / "predictions.json"
PUBLIC_PROPS = REPO_ROOT / "public" / "prop-leans.json"

EXPECTED_STARTER_IP = 5.5
LEAGUE_K_RATE = 0.223
K_MIN_EDGE = 0.35
FS_MIN_EDGE = 0.75


def _round_half(value: float) -> float:
    return round(value * 2) / 2


def _strikeout_projection(k9: float, opp_k_rate: float, innings: float = EXPECTED_STARTER_IP) -> float:
    opp_adj = 1.0 + (opp_k_rate - LEAGUE_K_RATE) * 1.25
    return max(0.0, k9 * innings / 9.0 * opp_adj)


def _confidence(edge: float, prop: str) -> str:
    if prop == "strikeouts":
        if edge >= 1.25:
            return "high"
        if edge >= 0.75:
            return "medium"
        if edge >= 0.35:
            return "low"
    if prop == "hitter_fantasy_score":
        if edge >= 2.0:
            return "high"
        if edge >= 1.25:
            return "medium"
        if edge >= 0.75:
            return "low"
    return "pass"


def _k_lean(k_proj: float, k9: float, posted_line: float | None = None) -> dict:
    fair = _round_half(k_proj)
    pp_line = posted_line if posted_line is not None else estimate_prizepicks_k_line(k_proj, k9)
    side, edge = pick_vs_line(k_proj, pp_line, min_edge=K_MIN_EDGE)
    return {
        "fair_line": fair,
        "line": pp_line,
        "projection": round(k_proj, 1),
        "lean": side,
        "edge": round(edge, 2),
        "confidence": _confidence(edge, "strikeouts") if side != "Pass" else "pass",
        "line_source": "posted" if posted_line is not None else "prizepicks_est",
    }


def _fs_lean(fs_proj: float, ops: float = 0.720, posted_line: float | None = None) -> dict:
    fair = _round_half(fs_proj)
    pp_line = posted_line if posted_line is not None else estimate_prizepicks_fs_line(fs_proj, ops)
    side, edge = pick_vs_line(fs_proj, pp_line, min_edge=FS_MIN_EDGE)
    return {
        "fair_line": fair,
        "line": pp_line,
        "projection": round(fs_proj, 1),
        "lean": side,
        "edge": round(edge, 2),
        "confidence": _confidence(edge, "hitter_fantasy_score") if side != "Pass" else "pass",
        "line_source": "posted" if posted_line is not None else "prizepicks_est",
    }


def build_prop_leans(board_rows: list[dict], game_date: date) -> dict:
    team_abbr = load_team_abbreviations()
    abbr_to_id = {v.lower(): k for k, v in team_abbr.items()}
    games = {g.game_pk: g for g in fetch_upcoming_games(game_date, game_date)}
    board_by_pk = {}
    for row in board_rows:
        try:
            board_by_pk[int(row["id"].rsplit("-", 1)[-1])] = row
        except (ValueError, KeyError, AttributeError):
            continue

    leans: list[dict] = []
    seen_players: set[str] = set()

    for game_pk, game in games.items():
        if not game.home_pitcher_id or not game.away_pitcher_id:
            continue
        row = board_by_pk.get(game_pk, {})
        home_abbr = team_abbr.get(game.home_team_id, "?")
        away_abbr = team_abbr.get(game.away_team_id, "?")
        home_id = game.home_team_id
        away_id = game.away_team_id

        home_team = team_stats_as_of(home_id, game_date)
        away_team = team_stats_as_of(away_id, game_date)
        projected_total = row.get("projectedTotal") or row.get("marketTotal") or 8.5
        home_runs = projected_total * row.get("modelHomeWinProbability", 0.5) * 0.52
        away_runs = projected_total * row.get("modelAwayWinProbability", 0.5) * 0.52

        home_pit_stats = pitcher_stats_as_of(game.home_pitcher_id, game_date)
        away_pit_stats = pitcher_stats_as_of(game.away_pitcher_id, game_date)

        pitchers = [
            (game.home_pitcher_name, game.home_pitcher_id, away_team.strikeout_rate, away_pit_stats, away_runs, home_abbr, away_abbr),
            (game.away_pitcher_name, game.away_pitcher_id, home_team.strikeout_rate, home_pit_stats, home_runs, away_abbr, home_abbr),
        ]
        for name, pid, opp_k, opp_pit, team_runs, team, opp_abbr in pitchers:
            if not name or name.upper() == "TBD" or name in seen_players:
                continue
            seen_players.add(name)
            k9 = pitcher_stats_as_of(pid, game_date)["strikeouts_per_9"]
            k_proj = _strikeout_projection(k9, opp_k)
            k = _k_lean(k_proj, k9)
            leans.append(
                {
                    "gameId": row.get("id", f"{away_abbr}-{home_abbr}-{game_pk}"),
                    "matchup": f"{away_abbr.upper()} @ {home_abbr.upper()}",
                    "player": name,
                    "team": team.upper(),
                    "prop": "strikeouts",
                    **k,
                    "k9": round(k9, 2),
                }
            )

        # Featured hitters — top OPS bats vs opposing starter
        hitter_pairs = [
            (home_id, away_pit_stats, home_runs, home_abbr, away_abbr, game.away_pitcher_name),
            (away_id, home_pit_stats, away_runs, away_abbr, home_abbr, game.home_pitcher_name),
        ]
        for team_id, opp_pit, team_runs, team, opp_abbr, opp_pitcher in hitter_pairs:
            for hitter_id, hitter_name, _ops in featured_hitters(team_id, game_date):
                if hitter_name in seen_players:
                    continue
                seen_players.add(hitter_name)
                hstats = hitter_stats_as_of(hitter_id, game_date)
                fs_proj = project_hitter_fs(
                    hstats,
                    opp_pitcher_era=float(opp_pit.get("era", 4.35)),
                    opp_pitcher_whip=float(opp_pit.get("whip", 1.28)),
                    implied_team_runs=float(team_runs or 4.5),
                )
                fs = _fs_lean(fs_proj, float(hstats.get("ops", 0.0)))
                leans.append(
                    {
                        "gameId": row.get("id", f"{away_abbr}-{home_abbr}-{game_pk}"),
                        "matchup": f"{away_abbr.upper()} @ {home_abbr.upper()}",
                        "player": hitter_name,
                        "team": team.upper(),
                        "prop": "hitter_fantasy_score",
                        "vs_pitcher": opp_pitcher,
                        **fs,
                        "ops": round(float(hstats.get("ops", 0.0)), 3),
                    }
                )

    actionable = [l for l in leans if l["lean"] in ("Over", "Under")]
    actionable.sort(key=lambda item: (-item.get("edge", 0), item.get("confidence") == "high"))
    leans.sort(key=lambda item: (0 if item["lean"] == "Over" else (1 if item["lean"] == "Under" else 2), -item.get("edge", 0)))

    return {
        "generated_at": game_date.isoformat(),
        "source": "prop-leans-v2",
        "note": "K uses estimated PrizePicks lines when posted line unknown. Hitter FS from top-4 OPS bats per team.",
        "actionable_count": len(actionable),
        "leans": leans,
        "top_plays": [
            {k: l[k] for k in ("player", "prop", "lean", "line", "projection", "edge", "confidence", "matchup") if k in l}
            for l in actionable[:12]
        ],
    }


def main() -> None:
    if not PUBLIC_BOARD.exists():
        print("prop_leans_skip no_board")
        return
    payload = json.loads(PUBLIC_BOARD.read_text())
    rows = payload.get("predictions", [])
    day = date.fromisoformat(payload.get("generated_at") or date.today().isoformat())
    out = build_prop_leans(rows, day)
    PUBLIC_PROPS.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_PROPS.write_text(json.dumps(out, indent=2))
    overs = sum(1 for lean in out["leans"] if lean["lean"] == "Over")
    print(f"prop_leans_ok count={len(out['leans'])} actionable={out['actionable_count']} overs={overs}")


if __name__ == "__main__":
    main()
