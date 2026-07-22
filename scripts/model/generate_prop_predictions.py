"""Daily prop predictions + PrizePicks parlay.

Primary board: live PrizePicks standard MLB lines (partner API).
Fallback: de-vigged sportsbook props from The Odds API.

Pipeline:
  1. Pull PrizePicks standard lines (or odds-api fallback).
  2. Project each prop from leakage-safe stats + matchup context.
  3. Edge vs a pick'em prior (0.5) on PrizePicks, or vs de-vigged books on fallback.
  4. Publish Top 5 + 5-leg Flex from the accuracy lane.

Outputs public/prop-predictions.json.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from mlb_api import fetch_upcoming_games, load_team_abbreviations
from pitcher_stats_provider import pitcher_stats_as_of
from prop_odds_provider import (
    PropLine,
    fetch_prop_lines,
    _norm_abbr,
    _norm_name,
    _same_team,
    _roster_name_map,
)
from prop_projections import project_prop
from prop_env import env_multipliers
from bullpen_provider import bullpen_stats_as_of
from lineup_provider import (
    confirmed_lineup,
    confirmed_lineup_by_team,
    expected_pa_for_player,
)
from player_statcast_provider import hitter_quality
from handedness_provider import pitcher_throws, batter_bat_side
from prop_calibration import calibrate
from prizepicks_provider import fetch_prizepicks_lines
from hitter_stats_provider import hitter_last_n_total_bases
from prop_publish_guards import scrub_predictions, assert_payload_sane

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "public" / "prop-predictions.json"
ARCHIVE_DIR = REPO_ROOT / "data" / "prop-predictions"

# Only publish a lean when we genuinely disagree with the de-vigged market by this
# much probability, and only trust markets priced by >=2 books.
MIN_EDGE = 0.04
MIN_BOOK_COUNT = 2

# The de-vigged market is a very strong prior. Publish only a fraction of our raw
# disagreement (residual blend) and hard-cap the edge, so a mis-specified Poisson
# tail can't manufacture a fake +30% edge that never hits. This is the same
# "don't fight the market" discipline used on the moneyline model.
MARKET_BLEND_ALPHA = 0.45
MAX_PROP_EDGE = 0.10
# Parlay legs must be likely to hit AND carry real edge.
PARLAY_MIN_PROB = 0.56
PARLAY_MIN_EDGE = 0.03
PARLAY_MAX_LEGS = 5
# PARLAY_TARGET_LEGS / PARLAY_MIN_LEGS set below with the accuracy policy.

# Props PrizePicks actually offers. Daily card only uses ACCURACY_PROPS (below).
PLAYABLE_PROPS = {
    "batter_hits",
    "batter_singles",
    "pitcher_strikeouts",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
    "pitcher_walks",
}

# Structurally misspecified on our engine (Poisson TB/RBI/HRR) — live hit rates
# were ~18–25%. Drop from the board entirely until distributions are rewritten.
BROKEN_PROPS = {
    "batter_total_bases",
    "batter_rbis",
    "batter_hits_runs_rbis",
    "batter_runs_scored",
    "batter_home_runs",
    "batter_stolen_bases",
    "batter_doubles",
}

# Accuracy card = salvageable markets only (not TB/RBI/HRR).
# Live graded: hits ~57–67%, K ~59%, pitcher HA/ER ~72–76%.
ACCURACY_PROPS = {
    "batter_hits",
    "pitcher_strikeouts",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
}
ACCURACY_LINES = {
    ("batter_hits", 0.5),
    ("batter_hits", 1.5),
    ("pitcher_strikeouts", 4.5),
    ("pitcher_strikeouts", 5.5),
    ("pitcher_strikeouts", 6.5),
    ("pitcher_strikeouts", 7.5),
    ("pitcher_hits_allowed", 5.5),
    ("pitcher_hits_allowed", 6.5),
    ("pitcher_earned_runs", 2.5),
    ("pitcher_earned_runs", 3.5),
}
TOP_BET_MIN_CONF = 0.58
PARLAY_LEG_MIN_PROB = 0.58
TOP_BET_ALLOW_OVER = False
PARLAY_TARGET_LEGS = 5
PARLAY_MIN_LEGS = 2  # honest short card beats empty or padded junk
PARLAY_TYPE = "flex"
# Shrink PrizePicks raw/calibrated P(over) toward 0.5 — live probs were badly
# overconfident without a book to anchor to (odds path already had this).
PRIZEPICKS_OVERCONFIDENCE_SHRINK = 0.70
APPLY_CALIBRATION_ON_PRIZEPICKS = False
POLICY_PATH = REPO_ROOT / "data" / "prop_accuracy_policy.json"

PRETTY = {
    "pitcher_strikeouts": "Strikeouts",
    "pitcher_outs": "Outs",
    "pitcher_earned_runs": "Earned Runs",
    "pitcher_hits_allowed": "Hits Allowed",
    "pitcher_walks": "Walks Allowed",
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


# Pitcher K Overs are the one Over we trust enough for the daily card when the
# projection clears the line by a full strikeout (e.g. Miz ~9 Ks on a 6.5 goblin).
# Ignore juiced baby goblins (3.5/4.5) — those flood the board and crowd out real lines.
K_OVER_MIN_CONF = 0.60
K_OVER_MIN_PROJ_EDGE = 1.0
K_OVER_MIN_LINE = 4.5  # real PP ladder; 3.5 baby goblins still excluded


def _load_accuracy_policy() -> None:
    """Override Top-5 thresholds from the latest freeze (if present)."""
    global TOP_BET_MIN_CONF, PARLAY_LEG_MIN_PROB, K_OVER_MIN_CONF
    global APPLY_CALIBRATION_ON_PRIZEPICKS, PRIZEPICKS_OVERCONFIDENCE_SHRINK
    if not POLICY_PATH.exists():
        return
    try:
        policy = json.loads(POLICY_PATH.read_text())
    except Exception:
        return
    shipped = policy.get("shipped") or {}
    # Only raise/cut thresholds when the gate passed.
    if not policy.get("gate_passed"):
        return
    if shipped.get("min_under_conf") is not None:
        TOP_BET_MIN_CONF = float(shipped["min_under_conf"])
        PARLAY_LEG_MIN_PROB = float(shipped["min_under_conf"])
    if shipped.get("k_over_min_conf") is not None:
        K_OVER_MIN_CONF = float(shipped["k_over_min_conf"])
    if shipped.get("apply_calibration_on_prizepicks"):
        APPLY_CALIBRATION_ON_PRIZEPICKS = True
    if shipped.get("overconfidence_shrink") is not None:
        PRIZEPICKS_OVERCONFIDENCE_SHRINK = float(shipped["overconfidence_shrink"])


_load_accuracy_policy()


def _confidence(
    edge: float,
    book_count: int,
    *,
    side: str = "Over",
    model_prob: float = 0.5,
    prop: str | None = None,
) -> str:
    # Confidence is about hit probability, not edge-vs-pick'em. Against a 0.5
    # PrizePicks prior, edge>=0.09 is trivial (model 0.59) and was labeling junk Elite.
    if side == "Over":
        if prop == "pitcher_strikeouts" and model_prob >= 0.75:
            return "Elite" if book_count >= 2 else "High"
        if prop == "pitcher_strikeouts" and model_prob >= K_OVER_MIN_CONF:
            return "High"
        if model_prob < 0.85:
            return "Low"
    if side == "Under" and model_prob >= TOP_BET_MIN_CONF and book_count >= 2:
        return "Elite"
    if side == "Under" and model_prob >= 0.70:
        return "High"
    if model_prob >= 0.62 or edge >= 0.06:
        return "Medium"
    return "Low"


def _is_freebie_leg(p: dict) -> bool:
    """Ban lines that are not real bets — obvious Unders / unplayable juice.

    SB/HR Under 0.5 will print ~95%+ forever. Nobody can (or should) bet them;
    they must never appear on the board or in scrub logs.
    """
    prop = p.get("prop") or ""
    side = (p.get("side") or "").strip()
    try:
        line = float(p.get("line") or 0)
    except Exception:
        return False
    if prop in BROKEN_PROPS:
        return True
    # Obvious "they won't steal / won't HR / won't double" Unders — not a market edge.
    if prop in ("batter_home_runs", "batter_stolen_bases", "batter_doubles") and line <= 0.5 and side == "Under":
        return True
    if prop == "batter_runs_scored":
        return True
    # Model collapsing to ~1.0 is the old calibration failure mode.
    if float(p.get("model_prob") or 0) >= 0.97:
        return True
    return False


def _is_unbettable_prop_line(prop: str, line: float, side: str | None = None) -> bool:
    """Drop before projecting — save work and keep junk off the board entirely."""
    if prop in BROKEN_PROPS:
        return True
    if prop in ("batter_home_runs", "batter_stolen_bases", "batter_doubles") and float(line) <= 0.5:
        if prop in ("batter_stolen_bases", "batter_doubles"):
            return True
        if side == "Under":
            return True
    return False


def _is_unplayable_on_prizepicks(p: dict) -> bool:
    """Demons/Goblins are More-only on PrizePicks — Under/Less cannot be selected."""
    odds = (p.get("pp_odds_type") or "").lower()
    if odds in ("demon", "goblin") and p.get("side") == "Under":
        return True
    return False


def _actionable_rank_key(p: dict) -> tuple:
    """Best-to-bet-first: playable, then hit prob, then edge. Unplayable sinks.

    Baby goblin K Overs (3.5/4.5) are juice — keep them below real 5.5+ K lines
    and high-conf Unders even if confidence tags them Elite.
    """
    junk = 1 if (_is_unplayable_on_prizepicks(p) or _is_freebie_leg(p) or p.get("coin_flip")) else 0
    baby_k = 0
    if (
        p.get("prop") == "pitcher_strikeouts"
        and p.get("side") == "Over"
        and float(p.get("line") or 0) < K_OVER_MIN_LINE
    ):
        baby_k = 1
    conf = {"Elite": 0, "High": 1, "Medium": 2, "Low": 3}.get(str(p.get("confidence") or ""), 4)
    return (
        junk,
        baby_k,
        conf,
        -float(p.get("model_prob") or 0),
        -float(p.get("edge") or 0),
    )


def _hot_streak_blocks_under(p: dict) -> bool:
    """Don't recommend TB/hits Under when the batter just cleared the line 3x."""
    if p.get("side") != "Under":
        return False
    if p.get("prop") not in ("batter_total_bases", "batter_hits"):
        return False
    pid = p.get("player_id")
    if not pid:
        return False
    try:
        last3 = hitter_last_n_total_bases(int(pid), date.today(), n=3)
        line = float(p.get("line") or 0)
    except Exception:
        return False
    if len(last3) < 3:
        return False
    # Hits Under: treat TB proxy as weak; require each game TB > line for hits too
    # (a 3-hit night is TB>=3). For hits line 0.5/1.5, clearing TB>line is enough.
    return all(tb > line for tb in last3)


