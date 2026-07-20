"""Project every MLB player prop from real stats, then edge it vs the real market.

For each real prop line (from prop_odds_provider) we build a leakage-safe
projection of the underlying stat using point-in-time player + opponent data, turn
it into P(over) via a Poisson/binomial outcome model, and compare it to the
de-vigged market P(over). The published edge is model P(over) − market P(over) on
the side we lean, so it reflects a genuine disagreement with the book — not a
self-invented line.

Features used per prop:
  - hitters: season rate stats (as-of), expected PAs from lineup context, opposing
    starter quality (ERA/WHIP/K9), park HR/run factor, opponent bullpen.
  - pitchers: K/9, expected IP, opponent team K-rate/OBP/OPS, park.
Handedness splits are layered in when available (see prop_matchup.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from hitter_stats_provider import (
    hitter_stats_as_of,
    hitter_recent_rates,
    hitter_last_n_total_bases,
)
from pitcher_stats_provider import pitcher_stats_as_of
from team_stats_provider import team_stats_as_of
from prop_odds_provider import PropLine
from handedness_provider import (
    pitcher_throws,
    hitter_platoon_multiplier,
    pitcher_k_platoon_multiplier,
)

LEAGUE_K_RATE = 0.223
LEAGUE_ERA = 4.30
LEAGUE_WHIP = 1.30
DEFAULT_PA = 4.15

# team abbr -> MLB team id (filled lazily)
_TEAM_ID_BY_ABBR: dict[str, int] | None = None


def _team_id_by_abbr() -> dict[str, int]:
    global _TEAM_ID_BY_ABBR
    if _TEAM_ID_BY_ABBR is None:
        from mlb_api import load_team_abbreviations
        try:
            _TEAM_ID_BY_ABBR = {v: k for k, v in load_team_abbreviations().items()}
        except Exception:
            _TEAM_ID_BY_ABBR = {}
    return _TEAM_ID_BY_ABBR


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam ** k / math.factorial(k)


def _poisson_sf(x_floor: int, lam: float) -> float:
    """P(X > line) where over(line) means X >= x_floor. = 1 - P(X <= x_floor-1)."""
    if x_floor <= 0:
        return 1.0
    cdf = sum(_poisson_pmf(k, lam) for k in range(0, x_floor))
    return max(0.0, min(1.0, 1.0 - cdf))


def _normal_sf(line: float, mean: float, sd: float) -> float:
    """P(X > line) for a normal — used for outs, which cluster tightly around
    expected innings (Poisson is far too wide for a starter's innings)."""
    if sd <= 0:
        return 1.0 if mean > line else 0.0
    z = (line - mean) / sd
    return max(0.0, min(1.0, 0.5 * math.erfc(z / math.sqrt(2.0))))


def _binom_pmf(n: int, k: int, p: float) -> float:
    if k < 0 or k > n:
        return 0.0
    return math.comb(n, k) * p ** k * (1 - p) ** (n - k)


def _binom_sf(x_floor: int, n: int, p: float) -> float:
    if x_floor <= 0:
        return 1.0
    cdf = sum(_binom_pmf(n, k, p) for k in range(0, min(x_floor, n + 1)))
    return max(0.0, min(1.0, 1.0 - cdf))


def _line_floor(line: float) -> int:
    """Over(line) is realized when count >= floor(line)+1 (lines are .5 style)."""
    return int(math.floor(line)) + 1


@dataclass
class PropProjection:
    prop: str
    projection: float          # expected value of the stat
    prob_over: float           # model P(over the line)
    model_note: str


def _opp_pitcher_quality(opp_starter: dict | None) -> tuple[float, float, float]:
    """Return (era, whip, k9) with league fallbacks."""
    if not opp_starter:
        return LEAGUE_ERA, LEAGUE_WHIP, 8.2
    era = opp_starter.get("era") or LEAGUE_ERA
    whip = opp_starter.get("whip") or LEAGUE_WHIP
    k9 = opp_starter.get("strikeouts_per_9") or 8.2
    return era, whip, k9


def _hitter_run_env(opp_era: float, opp_whip: float) -> float:
    """Multiplier on hitter production from opposing starter quality."""
    era_adj = 1.0 + (opp_era - LEAGUE_ERA) * 0.05
    whip_adj = 1.0 + (opp_whip - LEAGUE_WHIP) * 0.10
    return max(0.85, min(1.18, (era_adj + whip_adj) / 2.0))


def project_hitter(
    line: PropLine,
    game_date: date,
    opp_starter: dict | None,
    park_hr: float = 1.0,
    opp_pitcher_id: int | None = None,
    *,
    exp_pa: float | None = None,
    run_mult: float = 1.0,
    hr_env_mult: float = 1.0,
    opp_bullpen: tuple[float, float] | None = None,
    quality: object | None = None,
) -> PropProjection | None:
    stats = hitter_stats_as_of(line.player_id, game_date)
    pa = stats.get("plate_appearances", 0.0)
    if not pa or pa < 30:
        return None

    # Opposing run environment = starter blended with the bullpen the hitter will
    # also face (~65% starter innings / 35% relief in a typical game).
    opp_era, opp_whip, opp_k9 = _opp_pitcher_quality(opp_starter)
    if opp_bullpen:
        pen_era, pen_whip = opp_bullpen
        opp_era = 0.65 * opp_era + 0.35 * pen_era
        opp_whip = 0.65 * opp_whip + 0.35 * pen_whip
    boost = _hitter_run_env(opp_era, opp_whip)

    # Handedness platoon: tilt production by the hitter's OPS split vs the
    # opposing starter's throwing hand (shrunk on small samples).
    platoon = 1.0
    opp_hand = pitcher_throws(opp_pitcher_id) if opp_pitcher_id else None
    if opp_hand:
        platoon = hitter_platoon_multiplier(
            line.player_id, opp_hand, game_date, overall_ops=stats.get("ops")
        )
    boost *= platoon

    # Statcast quality-of-contact regression (recent xwOBACON / barrels).
    q_hit = float(getattr(quality, "hit_mult", 1.0) or 1.0)
    q_hr = float(getattr(quality, "hr_mult", 1.0) or 1.0)

    # Overall offense multiplier (park+weather runs, matchup, quality of contact).
    # Clamp the stacked product so no single projection can run away from reality
    # when several favorable factors compound.
    off_mult = max(0.70, min(1.40, boost * run_mult * q_hit))
    # Home-run multiplier uses HR-specific park/weather and barrel quality.
    hr_mult = max(0.55, min(1.90, boost * hr_env_mult * q_hr))

    exp_pa = exp_pa if exp_pa and exp_pa > 0 else DEFAULT_PA
    ab = exp_pa * 0.88  # PA minus walks/hbp/sac approx

    hits = stats.get("hits", 0.0)
    doubles = stats.get("doubles", 0.0)
    triples = stats.get("triples", 0.0)
    hr = stats.get("home_runs", 0.0)
    walks = stats.get("walks", 0.0)
    rbi = stats.get("rbi", 0.0)
    runs = stats.get("runs", 0.0)
    sb = stats.get("stolen_bases", 0.0)
    singles = max(0.0, hits - doubles - triples - hr)

    # per-PA and per-AB rates (season), then blend recent form so a 3/4/5 TB
    # heater isn't projected as a 1.46 Under 1.5.
    hit_pa = hits / pa
    hr_pa = hr / pa
    bb_pa = walks / pa
    rbi_pa = rbi / pa
    run_pa = runs / pa
    sb_pa = sb / pa
    single_pa = singles / pa
    double_pa = doubles / pa
    tb = singles + 2 * doubles + 3 * triples + 4 * hr
    tb_pa = tb / pa

    recent = hitter_recent_rates(line.player_id, game_date, lookback_days=14)
    form_w = 0.0
    if recent:
        # ~45% weight on last ~2 weeks when sample is decent.
        form_w = min(0.50, 0.20 + 0.30 * min(1.0, recent["plate_appearances"] / 40.0))
        hit_pa = (1.0 - form_w) * hit_pa + form_w * recent["hit_pa"]
        tb_pa = (1.0 - form_w) * tb_pa + form_w * recent["tb_pa"]
        hr_pa = (1.0 - form_w) * hr_pa + form_w * recent["hr_pa"]

    hit_pa *= off_mult
    hr_pa *= hr_mult
    rbi_pa *= off_mult
    run_pa *= off_mult
    single_pa *= off_mult
    double_pa *= off_mult
    tb_pa *= off_mult

    prop = line.prop
    L = line.line
    floor = _line_floor(L)
    n_ab = max(1, int(round(ab)))
    n_pa = max(1, int(round(exp_pa)))
    plt = f" vs{opp_hand} plt={platoon:.2f}" if opp_hand else ""
    form = f" formW={form_w:.2f}" if form_w else ""
    ctx = f" pa={exp_pa:.1f} off={off_mult:.2f} q={q_hit:.2f}{form}"

    if prop == "batter_hits":
        p = min(0.85, hit_pa / 0.88)  # per-AB hit prob
        proj = p * n_ab
        prob = _binom_sf(floor, n_ab, min(0.9, p))
        return PropProjection(prop, round(proj, 2), round(prob, 4), f"p_hit/ab={p:.3f}{ctx}{plt}")
    if prop == "batter_total_bases":
        lam = tb_pa * exp_pa
        # Hot-streak veto: last 3 games all cleared the line → don't invent Under.
        last3 = hitter_last_n_total_bases(line.player_id, game_date, n=3)
        if last3 and len(last3) >= 3 and all(tb_i > L for tb_i in last3):
            lam = max(lam, sum(last3) / len(last3) * 0.85)
        prob = _poisson_sf(floor, lam)
        note = f"tb/pa={tb_pa:.3f}{ctx}{plt}"
        if last3:
            note += f" L3TB={','.join(str(int(x)) for x in last3)}"
        return PropProjection(prop, round(lam, 2), round(prob, 4), note)
    if prop == "batter_home_runs":
        lam = hr_pa * exp_pa
        prob = _poisson_sf(floor, lam)
        return PropProjection(prop, round(lam, 3), round(prob, 4), f"hr/pa={hr_pa:.3f} hrx={hr_mult:.2f} qhr={q_hr:.2f}{plt}")
    if prop == "batter_rbis":
        lam = rbi_pa * exp_pa
        prob = _poisson_sf(floor, lam)
        return PropProjection(prop, round(lam, 2), round(prob, 4), f"rbi/pa={rbi_pa:.3f}")
    if prop == "batter_runs_scored":
        lam = run_pa * exp_pa
        prob = _poisson_sf(floor, lam)
        return PropProjection(prop, round(lam, 2), round(prob, 4), f"run/pa={run_pa:.3f}")
    if prop == "batter_walks":
        p = min(0.6, bb_pa)
        prob = _binom_sf(floor, n_pa, p)
        return PropProjection(prop, round(p * n_pa, 2), round(prob, 4), f"bb/pa={bb_pa:.3f}")
    if prop == "batter_stolen_bases":
        lam = sb_pa * exp_pa
        prob = _poisson_sf(floor, lam)
        return PropProjection(prop, round(lam, 3), round(prob, 4), f"sb/pa={sb_pa:.3f}")
    if prop == "batter_singles":
        p = min(0.7, single_pa / 0.88)
        prob = _binom_sf(floor, n_ab, p)
        return PropProjection(prop, round(p * n_ab, 2), round(prob, 4), f"1b/ab={p:.3f}")
    if prop == "batter_doubles":
        lam = double_pa * exp_pa
        prob = _poisson_sf(floor, lam)
        return PropProjection(prop, round(lam, 3), round(prob, 4), f"2b/pa={double_pa:.3f}")
    if prop == "batter_hits_runs_rbis":
        lam = (hit_pa + run_pa + rbi_pa) * exp_pa
        prob = _poisson_sf(floor, lam)
        return PropProjection(prop, round(lam, 2), round(prob, 4), f"hrr/pa={(hit_pa+run_pa+rbi_pa):.3f}")
    return None


def project_pitcher(
    line: PropLine,
    game_date: date,
    opp_team_abbr: str | None,
    *,
    pitcher_hand: str | None = None,
    opp_bat_sides: list[str] | None = None,
) -> PropProjection | None:
    stats = pitcher_stats_as_of(line.player_id, game_date)
    k9 = stats.get("strikeouts_per_9", 0.0)
    ip = stats.get("innings_pitched", 0.0)
    gs = stats.get("games_started", 0.0)
    whip = stats.get("whip", LEAGUE_WHIP)
    h9 = stats.get("hits_per_9", 8.5)
    era = stats.get("era", LEAGUE_ERA)
    if not k9 or not gs:
        return None
    exp_ip = max(4.0, min(6.7, ip / gs if gs else 5.5))

    opp_k_rate = LEAGUE_K_RATE
    opp_obp = 0.320
    tid = _team_id_by_abbr().get(opp_team_abbr) if opp_team_abbr else None
    if tid:
        try:
            snap = team_stats_as_of(tid, game_date)
            opp_k_rate = snap.strikeout_rate or LEAGUE_K_RATE
            opp_obp = snap.obp or 0.320
        except Exception:
            pass

    # Strikeout platoon: weight this pitcher's K rate vs LHB/RHB by the opposing
    # lineup's actual left/right composition (your "Ks vs lefty/righty" ask).
    k_platoon = 1.0
    if opp_bat_sides:
        k_platoon = pitcher_k_platoon_multiplier(
            line.player_id, pitcher_hand, opp_bat_sides, game_date
        )

    prop = line.prop
    L = line.line
    floor = _line_floor(L)

    if prop == "pitcher_strikeouts":
        opp_adj = 1.0 + (opp_k_rate - LEAGUE_K_RATE) * 1.3
        lam = max(0.0, k9 * exp_ip / 9.0 * opp_adj * k_platoon)
        prob = _poisson_sf(floor, lam)
        return PropProjection(prop, round(lam, 2), round(prob, 4),
                              f"k9={k9:.1f} ip={exp_ip:.1f} oppK={opp_k_rate:.3f} kplt={k_platoon:.2f}")
    if prop == "pitcher_outs":
        mean_outs = exp_ip * 3.0
        # Innings cluster tightly around the expected length (a healthy starter
        # rarely varies more than ~1 inning), so use a narrow normal, not Poisson.
        sd = 2.6
        prob = _normal_sf(L, mean_outs, sd)
        return PropProjection(prop, round(mean_outs, 1), round(prob, 4),
                              f"exp_ip={exp_ip:.1f} sd={sd}")
    if prop == "pitcher_earned_runs":
        lam = era * exp_ip / 9.0 * (1.0 + (opp_obp - 0.320) * 1.5)
        prob = _poisson_sf(floor, lam)
        return PropProjection(prop, round(lam, 2), round(prob, 4), f"era={era:.2f} ip={exp_ip:.1f}")
    if prop == "pitcher_hits_allowed":
        lam = h9 * exp_ip / 9.0 * (1.0 + (opp_obp - 0.320) * 1.2)
        prob = _poisson_sf(floor, lam)
        return PropProjection(prop, round(lam, 2), round(prob, 4), f"h9={h9:.1f} ip={exp_ip:.1f}")
    if prop == "pitcher_walks":
        bb9 = stats.get("walks_per_9") or stats.get("bb_per_9") or 3.2
        lam = max(0.0, float(bb9) * exp_ip / 9.0)
        prob = _poisson_sf(floor, lam)
        return PropProjection(prop, round(lam, 2), round(prob, 4), f"bb9={float(bb9):.1f} ip={exp_ip:.1f}")
    return None


HITTER_PROPS = {
    "batter_hits", "batter_total_bases", "batter_home_runs", "batter_rbis",
    "batter_runs_scored", "batter_walks", "batter_stolen_bases", "batter_singles",
    "batter_doubles", "batter_hits_runs_rbis",
}
PITCHER_PROPS = {
    "pitcher_strikeouts", "pitcher_outs", "pitcher_earned_runs", "pitcher_hits_allowed",
    "pitcher_walks",
}


def project_prop(
    line: PropLine,
    game_date: date,
    opp_starter: dict | None,
    park_hr: float = 1.0,
    opp_pitcher_id: int | None = None,
    *,
    exp_pa: float | None = None,
    run_mult: float = 1.0,
    hr_env_mult: float | None = None,
    opp_bullpen: tuple[float, float] | None = None,
    quality: object | None = None,
    pitcher_hand: str | None = None,
    opp_bat_sides: list[str] | None = None,
) -> PropProjection | None:
    if line.player_id is None:
        return None
    if line.prop in HITTER_PROPS:
        return project_hitter(
            line, game_date, opp_starter, park_hr, opp_pitcher_id,
            exp_pa=exp_pa,
            run_mult=run_mult,
            hr_env_mult=hr_env_mult if hr_env_mult is not None else park_hr,
            opp_bullpen=opp_bullpen,
            quality=quality,
        )
    if line.prop in PITCHER_PROPS:
        return project_pitcher(
            line, game_date, line.opp_abbr,
            pitcher_hand=pitcher_hand,
            opp_bat_sides=opp_bat_sides,
        )
    return None
