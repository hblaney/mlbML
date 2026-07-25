"""Plate-appearance Monte Carlo for full MLB games.

Discrete PA outcomes (not pitch-by-pitch). Matchups use log5 / odds-ratio
blending of batter rates × pitcher rates ÷ league averages.

Pitching changes (v2):
  - Starter exits on TBF budget, run hook, max innings, or early deficit.
  - Bullpen roles: long relief / middle / setup / closer, chosen by inning + score.
  - Relievers are capped ~1 inning of work, then another arm of the same tier.

Deterministic when ``seed`` is set (use game_pk for board integrity recomputes).
"""

from __future__ import annotations

import math
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
DEFAULT_STARTER_RUN_HOOK = 5
DEFAULT_STARTER_MAX_IP = 7
DEFAULT_RELIEVER_TBF = 5
DEFAULT_N_SIMS = 8000
MAX_INNINGS = 18

ROLE_STARTER = 0
ROLE_LONG = 1
ROLE_MIDDLE = 2
ROLE_SETUP = 3
ROLE_CLOSER = 4
N_ROLES = 5


@dataclass(frozen=True)
class PitcherRates:
    """Per-PA outcome probabilities for a pitcher (vs league-average batter)."""

    probs: np.ndarray  # shape (8,)


@dataclass(frozen=True)
class BatterRates:
    probs: np.ndarray  # shape (8,)


@dataclass(frozen=True)
class BullpenStaff:
    """Role-split bullpen derived from team pen ERA/WHIP (+ fatigue)."""

    long_relief: PitcherRates
    middle: PitcherRates
    setup: PitcherRates
    closer: PitcherRates
    fatigue_ip3: float = 0.0


@dataclass(frozen=True)
class TeamSide:
    batters: tuple[BatterRates, ...]  # length 9
    starter: PitcherRates
    pen: BullpenStaff
    starter_tbf: int = DEFAULT_STARTER_TBF
    starter_run_hook: int = DEFAULT_STARTER_RUN_HOOK
    starter_max_ip: int = DEFAULT_STARTER_MAX_IP
    reliever_tbf: int = DEFAULT_RELIEVER_TBF

    @property
    def bullpen(self) -> PitcherRates:
        """Back-compat: generic pen ≈ middle relief."""
        return self.pen.middle


@dataclass(frozen=True)
class SimResult:
    home_win_prob: float
    away_win_prob: float
    mean_home_runs: float
    mean_away_runs: float
    n_sims: int
    home_wins: int
    away_wins: int


@dataclass(frozen=True)
class OncePropBox:
    """Per-sim counting stats from the same PA draws as the moneyline sim."""

    away_hits: tuple[int, ...]  # length 9, lineup order
    home_hits: tuple[int, ...]
    away_tb: tuple[int, ...]
    home_tb: tuple[int, ...]
    # Starter pitching: home starter faces away lineup; away starter faces home.
    home_starter_k: int
    away_starter_k: int
    home_starter_ha: int
    away_starter_ha: int


@dataclass(frozen=True)
class OnceResult:
    away_runs: int
    home_runs: int
    props: OncePropBox


# Shared sentinel so the moneyline path (track_props=False) allocates nothing.
_EMPTY_PROP_BOX = OncePropBox((), (), (), (), 0, 0, 0, 0)


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
    quality: float = 1.0,
) -> PitcherRates:
    """Map bullpen ERA/WHIP onto per-PA rates.

    ``quality`` < 1.0 = better arm (closer/setup); > 1.0 = worse (long relief).
    """
    era = max(1.5, min(9.0, float(era) * float(quality)))
    whip = max(0.7, min(2.5, float(whip) * (0.5 + 0.5 * float(quality))))
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