def _sanitize_leg(p: dict) -> dict:
    """Hard guards so bad labels/sides can't ship even if a caller regresses."""
    row = dict(p)
    side = row.get("side") or ""
    model_p = float(row.get("model_prob") or 0.0)
    edge = float(row.get("edge") or 0.0)
    books = int(row.get("book_count") or 0)
    # Recompute confidence from model_prob — never trust a stale Elite tag.
    row["confidence"] = _confidence(
        edge, books, side=side, model_prob=model_p, prop=row.get("prop"),
    )
    if model_p < TOP_BET_MIN_CONF:
        row["below_oos_threshold"] = True
    # Unders with mean at/above the line are coin flips — mark them.
    try:
        if side == "Under" and float(row.get("projection") or 0) >= float(row.get("line") or 0):
            row["coin_flip"] = True
            row["confidence"] = "Low"
    except Exception:
        pass
    if _is_freebie_leg(row) or _is_unplayable_on_prizepicks(row):
        row["coin_flip"] = True
        row["unplayable"] = _is_unplayable_on_prizepicks(row)
        row["confidence"] = "Low"
    return row


def _pick_diverse(pool: list[dict], n: int, *, max_per_prop: int) -> list[dict]:
    best: dict[str, dict] = {}
    prop_counts: dict[str, int] = {}
    for p in pool:
        if p["player"] in best:
            continue
        if prop_counts.get(p["prop"], 0) >= max_per_prop:
            continue
        if _is_unplayable_on_prizepicks(p) or _is_freebie_leg(p) or _hot_streak_blocks_under(p):
            continue
        row = _sanitize_leg(p)
        if row.get("coin_flip") or row.get("unplayable"):
            continue
        best[p["player"]] = row
        prop_counts[p["prop"]] = prop_counts.get(p["prop"], 0) + 1
        if len(best) >= n:
            break
    return list(best.values())[:n]


