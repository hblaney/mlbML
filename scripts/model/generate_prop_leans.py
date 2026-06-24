"""Lightweight PrizePicks-style prop leans from board + MLB stats (K, implied TB)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from mlb_api import fetch_upcoming_games, load_team_abbreviations
from pitcher_stats_provider import pitcher_stats_as_of
from team_stats_provider import team_stats_as_of
from trained_edge_model import _safe_pitcher_stats

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_BOARD = REPO_ROOT / "public" / "predictions.json"
PUBLIC_PROPS = REPO_ROOT / "public" / "prop-leans.json"

EXPECTED_STARTER_IP = 5.5
LEAGUE_K_RATE = 0.223


def _round_half(value: float) -> float:
    return round(value * 2) / 2


def _strikeout_projection(k9: float, opp_k_rate: float, innings: float = EXPECTED_STARTER_IP) -> float:
    opp_adj = 1.0 + (opp_k_rate - LEAGUE_K_RATE) * 1.25
    return max(0.0, k9 * innings / 9.0 * opp_adj)


def _total_bases_projection(slg: float, implied_team_runs: float, plate_appearances: float = 4.2) -> float:
    # Rough: SLG × PA scaled by run environment vs league ~4.5 R/G.
    run_env = max(0.85, min(1.15, implied_team_runs / 4.5))
    return slg * plate_appearances * run_env


def build_prop_leans(board_rows: list[dict], game_date: date) -> dict:
    team_abbr = load_team_abbreviations()
    abbr_to_id = {v.lower(): k for k, v in team_abbr.items()}
    games = {g.game_pk: g for g in fetch_upcoming_games(game_date, game_date)}

    leans: list[dict] = []
    for row in board_rows:
        if not row.get("starterCertain"):
            continue
        game_pk = int(row["id"].rsplit("-", 1)[-1])
        game = games.get(game_pk)
        if game is None:
            continue

        home_abbr = row["homeTeam"]
        away_abbr = row["awayTeam"]
        home_id = abbr_to_id.get(home_abbr)
        away_id = abbr_to_id.get(away_abbr)
        if home_id is None or away_id is None:
            continue

        home_team = team_stats_as_of(home_id, game_date)
        away_team = team_stats_as_of(away_id, game_date)
        home_pit = _safe_pitcher_stats(game, game.home_pitcher_id)
        away_pit = _safe_pitcher_stats(game, game.away_pitcher_id)
        projected_total = row.get("projectedTotal") or row.get("marketTotal") or 8.5
        home_runs = projected_total * row.get("modelHomeWinProbability", 0.5) * 0.52
        away_runs = projected_total * row.get("modelAwayWinProbability", 0.5) * 0.52

        pitchers = [
            (row["homePitcher"], home_pit, away_team.strikeout_rate, home_runs, home_abbr),
            (row["awayPitcher"], away_pit, home_team.strikeout_rate, away_runs, away_abbr),
        ]
        for name, stats, opp_k, team_runs, team in pitchers:
            if not name or name.upper() == "TBD":
                continue
            k_proj = _strikeout_projection(stats["strikeouts_per_9"], opp_k)
            k_line = _round_half(k_proj)
            leans.append(
                {
                    "gameId": row["id"],
                    "matchup": f"{away_abbr.upper()} @ {home_abbr.upper()}",
                    "player": name,
                    "team": team.upper(),
                    "prop": "strikeouts",
                    "line": k_line,
                    "projection": round(k_proj, 1),
                    "lean": "Over" if k_proj >= k_line + 0.25 else ("Under" if k_proj <= k_line - 0.25 else "Pass"),
                    "k9": round(stats["strikeouts_per_9"], 2),
                }
            )

        # Team-level TB lean for the model's predicted side (no lineup data yet).
        pick = row.get("predictedTeam", "")
        if pick == home_abbr:
            slg = home_team.slg
            runs = home_runs
            label = f"{home_abbr.upper()} top hitter TB proxy"
        elif pick == away_abbr:
            slg = away_team.slg
            runs = away_runs
            label = f"{away_abbr.upper()} top hitter TB proxy"
        else:
            continue
        tb_proj = _total_bases_projection(slg, runs)
        tb_line = _round_half(max(0.5, tb_proj - 0.3))
        leans.append(
            {
                "gameId": row["id"],
                "matchup": f"{away_abbr.upper()} @ {home_abbr.upper()}",
                "player": label,
                "team": pick.upper(),
                "prop": "total_bases",
                "line": tb_line,
                "projection": round(tb_proj, 1),
                "lean": "Over" if tb_proj >= tb_line + 0.2 else "Pass",
                "note": "Team SLG proxy until lineup module ships",
            }
        )

    leans.sort(key=lambda item: (0 if item["lean"] == "Over" else 1, -item.get("projection", 0)))
    return {
        "generated_at": game_date.isoformat(),
        "source": "prop-leans-v1",
        "note": "Heuristic K/TB leans from point-in-time pitcher K/9 and team SLG — not locked bets.",
        "leans": leans,
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
    print(f"prop_leans_ok count={len(out['leans'])} overs={overs}")


if __name__ == "__main__":
    main()