def build_bullpen_staff(
    era: float,
    whip: float,
    *,
    park_hr: float = 1.0,
    fatigue_ip3: float = 0.0,
) -> BullpenStaff:
    """Split team pen into roles. Fatigue makes middle/long worse, closer less so."""
    fat = max(0.0, float(fatigue_ip3))
    # ~3+ IP in last 3 days starts to matter; 6+ IP is a tired pen.
    fat_scale = 1.0 + min(0.25, 0.04 * fat)
    # Mild role splits — extreme closer/setup quality crushed late offense (~3 R/G).
    return BullpenStaff(
        long_relief=bullpen_rates_from_era_whip(
            era, whip, park_hr=park_hr, quality=1.12 * fat_scale
        ),
        middle=bullpen_rates_from_era_whip(
            era, whip, park_hr=park_hr, quality=1.02 * fat_scale
        ),
        setup=bullpen_rates_from_era_whip(
            era, whip, park_hr=park_hr, quality=0.95 * (1.0 + 0.4 * (fat_scale - 1.0))
        ),
        closer=bullpen_rates_from_era_whip(
            era, whip, park_hr=park_hr, quality=0.90 * (1.0 + 0.3 * (fat_scale - 1.0))
        ),
        fatigue_ip3=fat,
    )


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


def _precompute_staff(offense: TeamSide, defense: TeamSide) -> np.ndarray:
    """Return (5 roles, 9 batters, 8 outcomes) CDF stack for one defense."""
    arms = (
        defense.starter,
        defense.pen.long_relief,
        defense.pen.middle,
        defense.pen.setup,
        defense.pen.closer,
    )
    out = np.empty((N_ROLES, 9, N_OUTCOMES), dtype=np.float64)
    for role, arm in enumerate(arms):
        out[role] = _precompute_matchups(offense, arm)
    return out


def _draw_outcome(cdf_row: np.ndarray, u: float) -> int:
    for i, c in enumerate(cdf_row):
        if u <= c:
            return i
    return OUT


def _starter_should_exit(
    *,
    tbf: int,
    runs: int,
    outs_recorded: int,
    tbf_limit: int,
    run_hook: int,
    max_ip: int,
    defense_lead: int,
) -> bool:
    ip = outs_recorded // 3
    if tbf >= tbf_limit:
        return True
    if runs >= run_hook:
        return True
    if ip >= max_ip:
        return True
    # Quick hook when getting blown out after 4–5 IP.
    if ip >= 5 and defense_lead <= -3:
        return True
    if ip >= 4 and runs >= 4 and defense_lead <= -2:
        return True
    return False


def _pick_reliever_role(
    *,
    inning: int,
    defense_lead: int,
    starter_ip: int,
) -> int:
    """Choose bullpen role from game state (defense perspective)."""
    # Save situation: 9th+ with a lead of 1–3 (classic closer).
    if inning >= 9 and 1 <= defense_lead <= 3:
        return ROLE_CLOSER
    # Hold / bridge: 8th with any lead, or 9th with bigger lead.
    if inning >= 8 and defense_lead >= 1:
        return ROLE_SETUP
    # Tied late / extras — high-leverage setup arm.
    if inning >= 9 and defense_lead == 0:
        return ROLE_SETUP
    # Starter barely made it — long man.
    if starter_ip <= 4:
        return ROLE_LONG
    return ROLE_MIDDLE


def _credit_batter(hits: list[int], tb: list[int], slot: int, outcome: int) -> None:
    if outcome == SINGLE:
        hits[slot] += 1
        tb[slot] += 1
    elif outcome == DOUBLE:
        hits[slot] += 1
        tb[slot] += 2
    elif outcome == TRIPLE:
        hits[slot] += 1
        tb[slot] += 3
    elif outcome == HR:
        hits[slot] += 1
        tb[slot] += 4