def _park_hr_factor(home_team_id: int | None) -> float:
    if home_team_id is None:
        return 1.0
    try:
        from park_factors import park_for_team
        park = park_for_team(home_team_id)
        return getattr(park, "park_factor_hr", 1.0) or 1.0
    except Exception:
        return 1.0


def build_predictions_from_prizepicks(game_date: date) -> list[dict]:
    """Edge projections against live PrizePicks standard lines (pick'em prior)."""
    # Prefer cache (30m TTL); force refresh only when explicitly asked.
    force = os.getenv("PRIZEPICKS_FORCE_REFRESH", "0") == "1"
    pp_lines = fetch_prizepicks_lines(odds_type="standard", force_refresh=force)
    if not pp_lines:
        return []

    abbr_by_id = load_team_abbreviations()
    id_by_abbr: dict[str, int] = {}
    for tid, abbr in abbr_by_id.items():
        id_by_abbr[abbr] = tid
        id_by_abbr[_norm_abbr(abbr)] = tid

    games = fetch_upcoming_games(game_date, game_date)
    # Build roster name -> (player_id, team_abbr) for today's teams.
    roster: dict[str, tuple[int, str]] = {}
    game_by_team: dict[str, dict] = {}
    for g in games:
        ha = abbr_by_id.get(g.home_team_id)
        aa = abbr_by_id.get(g.away_team_id)
        if not ha or not aa:
            continue
        meta = {
            "home_pitcher_id": g.home_pitcher_id,
            "away_pitcher_id": g.away_pitcher_id,
            "home_team_id": g.home_team_id,
            "away_team_id": g.away_team_id,
            "home_abbr": ha,
            "away_abbr": aa,
            "game_pk": g.game_pk,
            "game_datetime_iso": g.game_datetime_iso,
        }
        game_by_team[_norm_abbr(ha)] = meta
        game_by_team[_norm_abbr(aa)] = meta
        roster.update(_roster_name_map(g.home_team_id, ha, game_date.year))
        roster.update(_roster_name_map(g.away_team_id, aa, game_date.year))

    starter_cache: dict[int, dict] = {}
    predictions: list[dict] = []

    def starter_stats(pid: int | None) -> dict | None:
        if not pid:
            return None
        if pid not in starter_cache:
            try:
                starter_cache[pid] = pitcher_stats_as_of(pid, game_date)
            except Exception:
                starter_cache[pid] = {}
        return starter_cache[pid]

    for pp in pp_lines:
        # SB 0.5 / Runs / etc. — not bettable edges; never project or list them.
        if _is_unbettable_prop_line(pp.prop, float(pp.line)):
            continue
        key = _norm_name(pp.player)
        resolved = roster.get(key)
        if not resolved:
            continue
        player_id, team_abbr = resolved
        team_n = _norm_abbr(team_abbr)
        game_meta = game_by_team.get(team_n) or game_by_team.get(_norm_abbr(pp.team or ""))
        if not game_meta:
            continue

        is_home = _same_team(team_abbr, game_meta["home_abbr"])
        home_team_id = game_meta["home_team_id"]
        away_team_id = game_meta["away_team_id"]
        run_mult, hr_env_mult = env_multipliers(home_team_id, game_meta.get("game_datetime_iso"))

        line = PropLine(
            event_id=pp.projection_id,
            commence_time=pp.start_time,
            game_id=pp.game_id,
            home_abbr=game_meta["home_abbr"],
            away_abbr=game_meta["away_abbr"],
            player=pp.player,
            player_id=player_id,
            team_abbr=team_abbr,
            is_home=is_home,
            opp_abbr=game_meta["away_abbr"] if is_home else game_meta["home_abbr"],
            prop=pp.prop,
            line=pp.line,
            over_price=-110,
            under_price=-110,
            market_prob_over=0.5,  # PrizePicks pick'em
            book_count=3,
        )

        if pp.prop.startswith("batter_"):
            opp_pitcher_id = (
                game_meta["away_pitcher_id"] if is_home else game_meta["home_pitcher_id"]
            )
            opp_team_id = away_team_id if is_home else home_team_id
            slots = {}
            try:
                slots = confirmed_lineup(game_meta["game_pk"])
            except Exception:
                slots = {}
            exp_pa = expected_pa_for_player(player_id, slots)
            opp_bullpen = None
            if os.getenv("PROP_SKIP_BULLPEN", "0") != "1":
                try:
                    snap = bullpen_stats_as_of(opp_team_id, game_date)
                    opp_bullpen = (snap.era, snap.whip)
                except Exception:
                    opp_bullpen = None
            quality = None
            if os.getenv("PROP_SKIP_STATCAST", "0") != "1":
                try:
                    quality = hitter_quality(player_id, game_date)
                except Exception:
                    quality = None
            proj = project_prop(
                line, game_date, starter_stats(opp_pitcher_id), hr_env_mult, opp_pitcher_id,
                exp_pa=exp_pa, run_mult=run_mult, hr_env_mult=hr_env_mult,
                opp_bullpen=opp_bullpen, quality=quality,
            )
        else:
            hand = pitcher_throws(player_id)
            opp_team_id = away_team_id if is_home else home_team_id
            opp_sides = []
            try:
                by_team = confirmed_lineup_by_team(game_meta["game_pk"])
                for pid in by_team.get(opp_team_id, []):
                    s = batter_bat_side(pid)
                    if s:
                        opp_sides.append(s)
            except Exception:
                opp_sides = []
            proj = project_prop(
                line, game_date, None,
                pitcher_hand=hand, opp_bat_sides=opp_sides,
            )
        if proj is None:
            continue

        # PrizePicks is pick'em (~0.5). Calibrate, then shrink toward 0.5 — live
        # boards were shipping 0.85–0.95 soft Unders that hit ~38% overall.
        raw_over = float(proj.prob_over)
        p_over = (
            calibrate(pp.prop, raw_over)
            if APPLY_CALIBRATION_ON_PRIZEPICKS
            else raw_over
        )
        shrink = max(0.0, min(1.0, PRIZEPICKS_OVERCONFIDENCE_SHRINK))
        p_over = 0.5 + (p_over - 0.5) * shrink
        pickem = 0.5
        if p_over >= pickem:
            side = "Over"
            model_p = p_over
        else:
            side = "Under"
            model_p = 1.0 - p_over
        if _is_unbettable_prop_line(pp.prop, float(pp.line), side=side):
            continue
        if pp.prop not in PLAYABLE_PROPS and pp.prop not in ACCURACY_PROPS:
            continue
        edge = model_p - pickem
        if edge < MIN_EDGE:
            continue
        # Unders need the mean below the line; otherwise it's a dressed-up coin flip.
        if side == "Under" and float(proj.projection) >= float(pp.line):
            continue
        cand = {
                "game_id": pp.game_id,
                "matchup": f"{game_meta['away_abbr']} @ {game_meta['home_abbr']}",
                "commence_time": pp.start_time,
                "player": pp.player,
                "player_id": player_id,
                "team": team_abbr,
                "opp": line.opp_abbr,
                "prop": pp.prop,
                "prop_label": pp.prop_label,
                "line": pp.line,
                "side": side,
                "pick": f"{side} {pp.line}",
                "projection": proj.projection,
                "model_prob": round(model_p, 4),
                "model_prob_raw": round(raw_over if side == "Over" else 1.0 - raw_over, 4),
                "market_prob": None,  # pick'em — not a de-vigged book price
                "edge": round(edge, 4),
                "price": None,
                "ev": None,
                "confidence": _confidence(
                    edge, 3, side=side, model_prob=model_p, prop=pp.prop,
                ),
                "book_count": 0,  # not a multi-book consensus — pick'em
                "line_source": "prizepicks",
                "market_is_pickem": True,
                "pp_odds_type": pp.odds_type,
                "note": proj.model_note,
            }
        if _is_freebie_leg(cand):
            continue
        predictions.append(cand)

    # Safety net: sportsbook K lines for any starter PP omitted entirely.
    predictions.extend(
        _odds_api_k_fillins(game_date, predictions, roster, game_by_team, starter_cache)
    )
    predictions.sort(key=_actionable_rank_key)
    return predictions


