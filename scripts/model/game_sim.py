"""Plate-appearance Monte Carlo for full MLB games.

Discrete PA outcomes (not pitch-by-pitch). Matchups use log5 / odds-ratio
blending of batter rates × pitcher rates ÷ league averages. Starter hands off
to a bullpen after a fixed batters-faced budget. Extras continue until a winner
(cap 18 innings).

Deterministic when ``seed`` is set (use game_pk for board integrity recomputes).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

# Outcome indices
OUT, K, BB, HBP, SINGLE, DOUBLE, TRIPLE, HR = range(8)
N_OUTCOMES = 8

# League per-PA priors (tuned so mean runs/game ≈ 4.3–4.8 per side).
LEAGUE = np.array(
    [
        0.670,  # OUT (in-play + misc)
        0.220,  # K
        0.080,  # BB
        0.010,  # HBP
        0.138,  # 1B
        0.042,  # 2B
        0.004,  # 3B
        0.030,  # HR
    ],
    dtype=np.float64,
)
LEAGUE = LEAGUE / LEAGUE.sum()
# Extra dampener after log5 — matchups otherwise over-produce runs.
OFFENSE_DAMPEN = 0.82

DEFAULT_STARTER_TBF = 25
DEFAULT_N_SIMS = 8000
MAX_INNINGS = 18


@dataclass(frozen=True)
class PitcherRates:
    """Per-PA outcome probabilities for a pitcher (vs league-average batter)."""

    probs: np.ndarray  # shape (8,)


@dataclass(frozen=True)
class BatterRates:
    probs: np.ndarray  # shape (8,)


@dataclass(frozen=True)
class TeamSide:
    batters: tuple[BatterRates, ...]  # length 9
    starter: PitcherRates
    bullpen: PitcherRates
    starter_tbf: int = DEFAULT_STARTER_TBF


@dataclass(frozen=True)
class SimResult:
    home_win_prob: float
    away_win_prob: float
    mean_home_runs: float
    mean_away_runs: float
    n_sims: int
    home_wins: int
    away_wins: int


def _clip_probs(p: np.ndarray) -> np.ndarray:
    p = np.maximum(p, 1e-6)
    return p / p.sum()


def batter_rates_from_stats(stats: dict[str, float]) -> BatterRates:
    pa = max(float(stats.get("plate_appearances", 0.0)), 1.0)
    k = float(stats.get("strikeouts", 0.0)) / pa
    bb = float(stats.get("walks", 0.0)) / pa
    hbp = float(stats.get("hbp", 0.0)) / pa
    hr = float(stats.get("home_runs", 0.0)) / pa
    doubles = float(stats.get("doubles", 0.0)) / pa
    triples = float(stats.get("triples", 0.0)) / pa
    hits = float(stats.get("hits", 0.0)) / pa
    singles = max(0.0, hits - doubles - triples - hr)
    # Shrink thin samples toward league.
    w = min(1.0, pa / 120.0)
    raw = np.array(
        [
            max(0.0, 1.0 - k - bb - hbp - singles - doubles - triples - hr),
            k,
            bb,
            hbp,
            singles,
            doubles,
            triples,
            hr,
        ],
        dtype=np.float64,
    )
    raw = _clip_probs(raw)
    blended = _clip_probs(w * raw + (1.0 - w) * LEAGUE)
    return BatterRates(probs=blended)


def pitcher_rates_from_stats(stats: dict[str, float], *, park_hr: float = 1.0) -> PitcherRates:
    """Convert per-9 pitcher lines to per-PA outcome probs."""
    k9 = float(stats.get("strikeouts_per_9", 8.5) or 8.5)
    bb9 = float(stats.get("walks_per_9", 3.2) or 3.2)
    h9 = float(stats.get("hits_per_9", 8.5) or 8.5)
    hr9 = float(stats.get("home_runs_per_9", 1.15) or 1.15) * float(park_hr)
    # League-typical ~38 PA / 9 IP
    pa9 = 38.0
    k = min(0.40, k9 / pa9)
    bb = min(0.20, bb9 / pa9)
    hbp = 0.01
    hr = min(0.08, hr9 / pa9)
    hits = min(0.28, h9 / pa9)
    # Split hits into 1B/2B/3B/HR with league hit-type mix (HR already set).
    non_hr_hits = max(0.0, hits - hr)
    # League share of non-HR hits: 1B ~75%, 2B ~22%, 3B ~3%
    singles = non_hr_hits * 0.75
    doubles = non_hr_hits * 0.22
    triples = non_hr_hits * 0.03
    out = max(0.0, 1.0 - k - bb - hbp - singles - doubles - triples - hr)
    raw = _clip_probs(
        np.array([out, k, bb, hbp, singles, doubles, triples, hr], dtype=np.float64)
    )
    ip = float(stats.get("innings_pitched", 0.0) or 0.0)
    w = min(1.0, ip / 60.0)
    return PitcherRates(probs=_clip_probs(w * raw + (1.0 - w) * LEAGUE))


def bullpen_rates_from_era_whip(
    era: float,
    whip: float,
    *,
    park_hr: float = 1.0,
) -> PitcherRates:
    """Map bullpen ERA/WHIP onto per-PA rates (league K/BB skeleton)."""
    era = max(1.5, min(9.0, float(era)))
    whip = max(0.7, min(2.5, float(whip)))
    # Scale offense allowed vs league (~4.10 ERA, 1.32 WHIP).
    run_scale = era / 4.10
    obp_scale = whip / 1.32
    base = LEAGUE.copy()
    # More WHIP → more BB/HBP/hits; more ERA → more HR; fewer outs.
    base[BB] *= obp_scale
    base[HBP] *= obp_scale
    base[SINGLE] *= obp_scale
    base[DOUBLE] *= obp_scale * (0.85 + 0.15 * run_scale)
    base[TRIPLE] *= obp_scale
    base[HR] *= run_scale * park_hr
    base[K] *= max(0.7, 1.15 - 0.15 * run_scale)
    base[OUT] *= max(0.55, 1.25 - 0.25 * obp_scale)
    return PitcherRates(probs=_clip_probs(base))


def log5_matchup(batter: BatterRates, pitcher: PitcherRates) -> np.ndarray:
    """Bill James log5 per outcome, then renormalize."""
    b = batter.probs
    p = pitcher.probs
    lg = LEAGUE
    out = np.empty(N_OUTCOMES, dtype=np.float64)
    for i in range(N_OUTCOMES):
        bi, pi, li = b[i], p[i], max(lg[i], 1e-9)
        # Odds-ratio form of log5
        num = bi * pi / li
        den = num + (1.0 - bi) * (1.0 - pi) / max(1.0 - li, 1e-9)
        out[i] = num / den if den > 0 else li
    out = _clip_probs(out)
    # Pull non-out events slightly toward outs so run environment stays realistic.
    if OFFENSE_DAMPEN < 1.0:
        for i in range(1, N_OUTCOMES):
            out[i] *= OFFENSE_DAMPEN
        out[OUT] = max(out[OUT], 1.0 - out[1:].sum())
        out = _clip_probs(out)
    return out


def _apply_walk(bases: list[int]) -> int:
    runs = 0
    if bases[0] and bases[1] and bases[2]:
        runs = 1
    if bases[0] and bases[1]:
        bases[2] = 1
    if bases[0]:
        bases[1] = 1
    bases[0] = 1
    return runs


def resolve_pa(outcome: int, bases: list[int], outs: int) -> tuple[int, int]:
    """Apply one PA. Returns (runs, new_outs)."""
    if outcome in (OUT, K):
        return 0, outs + 1
    if outcome in (BB, HBP):
        return _apply_walk(bases), outs
    if outcome == SINGLE:
        # Conservative: 3rd scores; 2nd → 3rd; 1st → 2nd (no auto-score from 2nd).
        runs = 1 if bases[2] else 0
        first, second = bases[0], bases[1]
        bases[0], bases[1], bases[2] = 1, first, second
        return runs, outs
    if outcome == DOUBLE:
        # 2nd/3rd score; 1st → 3rd; batter to 2nd.
        runs = (1 if bases[1] else 0) + (1 if bases[2] else 0)
        first = bases[0]
        bases[0], bases[1], bases[2] = 0, 1, first
        return runs, outs
    if outcome == TRIPLE:
        runs = sum(bases)
        bases[:] = [0, 0, 1]
        return runs, outs
    if outcome == HR:
        runs = 1 + sum(bases)
        bases[:] = [0, 0, 0]
        return runs, outs
    return 0, outs + 1


def _precompute_matchups(offense: TeamSide, pitcher: PitcherRates) -> np.ndarray:
    """Return (9, 8) cumulative probs for each batter vs this pitcher."""
    cdf = np.empty((9, N_OUTCOMES), dtype=np.float64)
    for i, batter in enumerate(offense.batters):
        p = log5_matchup(batter, pitcher)
        cdf[i] = np.cumsum(p)
    return cdf


def _draw_outcome(cdf_row: np.ndarray, u: float) -> int:
    for i, c in enumerate(cdf_row):
        if u <= c:
            return i
    return OUT


def simulate_game_once(
    home: TeamSide,
    away: TeamSide,
    rng: np.random.Generator,
    *,
    away_vs_home_starter: np.ndarray,
    away_vs_home_pen: np.ndarray,
    home_vs_away_starter: np.ndarray,
    home_vs_away_pen: np.ndarray,
) -> tuple[int, int]:
    """Return (away_runs, home_runs) for one simulated game."""
    away_score = 0
    home_score = 0
    away_slot = 0
    home_slot = 0
    home_tbf = 0  # batters faced by home pitcher (facing away lineup)
    away_tbf = 0

    for inning in range(1, MAX_INNINGS + 1):
        # Top: away bats
        bases = [0, 0, 0]
        outs = 0
        while outs < 3:
            use_pen = home_tbf >= home.starter_tbf
            cdf = away_vs_home_pen if use_pen else away_vs_home_starter
            u = float(rng.random())
            outcome = _draw_outcome(cdf[away_slot], u)
            runs, outs = resolve_pa(outcome, bases, outs)
            away_score += runs
            away_slot = (away_slot + 1) % 9
            home_tbf += 1

        # Bottom: home bats (walk-off / don't play if home already ahead after 9+)
        if inning >= 9 and home_score > away_score:
            break

        bases = [0, 0, 0]
        outs = 0
        while outs < 3:
            use_pen = away_tbf >= away.starter_tbf
            cdf = home_vs_away_pen if use_pen else home_vs_away_starter
            u = float(rng.random())
            outcome = _draw_outcome(cdf[home_slot], u)
            runs, outs = resolve_pa(outcome, bases, outs)
            home_score += runs
            home_slot = (home_slot + 1) % 9
            away_tbf += 1
            # Walk-off
            if inning >= 9 and home_score > away_score:
                return away_score, home_score

        if inning >= 9 and home_score != away_score:
            break

    # Still tied after max innings — coin flip by one more half (rare).
    if home_score == away_score:
        if rng.random() < 0.5:
            home_score += 1
        else:
            away_score += 1
    return away_score, home_score


def simulate_game(
    home: TeamSide,
    away: TeamSide,
    *,
    n_sims: int = DEFAULT_N_SIMS,
    seed: int | None = None,
) -> SimResult:
    rng = np.random.default_rng(seed)
    away_vs_home_starter = _precompute_matchups(away, home.starter)
    away_vs_home_pen = _precompute_matchups(away, home.bullpen)
    home_vs_away_starter = _precompute_matchups(home, away.starter)
    home_vs_away_pen = _precompute_matchups(home, away.bullpen)

    home_wins = 0
    away_wins = 0
    home_runs_total = 0
    away_runs_total = 0
    for _ in range(n_sims):
        ar, hr = simulate_game_once(
            home,
            away,
            rng,
            away_vs_home_starter=away_vs_home_starter,
            away_vs_home_pen=away_vs_home_pen,
            home_vs_away_starter=home_vs_away_starter,
            home_vs_away_pen=home_vs_away_pen,
        )
        away_runs_total += ar
        home_runs_total += hr
        if hr > ar:
            home_wins += 1
        else:
            away_wins += 1
    n = float(n_sims)
    return SimResult(
        home_win_prob=home_wins / n,
        away_win_prob=away_wins / n,
        mean_home_runs=home_runs_total / n,
        mean_away_runs=away_runs_total / n,
        n_sims=n_sims,
        home_wins=home_wins,
        away_wins=away_wins,
    )


def make_team_side(
    batter_stats: Sequence[dict[str, float]],
    starter_stats: dict[str, float],
    bullpen_era: float,
    bullpen_whip: float,
    *,
    park_hr: float = 1.0,
    starter_tbf: int = DEFAULT_STARTER_TBF,
) -> TeamSide:
    batters = tuple(batter_rates_from_stats(s) for s in batter_stats)
    while len(batters) < 9:
        batters = batters + (BatterRates(probs=LEAGUE.copy()),)
    batters = batters[:9]
    return TeamSide(
        batters=batters,
        starter=pitcher_rates_from_stats(starter_stats, park_hr=park_hr),
        bullpen=bullpen_rates_from_era_whip(bullpen_era, bullpen_whip, park_hr=park_hr),
        starter_tbf=starter_tbf,
    )