def simulate_game_once(
    home: TeamSide,
    away: TeamSide,
    rng: np.random.Generator,
    *,
    away_vs_home: np.ndarray,
    home_vs_away: np.ndarray,
    track_props: bool = True,
) -> OnceResult:
    """Simulate one game; return runs (+ per-player prop stats when track_props).

    The moneyline board only needs runs/wins, so it passes track_props=False to
    skip per-PA batter crediting and prop bookkeeping — that overhead on every
    sim was silently slowing the core sim by a large factor.
    """
    away_score = 0
    home_score = 0
    away_slot = 0
    home_slot = 0
    away_hits = [0] * 9
    home_hits = [0] * 9
    away_tb = [0] * 9
    home_tb = [0] * 9
    home_starter_k = home_starter_ha = 0
    away_starter_k = away_starter_ha = 0

    # Defense pitching state for home (faces away) and away (faces home).
    home_starter_out = False
    away_starter_out = False
    home_st_tbf = home_st_runs = home_st_outs = 0
    away_st_tbf = away_st_runs = away_st_outs = 0
    home_rel_tbf = 0
    away_rel_tbf = 0
    home_role = ROLE_STARTER
    away_role = ROLE_STARTER

    for inning in range(1, MAX_INNINGS + 1):
        # Top: away bats, home pitches
        bases = [0, 0, 0]
        outs = 0
        while outs < 3:
            lead = home_score - away_score
            if not home_starter_out:
                if _starter_should_exit(
                    tbf=home_st_tbf,
                    runs=home_st_runs,
                    outs_recorded=home_st_outs,
                    tbf_limit=home.starter_tbf,
                    run_hook=home.starter_run_hook,
                    max_ip=home.starter_max_ip,
                    defense_lead=lead,
                ):
                    home_starter_out = True
                    home_rel_tbf = 0
                    home_role = _pick_reliever_role(
                        inning=inning,
                        defense_lead=lead,
                        starter_ip=home_st_outs // 3,
                    )
            if home_starter_out:
                # New arm each ~reliever_tbf, re-pick role from live score.
                if home_rel_tbf >= home.reliever_tbf:
                    home_rel_tbf = 0
                    home_role = _pick_reliever_role(
                        inning=inning,
                        defense_lead=lead,
                        starter_ip=home_st_outs // 3,
                    )
                role = home_role
            else:
                role = ROLE_STARTER

            u = float(rng.random())
            outcome = _draw_outcome(away_vs_home[role, away_slot], u)
            prev_outs = outs
            bat_slot = away_slot
            runs, outs = resolve_pa(outcome, bases, outs)
            away_score += runs
            if track_props:
                _credit_batter(away_hits, away_tb, bat_slot, outcome)
            away_slot = (away_slot + 1) % 9
            if role == ROLE_STARTER:
                home_st_tbf += 1
                home_st_runs += runs
                home_st_outs += max(0, outs - prev_outs)
                if track_props:
                    if outcome == K:
                        home_starter_k += 1
                    elif outcome in (SINGLE, DOUBLE, TRIPLE, HR):
                        home_starter_ha += 1
            else:
                home_rel_tbf += 1

        # Bottom: home bats (skip if home already ahead after 9+)
        if inning >= 9 and home_score > away_score:
            break

        bases = [0, 0, 0]
        outs = 0
        while outs < 3:
            lead = away_score - home_score  # away defense lead
            if not away_starter_out:
                if _starter_should_exit(
                    tbf=away_st_tbf,
                    runs=away_st_runs,
                    outs_recorded=away_st_outs,
                    tbf_limit=away.starter_tbf,
                    run_hook=away.starter_run_hook,
                    max_ip=away.starter_max_ip,
                    defense_lead=lead,
                ):
                    away_starter_out = True
                    away_rel_tbf = 0
                    away_role = _pick_reliever_role(
                        inning=inning,
                        defense_lead=lead,
                        starter_ip=away_st_outs // 3,
                    )
            if away_starter_out:
                if away_rel_tbf >= away.reliever_tbf:
                    away_rel_tbf = 0
                    away_role = _pick_reliever_role(
                        inning=inning,
                        defense_lead=lead,
                        starter_ip=away_st_outs // 3,
                    )
                role = away_role
            else:
                role = ROLE_STARTER

            u = float(rng.random())
            outcome = _draw_outcome(home_vs_away[role, home_slot], u)
            prev_outs = outs
            bat_slot = home_slot
            runs, outs = resolve_pa(outcome, bases, outs)
            home_score += runs
            if track_props:
                _credit_batter(home_hits, home_tb, bat_slot, outcome)
            home_slot = (home_slot + 1) % 9
            if role == ROLE_STARTER:
                away_st_tbf += 1
                away_st_runs += runs
                away_st_outs += max(0, outs - prev_outs)
                if track_props:
                    if outcome == K:
                        away_starter_k += 1
                    elif outcome in (SINGLE, DOUBLE, TRIPLE, HR):
                        away_starter_ha += 1
            else:
                away_rel_tbf += 1
            # Walk-off
            if inning >= 9 and home_score > away_score:
                return OnceResult(
                    away_score,
                    home_score,
                    OncePropBox(
                        tuple(away_hits),
                        tuple(home_hits),
                        tuple(away_tb),
                        tuple(home_tb),
                        home_starter_k,
                        away_starter_k,
                        home_starter_ha,
                        away_starter_ha,
                    ) if track_props else _EMPTY_PROP_BOX,
                )

        if inning >= 9 and home_score != away_score:
            break

    # Still tied after max innings — coin flip (rare).
    if home_score == away_score:
        if rng.random() < 0.5:
            home_score += 1
        else:
            away_score += 1
    return OnceResult(
        away_score,
        home_score,
        OncePropBox(
            tuple(away_hits),
            tuple(home_hits),
            tuple(away_tb),
            tuple(home_tb),
            home_starter_k,
            away_starter_k,
            home_starter_ha,
            away_starter_ha,
        ) if track_props else _EMPTY_PROP_BOX,
    )