def _odds_api_k_fillins(
    game_date: date,
    existing: list[dict],
    roster: dict[str, tuple[int, str]],
    game_by_team: dict[str, dict],
    starter_cache: dict[int, dict],
) -> list[dict]:
    """If PrizePicks dropped a starter K, still score the sportsbook K line."""
    have = {_norm_name(p["player"]) for p in existing if p.get("prop") == "pitcher_strikeouts"}
    try:
        book_lines = [l for l in fetch_prop_lines() if l.prop == "pitcher_strikeouts"]
    except Exception:
        return []
    out: list[dict] = []
    for line in book_lines:
        key = _norm_name(line.player)
        if key in have:
            continue
        resolved = roster.get(key)
        if not resolved and line.player_id:
            # Odds API already resolved id.
            player_id = line.player_id
            team_abbr = line.team_abbr or ""
        elif resolved:
            player_id, team_abbr = resolved
        else:
            continue
        team_n = _norm_abbr(team_abbr or line.team_abbr or "")
        game_meta = game_by_team.get(team_n)
        if not game_meta:
            continue
        is_home = _same_team(team_abbr or "", game_meta["home_abbr"])
        hand = pitcher_throws(player_id)
        opp_sides: list[str] = []
        try:
            by_team = confirmed_lineup_by_team(game_meta["game_pk"])
            opp_team_id = game_meta["away_team_id"] if is_home else game_meta["home_team_id"]
            for pid in by_team.get(opp_team_id, []):
                s = batter_bat_side(pid)
                if s:
                    opp_sides.append(s)
        except Exception:
            opp_sides = []
        pl = PropLine(
            event_id=line.event_id,
            commence_time=line.commence_time,
            game_id=line.game_id,
            home_abbr=game_meta["home_abbr"],
            away_abbr=game_meta["away_abbr"],
            player=line.player,
            player_id=player_id,
            team_abbr=team_abbr or line.team_abbr,
            is_home=is_home,
            opp_abbr=game_meta["away_abbr"] if is_home else game_meta["home_abbr"],
            prop="pitcher_strikeouts",
            line=line.line,
            over_price=line.over_price,
            under_price=line.under_price,
            market_prob_over=line.market_prob_over,
            book_count=line.book_count,
        )
        proj = project_prop(
            pl, game_date, None, pitcher_hand=hand, opp_bat_sides=opp_sides,
        )
        if proj is None:
            continue
        raw_over = float(proj.prob_over)
        market_over = float(line.market_prob_over)
        if raw_over >= market_over:
            side, model_p, market_p, price = "Over", raw_over, market_over, line.over_price
        else:
            side, model_p, market_p, price = "Under", 1.0 - raw_over, 1.0 - market_over, line.under_price
        edge = model_p - market_p
        if edge < MIN_EDGE:
            continue
        if side == "Under" and float(proj.projection) >= float(line.line):
            continue
        out.append(
            {
                "game_id": line.game_id,
                "matchup": f"{game_meta['away_abbr']} @ {game_meta['home_abbr']}",
                "commence_time": line.commence_time,
                "player": line.player,
                "player_id": player_id,
                "team": team_abbr or line.team_abbr,
                "opp": pl.opp_abbr,
                "prop": "pitcher_strikeouts",
                "prop_label": "Pitcher Strikeouts",
                "line": line.line,
                "side": side,
                "pick": f"{side} {line.line}",
                "projection": proj.projection,
                "model_prob": round(model_p, 4),
                "model_prob_raw": round(model_p, 4),
                "market_prob": round(market_p, 4),
                "edge": round(edge, 4),
                "price": price,
                "ev": round(model_p * (_decimal(price) - 1.0) - (1.0 - model_p), 4),
                "confidence": _confidence(
                    edge, line.book_count, side=side, model_prob=model_p, prop="pitcher_strikeouts",
                ),
                "book_count": line.book_count,
                "line_source": "the-odds-api",
                "pp_odds_type": None,
                "note": proj.model_note,
            }
        )
        have.add(key)
    return out


