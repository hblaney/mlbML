"""Pitcher prop bet cards — 'Brandon Sproat vs PHI → Over 4.5 K'.

Usage:
  python prop_bet.py "Brandon Sproat" --vs PHI
  python prop_bet.py --today
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from generate_prop_leans import (
    EXPECTED_STARTER_IP,
    LEAGUE_K_RATE,
    _round_half,
    _strikeout_projection,
)
from fantasy_score import estimate_prizepicks_k_line, pick_vs_line, project_hitter_fs
from hitter_stats_provider import hitter_stats_as_of
from mlb_api import fetch_upcoming_games, load_team_abbreviations, load_team_names
from pitcher_stats_provider import pitcher_stats_as_of
from team_stats_provider import team_stats_as_of
from trained_edge_model import _safe_pitcher_stats

REPO = Path(__file__).resolve().parents[2]
PUBLIC_OUT = REPO / "public" / "prop-bet-cards.json"

# Nickname / city aliases → MLB abbr (lowercase keys)
OPP_ALIASES: dict[str, str] = {
    "phillies": "phi", "philadelphia": "phi", "philly": "phi",
    "mets": "nym", "yankees": "nyy", "dodgers": "lad", "red sox": "bos",
    "cubs": "chc", "white sox": "cws", "guardians": "cle", "athletics": "oak",
    "astros": "hou", "braves": "atl", "orioles": "bal", "rays": "tb",
    "mariners": "sea", "twins": "min", "brewers": "mil", "reds": "cin",
    "pirates": "pit", "nationals": "wsh", "rockies": "col", "dbacks": "ari",
    "diamondbacks": "ari", "padres": "sd", "giants": "sf", "royals": "kc",
    "tigers": "det", "rangers": "tex", "angels": "laa", "marlins": "mia",
    "blue jays": "tor", "cardinals": "stl",
}


@dataclass
class PropBetCard:
    player: str
    team: str
    opponent: str
    matchup: str
    game_date: str
    props: list[dict]
    headline: str
    notes: list[str]


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z ]", "", name.lower()).strip()


def _name_matches(query: str, full_name: str) -> bool:
    q = _normalize_name(query)
    n = _normalize_name(full_name)
    if not q or not n:
        return False
    if q in n or n in q:
        return True
    # last-name match: "sproat" matches "brandon sproat"
    q_parts = q.split()
    n_parts = n.split()
    if len(q_parts) == 1 and q_parts[0] in n_parts:
        return True
    if len(n_parts) >= 2 and q == n_parts[-1]:
        return True
    return False


def _resolve_opponent(token: str, abbr_map: dict[int, str]) -> str | None:
    t = token.strip().lower()
    if t in OPP_ALIASES:
        return OPP_ALIASES[t]
    rev = {v.lower(): v.lower() for v in abbr_map.values()}
    if t in rev:
        return t
    for abbr in abbr_map.values():
        if abbr.lower() == t:
            return abbr.lower()
    return None


def _find_game_for_pitcher(
    pitcher_query: str,
    game_date: date,
    vs: str | None,
    abbr_map: dict[int, str],
    names_map: dict[int, str],
) -> tuple[object, str, str, int] | None:
    """Return (game, pitcher_name, team_abbr, pitcher_id, opp_abbr)."""
    opp = _resolve_opponent(vs, abbr_map) if vs else None

    for game in fetch_upcoming_games(game_date, game_date):
        for pid, pname, tid, opp_id in (
            (game.home_pitcher_id, game.home_pitcher_name, game.home_team_id, game.away_team_id),
            (game.away_pitcher_id, game.away_pitcher_name, game.away_team_id, game.home_team_id),
        ):
            if not pid or not pname:
                continue
            if not _name_matches(pitcher_query, pname):
                continue
            team_abbr = abbr_map.get(tid, "?").lower()
            opp_abbr = abbr_map.get(opp_id, "?").lower()
            if opp and opp_abbr != opp and team_abbr != opp:
                continue
            return game, pname, team_abbr, pid, opp_abbr
    return None


def _confidence(edge: float, prop: str) -> str:
    if prop == "strikeouts":
        if edge >= 1.0:
            return "high"
        if edge >= 0.5:
            return "medium"
        if edge >= 0.25:
            return "low"
    return "pass"


def _pick_vs_line(projection: float, default_line: float) -> tuple[str, float, float, str]:
    """Return side, recommended PrizePicks-style line, edge, confidence."""
    line = _round_half(default_line)
    edge = projection - line
    if projection >= line + 0.25:
        return "Over", line, edge, _confidence(edge, "strikeouts")
    if projection <= line - 0.25:
        return "Under", line, -edge, _confidence(abs(edge), "strikeouts")
    return "Pass", line, edge, "pass"


def build_pitcher_card(
    pitcher_name: str,
    game_date: date | None = None,
    vs: str | None = None,
    prizepicks_line: float | None = None,
) -> PropBetCard | None:
    game_date = game_date or date.today()
    abbr_map = load_team_abbreviations()
    names_map = load_team_names()

    found = _find_game_for_pitcher(pitcher_name, game_date, vs, abbr_map, names_map)
    if not found:
        return None

    game, pname, team_abbr, pid, opp_abbr = found
    my_id = game.home_team_id if game.home_pitcher_id == pid else game.away_team_id
    opp_id = game.away_team_id if game.home_team_id == my_id else game.home_team_id
    opp_abbr = abbr_map.get(opp_id, opp_abbr).lower()
    team_abbr = abbr_map.get(my_id, team_abbr).upper()

    pit_stats = pitcher_stats_as_of(pid, game_date)
    opp_team = team_stats_as_of(opp_id, game_date)
    k_proj = _strikeout_projection(pit_stats["strikeouts_per_9"], opp_team.strikeout_rate)
    model_line = _round_half(k_proj)
    k9 = pit_stats["strikeouts_per_9"]
    pp_line = prizepicks_line if prizepicks_line is not None else estimate_prizepicks_k_line(k_proj, k9)
    side, edge = pick_vs_line(k_proj, pp_line, min_edge=0.35)
    conf = _confidence(abs(edge), "strikeouts") if side != "Pass" else "pass"

    # Pitcher outs: ~3 outs per IP
    exp_ip = EXPECTED_STARTER_IP
    outs_proj = exp_ip * 3.0
    outs_line = _round_half(outs_proj - 0.5)  # e.g. 16.5

    props: list[dict] = []
    notes: list[str] = []

    if side != "Pass":
        props.append({
            "prop": "strikeouts",
            "pick": side,
            "model_line": model_line,
            "use_line": pp_line,
            "projection": round(k_proj, 1),
            "edge": round(edge, 2),
            "confidence": conf,
            "k9": round(k9, 2),
            "opp_k_rate": round(opp_team.strikeout_rate, 3),
        })

    if side == "Pass":
        notes.append(f"Projection {k_proj:.1f} K — too close to line {pp_line:.1f}; wait for better number on PrizePicks.")

    if not game.home_pitcher_id or not game.away_pitcher_id:
        notes.append("Probable starter not fully confirmed — verify before betting.")

    away = abbr_map.get(game.away_team_id, "?")
    home = abbr_map.get(game.home_team_id, "?")
    matchup = f"{away} @ {home}"

    headline = "NO BET — edge too thin"
    if props:
        p = props[0]
        headline = f"{p['pick']} {p['use_line']} {p['prop'].upper()} ({p['confidence']} confidence)"

    return PropBetCard(
        player=pname,
        team=team_abbr,
        opponent=opp_abbr.upper(),
        matchup=matchup,
        game_date=game_date.isoformat(),
        props=props,
        headline=headline,
        notes=notes,
    )


def build_all_starters(game_date: date | None = None) -> list[PropBetCard]:
    game_date = game_date or date.today()
    abbr_map = load_team_abbreviations()
    cards: list[PropBetCard] = []
    seen: set[str] = set()

    for game in fetch_upcoming_games(game_date, game_date):
        for pname in (game.home_pitcher_name, game.away_pitcher_name):
            if not pname or pname.upper() == "TBD" or pname in seen:
                continue
            seen.add(pname)
            card = build_pitcher_card(pname, game_date)
            if card and card.props:
                cards.append(card)
    cards.sort(key=lambda c: -max(p.get("edge", 0) for p in c.props))
    return cards


def save_cards(cards: list[PropBetCard], game_date: date) -> Path:
    PUBLIC_OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": game_date.isoformat(),
        "source": "prop-bet-card-v1",
        "disclaimer": "Compare use_line to PrizePicks posted line before playing.",
        "cards": [asdict(c) for c in cards],
    }
    PUBLIC_OUT.write_text(json.dumps(payload, indent=2))
    return PUBLIC_OUT


def print_card(card: PropBetCard) -> None:
    print(f"\n{'='*56}")
    print(f"  {card.player} ({card.team}) vs {card.opponent}")
    print(f"  {card.matchup}  |  {card.game_date}")
    print(f"{'='*56}")
    if not card.props:
        print(f"  {card.headline}")
    for p in card.props:
        print(f"\n  BET: {p['pick']} {p['use_line']} {p['prop'].upper()}")
        print(f"       Projection: {p['projection']}  |  Edge: {p['edge']:+.1f}")
        print(f"       K/9: {p['k9']}  vs opp K%: {p['opp_k_rate']:.1%}")
        print(f"       Confidence: {p['confidence']}")
    for n in card.notes:
        print(f"  ⚠ {n}")
    print(f"\n  → On PrizePicks: find {card.player}, check K line vs {card.props[0]['use_line'] if card.props else '?'}")


def main() -> None:
    p = argparse.ArgumentParser(description="MLB pitcher prop bet card")
    p.add_argument("pitcher", nargs="?", help='e.g. "Brandon Sproat"')
    p.add_argument("--vs", help="Opponent abbr or name, e.g. PHI or phillies")
    p.add_argument("--line", type=float, help="PrizePicks posted K line (e.g. 4.5)")
    p.add_argument("--today", action="store_true", help="All starters today")
    p.add_argument("--date", help="YYYY-MM-DD (default today)")
    args = p.parse_args()

    gd = date.fromisoformat(args.date) if args.date else date.today()

    if args.today:
        cards = build_all_starters(gd)
        save_cards(cards, gd)
        print(f"Prop bet cards: {len(cards)} with actionable leans")
        for c in cards[:15]:
            print_card(c)
        print(f"\nSaved → {PUBLIC_OUT}")
        return

    if not args.pitcher:
        p.error("Provide a pitcher name or use --today")

    card = build_pitcher_card(args.pitcher, gd, vs=args.vs, prizepicks_line=args.line)
    if not card:
        print(f"No game found for '{args.pitcher}' on {gd}" + (f" vs {args.vs}" if args.vs else ""))
        return
    print_card(card)
    save_cards([card], gd)


if __name__ == "__main__":
    main()
