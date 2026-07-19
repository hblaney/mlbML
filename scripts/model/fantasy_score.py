"""PrizePicks MLB hitter fantasy score — projection and grading."""

from __future__ import annotations

# Official PrizePicks hitter FS chart (playbook)
FS_POINTS: dict[str, float] = {
    "single": 3.0,
    "double": 5.0,
    "triple": 8.0,
    "home_run": 10.0,
    "run": 2.0,
    "rbi": 2.0,
    "walk": 2.0,
    "hbp": 2.0,
    "stolen_base": 5.0,
}

DEFAULT_PA = 4.2
LEAGUE_ERA = 4.35


def _round_half(value: float) -> float:
    return round(value * 2) / 2


def fs_from_counts(
    singles: int = 0,
    doubles: int = 0,
    triples: int = 0,
    home_runs: int = 0,
    runs: int = 0,
    rbi: int = 0,
    walks: int = 0,
    hbp: int = 0,
    stolen_bases: int = 0,
) -> float:
    return (
        singles * FS_POINTS["single"]
        + doubles * FS_POINTS["double"]
        + triples * FS_POINTS["triple"]
        + home_runs * FS_POINTS["home_run"]
        + runs * FS_POINTS["run"]
        + rbi * FS_POINTS["rbi"]
        + walks * FS_POINTS["walk"]
        + hbp * FS_POINTS["hbp"]
        + stolen_bases * FS_POINTS["stolen_base"]
    )


def fs_from_batting_line(bat: dict) -> float:
    hits = int(bat.get("hits", 0) or 0)
    doubles = int(bat.get("doubles", 0) or 0)
    triples = int(bat.get("triples", 0) or 0)
    home_runs = int(bat.get("homeRuns", 0) or 0)
    singles = max(0, hits - doubles - triples - home_runs)
    return fs_from_counts(
        singles=singles,
        doubles=doubles,
        triples=triples,
        home_runs=home_runs,
        runs=int(bat.get("runs", 0) or 0),
        rbi=int(bat.get("rbi", 0) or 0),
        walks=int(bat.get("baseOnBalls", 0) or 0),
        hbp=int(bat.get("hitByPitch", 0) or 0),
        stolen_bases=int(bat.get("stolenBases", 0) or 0),
    )


def _opp_hitting_boost(opp_pitcher_era: float, opp_pitcher_whip: float) -> float:
    era_adj = 1.0 + (opp_pitcher_era - LEAGUE_ERA) * 0.06
    whip_adj = 1.0 + (opp_pitcher_whip - 1.28) * 0.12
    return max(0.88, min(1.15, (era_adj + whip_adj) / 2.0))


def project_hitter_fs(
    hitter: dict[str, float],
    *,
    expected_pa: float = DEFAULT_PA,
    opp_pitcher_era: float = LEAGUE_ERA,
    opp_pitcher_whip: float = 1.28,
    implied_team_runs: float = 4.5,
) -> float:
    """Expected PrizePicks FS from per-PA rates + matchup/run environment."""
    pa = max(hitter.get("plate_appearances", 0.0), 1.0)
    rates = {
        "single": max(0.0, (hitter.get("hits", 0.0) - hitter.get("doubles", 0.0) - hitter.get("triples", 0.0) - hitter.get("home_runs", 0.0)) / pa),
        "double": hitter.get("doubles", 0.0) / pa,
        "triple": hitter.get("triples", 0.0) / pa,
        "home_run": hitter.get("home_runs", 0.0) / pa,
        "run": hitter.get("runs", 0.0) / pa,
        "rbi": hitter.get("rbi", 0.0) / pa,
        "walk": hitter.get("walks", 0.0) / pa,
        "hbp": hitter.get("hbp", 0.0) / pa,
        "stolen_base": hitter.get("stolen_bases", 0.0) / pa,
    }
    run_env = max(0.85, min(1.15, implied_team_runs / 4.5))
    boost = _opp_hitting_boost(opp_pitcher_era, opp_pitcher_whip) * run_env
    exp_pa = expected_pa * boost
    per_pa_fs = (
        rates["single"] * FS_POINTS["single"]
        + rates["double"] * FS_POINTS["double"]
        + rates["triple"] * FS_POINTS["triple"]
        + rates["home_run"] * FS_POINTS["home_run"]
        + rates["run"] * FS_POINTS["run"]
        + rates["rbi"] * FS_POINTS["rbi"]
        + rates["walk"] * FS_POINTS["walk"]
        + rates["hbp"] * FS_POINTS["hbp"]
        + rates["stolen_base"] * FS_POINTS["stolen_base"]
    )
    return per_pa_fs * exp_pa


def estimate_prizepicks_fs_line(fs_proj: float, ops: float = 0.720) -> float:
    """PrizePicks FS lines often sit well below model fair for star bats."""
    if ops >= 0.900:
        cushion = 2.0
    elif ops >= 0.820:
        cushion = 1.5
    elif ops >= 0.750:
        cushion = 1.0
    else:
        cushion = 0.75
    return max(4.5, _round_half(fs_proj - cushion))


def estimate_prizepicks_k_line(model_k: float, k9: float) -> float:
    """PrizePicks K lines often sit below model fair — especially for high-K arms."""
    if k9 >= 10.0:
        cushion = 1.75
    elif k9 >= 9.5:
        cushion = 1.25
    elif k9 >= 8.5:
        cushion = 0.75
    else:
        cushion = 0.5
    return max(3.5, _round_half(model_k - cushion))


def pick_vs_line(projection: float, line: float, *, min_edge: float = 0.35) -> tuple[str, float]:
    edge = projection - line
    if projection >= line + min_edge:
        return "Over", edge
    if projection <= line - min_edge:
        return "Under", -edge
    return "Pass", edge