def build_predictions(game_date: date) -> list[dict]:
    lines = fetch_prop_lines()
    if not lines:
        return []

    abbr_by_id = load_team_abbreviations()
    # Index team ids by every known alias (ATH/OAK, AZ/ARI, etc.).
    id_by_abbr: dict[str, int] = {}
    for tid, abbr in abbr_by_id.items():
        id_by_abbr[abbr] = tid
        id_by_abbr[_norm_abbr(abbr)] = tid
    for alias, canon in (("ATH", "OAK"), ("AZ", "ARI"), ("CWS", "CHW"), ("TBR", "TB"),
                         ("SFG", "SF"), ("KCR", "KC"), ("SDP", "SD"), ("WAS", "WSH")):
        if canon in id_by_abbr:
            id_by_abbr[alias] = id_by_abbr[canon]

    # Map normalized (away, home) -> probable pitcher ids + park + game context.
    games = fetch_upcoming_games(game_date, game_date)
    starters: dict[tuple[str, str], dict] = {}
    for g in games:
        ha = abbr_by_id.get(g.home_team_id)
        aa = abbr_by_id.get(g.away_team_id)
        if not ha or not aa:
            continue
        meta = {
            "home_pitcher_id": g.home_pitcher_id,
            "away_pitcher_id": g.away_pitcher_id,
            "home_team_id": g.home_team_id,
            "away_team_id": g.away_team_id,
            "game_pk": g.game_pk,
            "game_datetime_iso": g.game_datetime_iso,
        }
        starters[(_norm_abbr(aa), _norm_abbr(ha))] = meta

    predictions: list[dict] = []
    starter_cache: dict[int, dict] = {}
    bullpen_cache: dict[int, tuple[float, float]] = {}
    quality_cache: dict[int, object] = {}
    lineup_slot_cache: dict[int, dict[int, int]] = {}
    bat_side_cache: dict[int, list[str]] = {}

    def starter_stats(pid: int | None) -> dict | None:
        if not pid:
            return None
        if pid not in starter_cache:
            try:
                starter_cache[pid] = pitcher_stats_as_of(pid, game_date)
            except Exception:
                starter_cache[pid] = {}
        return starter_cache[pid]

    def bullpen(team_id: int | None) -> tuple[float, float] | None:
        if not team_id:
            return None
        if os.getenv("PROP_SKIP_BULLPEN", "0") == "1":
            return None
        if team_id not in bullpen_cache:
            try:
                snap = bullpen_stats_as_of(team_id, game_date)
                bullpen_cache[team_id] = (snap.era, snap.whip)
            except Exception:
                bullpen_cache[team_id] = None
        return bullpen_cache[team_id]

    def quality(pid: int | None) -> object | None:
        if not pid:
            return None
        # Statcast pulls can hang / lag the daily board; allow skipping under load.
        if os.getenv("PROP_SKIP_STATCAST", "0") == "1":
            return None
        if pid not in quality_cache:
            try:
                quality_cache[pid] = hitter_quality(pid, game_date)
            except Exception:
                quality_cache[pid] = None
        return quality_cache[pid]

    def lineup_slots(game_pk: int | None) -> dict[int, int]:
        if not game_pk:
            return {}
        if game_pk not in lineup_slot_cache:
            try:
                lineup_slot_cache[game_pk] = confirmed_lineup(game_pk)
            except Exception:
                lineup_slot_cache[game_pk] = {}
        return lineup_slot_cache[game_pk]

    def opp_lineup_bat_sides(game_pk: int | None, opp_team_id: int | None) -> list[str]:
        """Bat sides for the opposing lineup (for pitcher K platoon)."""
        key = (game_pk or 0)
        if not game_pk or not opp_team_id:
            return []
        cache_key = game_pk * 1000 + (opp_team_id % 1000)
        if cache_key not in bat_side_cache:
            sides: list[str] = []
            try:
                by_team = confirmed_lineup_by_team(game_pk)
                ids = by_team.get(opp_team_id, [])
                for pid in ids:
                    s = batter_bat_side(pid)
                    if s:
                        sides.append(s)
            except Exception:
                sides = []
            bat_side_cache[cache_key] = sides
        return bat_side_cache[cache_key]

    for line in lines:
        if line.player_id is None or line.book_count < MIN_BOOK_COUNT:
            continue
        game_key = (_norm_abbr(line.away_abbr), _norm_abbr(line.home_abbr))
        game_meta = starters.get(game_key, {})
        home_team_id = game_meta.get("home_team_id") or id_by_abbr.get(_norm_abbr(line.home_abbr)) or id_by_abbr.get(line.home_abbr)
        away_team_id = game_meta.get("away_team_id") or id_by_abbr.get(_norm_abbr(line.away_abbr)) or id_by_abbr.get(line.away_abbr)
        game_pk = game_meta.get("game_pk")
        run_mult, hr_env_mult = env_multipliers(home_team_id, game_meta.get("game_datetime_iso"))

        proj = None
        if line.prop.startswith("batter_"):
            # Need a resolved side so we don't invent the wrong opposing pitcher.
            is_home = line.is_home
            if is_home is None and line.team_abbr:
                if _same_team(line.team_abbr, line.home_abbr):
                    is_home = True
                elif _same_team(line.team_abbr, line.away_abbr):
                    is_home = False
            if is_home is None:
                continue
            opp_pitcher_id = (
                game_meta.get("away_pitcher_id") if is_home else game_meta.get("home_pitcher_id")
            )
            opp_team_id = away_team_id if is_home else home_team_id
            opp_starter = starter_stats(opp_pitcher_id)
            exp_pa = expected_pa_for_player(line.player_id, lineup_slots(game_pk))
            proj = project_prop(
                line, game_date, opp_starter, hr_env_mult, opp_pitcher_id,
                exp_pa=exp_pa,
                run_mult=run_mult,
                hr_env_mult=hr_env_mult,
                opp_bullpen=bullpen(opp_team_id),
                quality=quality(line.player_id),
            )
        else:
            # Pitcher prop: strikeout platoon vs the opposing lineup composition.
            is_home = line.is_home
            if is_home is None and line.team_abbr:
                if _same_team(line.team_abbr, line.home_abbr):
                    is_home = True
                elif _same_team(line.team_abbr, line.away_abbr):
                    is_home = False
            if is_home is None:
                continue
            pitcher_hand = pitcher_throws(line.player_id)
            opp_team_id = away_team_id if is_home else home_team_id
            proj = project_prop(
                line, game_date, None,
                pitcher_hand=pitcher_hand,
                opp_bat_sides=opp_lineup_bat_sides(game_pk, opp_team_id),
            )
        if proj is None:
            continue

        # Empirically calibrate, then apply Over-side distrust: walk-forward shows
        # calibrated P(over)>=0.70 still only lands ~60%. Pull Overs toward 0.5
        # before market blend so we stop manufacturing fake Over edges.
        raw_over = calibrate(line.prop, proj.prob_over)
        if raw_over > 0.5:
            raw_over = 0.5 + (raw_over - 0.5) * 0.55
        market_over = line.market_prob_over
        blended_over = market_over + MARKET_BLEND_ALPHA * (raw_over - market_over)

        if blended_over >= market_over:
            side = "Over"
            model_p = blended_over
            market_p = market_over
            price = line.over_price
        else:
            side = "Under"
            model_p = 1.0 - blended_over
            market_p = 1.0 - market_over
            price = line.under_price

        edge = model_p - market_p
        if edge > MAX_PROP_EDGE:
            model_p = market_p + MAX_PROP_EDGE
            edge = MAX_PROP_EDGE
        if edge < MIN_EDGE:
            continue
        if _is_unbettable_prop_line(line.prop, float(line.line), side=side):
            continue
        ev = model_p * (_decimal(price) - 1.0) - (1.0 - model_p)
        if _is_freebie_leg({
            "prop": line.prop, "side": side, "line": line.line, "model_prob": model_p,
        }):
            continue

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
                "model_prob_raw": round(raw_over if side == "Over" else 1.0 - raw_over, 4),
                "market_prob": round(market_p, 4),
                "edge": round(edge, 4),
                "price": price,
                "ev": round(ev, 4),
                "confidence": _confidence(
                    edge, line.book_count, side=side, model_prob=model_p, prop=line.prop,
                ),
                "book_count": line.book_count,
                "note": proj.model_note,
            }
        )

    predictions.sort(key=_actionable_rank_key)
    return predictions