def simulate_game(
    home: TeamSide,
    away: TeamSide,
    *,
    n_sims: int = DEFAULT_N_SIMS,
    seed: int | None = None,
) -> SimResult:
    rng = np.random.default_rng(seed)
    away_vs_home = _precompute_staff(away, home)
    home_vs_away = _precompute_staff(home, away)

    home_wins = 0
    away_wins = 0
    home_runs_total = 0
    away_runs_total = 0
    for _ in range(n_sims):
        once = simulate_game_once(
            home,
            away,
            rng,
            away_vs_home=away_vs_home,
            home_vs_away=home_vs_away,
            track_props=False,
        )
        ar, hr = once.away_runs, once.home_runs
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


@dataclass(frozen=True)
class PropSimBundle:
    """Empirical distributions from PA Monte Carlo (same engine as moneyline)."""

    n_sims: int
    # player_id -> list of per-sim counts
    hits: dict[int, tuple[int, ...]]
    total_bases: dict[int, tuple[int, ...]]
    starter_strikeouts: dict[int, tuple[int, ...]]
    starter_hits_allowed: dict[int, tuple[int, ...]]

    def mean(self, store: dict[int, tuple[int, ...]], player_id: int) -> float | None:
        samples = store.get(player_id)
        if not samples:
            return None
        return float(sum(samples)) / float(len(samples))

    def prob_over(self, store: dict[int, tuple[int, ...]], player_id: int, line: float) -> float | None:
        samples = store.get(player_id)
        if not samples:
            return None
        # Match prop_projections._line_floor: Over 1.5 needs count >= 2.
        need = int(math.floor(float(line))) + 1
        n_hit = sum(1 for c in samples if c >= need)
        return n_hit / float(len(samples))

    def store_for(self, prop: str) -> dict[int, tuple[int, ...]] | None:
        return {
            "batter_hits": self.hits,
            "batter_total_bases": self.total_bases,
            "pitcher_strikeouts": self.starter_strikeouts,
            "pitcher_hits_allowed": self.starter_hits_allowed,
        }.get(prop)

    def leg_bool(
        self, prop: str, player_id: int, line: float, side: str,
    ) -> tuple[bool, ...] | None:
        """Per-sim win/loss vector for one leg, aligned by sim index.

        Over 1.5 needs count >= 2; Under 1.5 needs count <= 1. Same-index across
        players in one game bundle, so ANDing vectors gives the true joint.
        """
        store = self.store_for(prop)
        if store is None:
            return None
        samples = store.get(int(player_id))
        if not samples:
            return None
        need = int(math.floor(float(line))) + 1
        if side == "Under":
            return tuple(c < need for c in samples)
        return tuple(c >= need for c in samples)

    def joint_prob(
        self, legs: Sequence[tuple[str, int, float, str]],
    ) -> tuple[float, float] | None:
        """(correlated joint P(all hit), independent product of raw marginals).

        Correlated number counts sims where every leg hits from the SAME game
        draws — that's the correlation edge. Independent product is the naive
        book assumption; ratio shows how much the legs help/hurt each other.
        """
        vecs: list[tuple[bool, ...]] = []
        marg: list[float] = []
        for prop, pid, line, side in legs:
            v = self.leg_bool(prop, int(pid), float(line), side)
            if v is None:
                return None
            vecs.append(v)
            marg.append(sum(1 for b in v if b) / float(len(v)))
        n = len(vecs[0])
        if any(len(v) != n for v in vecs):
            return None
        all_hit = sum(1 for i in range(n) if all(v[i] for v in vecs))
        joint = all_hit / float(n)
        indep = 1.0
        for m in marg:
            indep *= m
        return joint, indep