def _accuracy_lane(predictions: list[dict], min_conf: float, *, prefer_lines: bool = True) -> list[dict]:
    """Picks that historically clear ~80% leg hit rate / feed the 5-leg Flex."""
    out = []
    for p in predictions:
        if p["prop"] not in ACCURACY_PROPS:
            continue
        if p["model_prob"] < min_conf:
            continue
        if not TOP_BET_ALLOW_OVER and p["side"] != "Under":
            continue
        # Ban broken / freebie lines.
        if p["prop"] == "batter_runs_scored" and float(p["line"]) >= 1.5:
            continue
        if p["prop"] in ("batter_home_runs", "batter_stolen_bases") and float(p["line"]) <= 0.5:
            continue
        if prefer_lines and (p["prop"], float(p["line"])) not in ACCURACY_LINES:
            continue
        out.append(p)
    out.sort(key=lambda p: (p["model_prob"], p["edge"]), reverse=True)
    return out


def _k_over_lane(predictions: list[dict]) -> list[dict]:
    """Strong pitcher K Overs — the matchup exception to Under-only cards.

    Catches spots like Misiorowski (13 K/9) on the real PP K ladder (often
    tagged goblin with no ``standard`` row). Prefer PrizePicks-bettable lines
    over sportsbook fill-ins when seeding the daily card.
    """
    if POLICY_PATH.exists():
        try:
            shipped = (json.loads(POLICY_PATH.read_text()).get("shipped") or {})
            if shipped.get("allow_k_over") is False:
                return []
        except Exception:
            pass
    out = []
    for p in predictions:
        if p.get("prop") != "pitcher_strikeouts" or p.get("side") != "Over":
            continue
        if float(p.get("line") or 0) < K_OVER_MIN_LINE:
            continue
        if float(p.get("model_prob") or 0) < K_OVER_MIN_CONF:
            continue
        if float(p.get("projection") or 0) < float(p.get("line") or 0) + K_OVER_MIN_PROJ_EDGE:
            continue
        out.append(p)
    out.sort(
        key=lambda p: (
            1 if p.get("line_source") == "prizepicks" else 0,
            p["model_prob"],
            p["edge"],
        ),
        reverse=True,
    )
    return out


def build_top_bets(predictions: list[dict], n: int = 5) -> list[dict]:
    """Always field n Flex legs: top n unique players by model_prob.

    No reserved markets, no "max 2 of this prop" cap — that was kicking out
    #3 overall (Miz) for a weaker Singles leg. Only constraints:
      - one leg per player
      - freebies / coin-flips excluded
      - K Overs eligible alongside accuracy Unders
    """
    # Floor matches OOS-tuned TOP_BET_MIN_CONF — do not pad with sub-threshold junk.
    pool = [
        p for p in (
            _accuracy_lane(predictions, TOP_BET_MIN_CONF, prefer_lines=False)
            + _k_over_lane(predictions)
        )
        if (
            not _is_unplayable_on_prizepicks(p)
            and not _is_freebie_leg(p)
            and not _hot_streak_blocks_under(p)
        )
    ]
    dedup: dict[tuple[str, str, float, str], dict] = {}
    for p in pool:
        key = (p["player"], p["prop"], float(p["line"]), p["side"])
        prev = dedup.get(key)
        if prev is None or p["model_prob"] > prev["model_prob"]:
            dedup[key] = p
    pool = sorted(
        dedup.values(),
        key=lambda p: (p["model_prob"], p["edge"]),
        reverse=True,
    )

    # Unique players only — allow any number of the same prop type.
    # Prefer fewer honest legs over forcing n with coin flips.
    legs = _pick_diverse(pool, n, max_per_prop=n)
    return [_sanitize_leg(l) for l in legs[:n]]


def build_parlay(predictions: list[dict]) -> dict:
    """Daily Flex card from Top 5. Always publishes when we have legs."""
    legs = build_top_bets(predictions, n=PARLAY_TARGET_LEGS)

    combined = 1.0
    for l in legs:
        combined *= l["model_prob"]

    strong = sum(1 for l in legs if l["model_prob"] >= TOP_BET_MIN_CONF)
    quality = (
        "full" if len(legs) >= 5
        else "mixed" if len(legs) >= 3
        else "thin"
    )
    return {
        "type": PARLAY_TYPE if len(legs) >= 4 else ("power" if len(legs) <= 3 else "flex"),
        "n_legs": len(legs),
        "combined_prob": round(combined, 4),
        "card_quality": quality,
        "oos_legs": strong,
        # Do not advertise fake Flex cash rates from the old in-sample OOS search.
        "flex_cash_rate_oos": None,
        "power_cash_rate_oos": None,
        "policy": (
            json.loads(POLICY_PATH.read_text()).get("version", "accuracy_hits_k_live_v1")
            if POLICY_PATH.exists()
            else "accuracy_hits_k_live_v1"
        ),
        "legs": legs,
    }