def simulate_prop_dists(
    home: TeamSide,
    away: TeamSide,
    *,
    away_batter_ids: Sequence[int],
    home_batter_ids: Sequence[int],
    away_starter_id: int | None,
    home_starter_id: int | None,
    n_sims: int = 2000,
    seed: int | None = None,
) -> PropSimBundle:
    """Run the PA sim and accumulate per-player prop counting stats."""
    if len(away_batter_ids) < 9 or len(home_batter_ids) < 9:
        raise ValueError("need 9 batter ids per side")
    rng = np.random.default_rng(seed)
    away_vs_home = _precompute_staff(away, home)
    home_vs_away = _precompute_staff(home, away)

    away_hits_s: list[list[int]] = [[] for _ in range(9)]
    home_hits_s: list[list[int]] = [[] for _ in range(9)]
    away_tb_s: list[list[int]] = [[] for _ in range(9)]
    home_tb_s: list[list[int]] = [[] for _ in range(9)]
    home_k_s: list[int] = []
    away_k_s: list[int] = []
    home_ha_s: list[int] = []
    away_ha_s: list[int] = []

    for _ in range(n_sims):
        once = simulate_game_once(
            home,
            away,
            rng,
            away_vs_home=away_vs_home,
            home_vs_away=home_vs_away,
        )
        box = once.props
        for i in range(9):
            away_hits_s[i].append(box.away_hits[i])
            home_hits_s[i].append(box.home_hits[i])
            away_tb_s[i].append(box.away_tb[i])
            home_tb_s[i].append(box.home_tb[i])
        home_k_s.append(box.home_starter_k)
        away_k_s.append(box.away_starter_k)
        home_ha_s.append(box.home_starter_ha)
        away_ha_s.append(box.away_starter_ha)

    hits: dict[int, tuple[int, ...]] = {}
    tb: dict[int, tuple[int, ...]] = {}
    for i, pid in enumerate(away_batter_ids[:9]):
        hits[int(pid)] = tuple(away_hits_s[i])
        tb[int(pid)] = tuple(away_tb_s[i])
    for i, pid in enumerate(home_batter_ids[:9]):
        hits[int(pid)] = tuple(home_hits_s[i])
        tb[int(pid)] = tuple(home_tb_s[i])

    starter_k: dict[int, tuple[int, ...]] = {}
    starter_ha: dict[int, tuple[int, ...]] = {}
    if home_starter_id:
        starter_k[int(home_starter_id)] = tuple(home_k_s)
        starter_ha[int(home_starter_id)] = tuple(home_ha_s)
    if away_starter_id:
        starter_k[int(away_starter_id)] = tuple(away_k_s)
        starter_ha[int(away_starter_id)] = tuple(away_ha_s)

    return PropSimBundle(
        n_sims=n_sims,
        hits=hits,
        total_bases=tb,
        starter_strikeouts=starter_k,
        starter_hits_allowed=starter_ha,
    )


def make_team_side(
    batter_stats: Sequence[dict[str, float]],
    starter_stats: dict[str, float],
    bullpen_era: float,
    bullpen_whip: float,
    *,
    park_hr: float = 1.0,
    starter_tbf: int = DEFAULT_STARTER_TBF,
    fatigue_ip3: float = 0.0,
) -> TeamSide:
    batters = tuple(batter_rates_from_stats(s) for s in batter_stats)
    while len(batters) < 9:
        batters = batters + (BatterRates(probs=LEAGUE.copy()),)
    batters = batters[:9]
    return TeamSide(
        batters=batters,
        starter=pitcher_rates_from_stats(starter_stats, park_hr=park_hr),
        pen=build_bullpen_staff(
            bullpen_era,
            bullpen_whip,
            park_hr=park_hr,
            fatigue_ip3=fatigue_ip3,
        ),
        starter_tbf=starter_tbf,
    )