def main() -> None:
    game_date = date.today()
    source = "prizepicks"
    predictions = build_predictions_from_prizepicks(game_date)
    if not predictions:
        source = "the-odds-api"
        predictions = build_predictions(game_date)

    # Fail-closed: drop absurd / unbettable rows BEFORE Top 5 / public write.
    predictions, rejected = scrub_predictions(predictions)
    if rejected:
        # Don't spam SB-Under freebies — those should have been filtered upstream.
        interesting = [
            r for r in rejected
            if r.get("prop") not in ("batter_stolen_bases", "batter_runs_scored")
            and not (
                r.get("prop") == "batter_home_runs"
                and r.get("side") == "Under"
                and float(r.get("line") or 0) <= 0.5
            )
        ]
        print(f"prop_publish_scrub dropped={len(rejected)} model_bugs={len(interesting)}")
        for row in interesting[:15]:
            print(
                f"  reject {row.get('player')} {row.get('side')} {row.get('line')} "
                f"{row.get('prop')} proj={row.get('projection')} "
                f"p={row.get('model_prob')} ({row.get('publish_reject_reason')})"
            )

    top_bets = build_top_bets(predictions) if predictions else []
    parlay = build_parlay(predictions) if predictions else {"n_legs": 0, "legs": []}
    # Keep Top 5 and parlay identical (parlay rebuilds from the same function).
    if top_bets:
        parlay["legs"] = top_bets
        parlay["n_legs"] = len(top_bets)
    if source == "prizepicks":
        source_label = (
            "prizepicks partner-api + calibrated leakage-safe projections (OOS-gated Top 5)"
            if APPLY_CALIBRATION_ON_PRIZEPICKS
            else "prizepicks partner-api standard lines + raw leakage-safe projections"
        )
    else:
        source_label = "the-odds-api player props (de-vigged) + leakage-safe projections"
    payload = {
        "generated_at": game_date.isoformat(),
        "board_generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": source_label,
        "line_source": source,
        "count": len(predictions),
        "scrubbed_rejects": len(rejected),
        "min_edge": MIN_EDGE,
        "card_quality": parlay.get("card_quality"),
        "top_bets": top_bets,
        "parlay": parlay,
        "predictions": predictions,
    }
    # Final board-level guard: never ship Elite tags below the OOS bar.
    for bucket in (payload["top_bets"], payload["parlay"].get("legs") or []):
        for i, leg in enumerate(bucket):
            bucket[i] = _sanitize_leg(leg)
    assert_payload_sane(payload, context="prop-predictions.json")
    OUT_PATH.write_text(json.dumps(payload, indent=2))

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = ARCHIVE_DIR / f"{game_date.isoformat()}.json"
    # Lock once a real card exists. Overwrite when: switching to PrizePicks,
    # empty/incomplete archive, force flag, or the new card is the OOS-gated
    # precision card (never restore a pre-gate padded Top 5 over a thin honest one).
    overwrite = False
    policy_version = (
        json.loads(POLICY_PATH.read_text()).get("version")
        if POLICY_PATH.exists()
        else None
    )
    if archive_path.exists():
        try:
            locked = json.loads(archive_path.read_text())
            locked_legs = len(locked.get("top_bets") or [])
            locked_parlay = int((locked.get("parlay") or {}).get("n_legs") or 0)
            incomplete = locked_legs < PARLAY_MIN_LEGS and locked_parlay < PARLAY_MIN_LEGS
            locked_policy = (locked.get("parlay") or {}).get("policy")
            locked_min = min(
                (float(x.get("model_prob") or 0) for x in (locked.get("top_bets") or [])),
                default=0.0,
            )
            new_min = min(
                (float(x.get("model_prob") or 0) for x in top_bets),
                default=0.0,
            )
            precision_upgrade = (
                bool(policy_version)
                and locked_policy != policy_version
                and (
                    len(top_bets) > 0
                    and (new_min >= TOP_BET_MIN_CONF or len(top_bets) < locked_legs)
                )
            )
            if os.getenv("PROP_FORCE_ARCHIVE", "0") == "1":
                overwrite = True
            elif source == "prizepicks" and locked.get("line_source") != "prizepicks":
                overwrite = True
            elif incomplete and len(top_bets) >= 1:
                overwrite = True
            elif locked.get("no_bet") and len(top_bets) >= 1:
                overwrite = True
            elif precision_upgrade:
                overwrite = True
            elif locked_legs or locked_parlay:
                if not overwrite:
                    payload["top_bets"] = locked.get("top_bets", payload.get("top_bets"))
                    payload["parlay"] = locked.get("parlay", payload.get("parlay"))
                    payload["locked_from_archive"] = True
                    OUT_PATH.write_text(json.dumps(payload, indent=2))
                    top_bets = payload["top_bets"]
                    parlay = payload["parlay"]
        except Exception:
            pass
    if not archive_path.exists() or overwrite:
        archive_path.write_text(json.dumps(payload, indent=2))

    print(
        f"prop_predictions_ok source={source} count={len(predictions)} "
        f"parlay_legs={parlay.get('n_legs')} top_bets={len(top_bets)}"
    )
    for b in top_bets:
        print(f"  TOP {b['player']:20s} {b['prop_label']:14s} {b['pick']:10s} "
              f"model={b['model_prob']:.2f} edge={b['edge']:+.3f} conf={b['confidence']}")
    for l in parlay.get("legs", []):
        mkt = l.get("market_prob")
        mkt_s = "pickem" if mkt is None or l.get("market_is_pickem") else f"{mkt:.2f}"
        print(f"  {l['player']:22s} {l['prop_label']:14s} {l['pick']:10s} "
              f"model={l['model_prob']:.2f} mkt={mkt_s} edge={l['edge']:+.3f} conf={l['confidence']}")


if __name__ == "__main__":
    main()
