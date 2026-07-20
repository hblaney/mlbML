"""Player-level Statcast quality-of-contact, used to regress surface stats.

Season batting lines are noisy: a hitter can run a high average on weak contact
(lucky, due to regress down) or a low average on barrels (unlucky, due to bounce
back). We pull each hitter's recent batted-ball Statcast and turn quality of
contact into multipliers on the projection:

  - hit_mult: from recent xwOBA-on-contact vs league (~.370)
  - hr_mult:  from recent barrel rate vs league (~.080)

Everything is cached per (player, as_of) and wrapped so a pybaseball/network
failure degrades to neutral (1.0) instead of breaking the pipeline.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

# Quality-of-contact is a stable skill signal, so we use a wide recent window and
# take whatever batted balls are available (Statcast mirrors can lag by weeks).
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "player_statcast"
WINDOW_DAYS = 110
MIN_BATTED = 25

LEAGUE_XWOBACON = 0.370
LEAGUE_BARREL = 0.080


@dataclass(frozen=True)
class HitterQuality:
    hit_mult: float
    hr_mult: float
    n_batted: int
    xwobacon: float
    barrel_rate: float


NEUTRAL = HitterQuality(1.0, 1.0, 0, 0.0, 0.0)


def _fetch_batter(player_id: int, start: date, end: date):
    from pybaseball import statcast_batter
    sink = io.StringIO()
    with redirect_stdout(sink), redirect_stderr(sink):
        return statcast_batter(start.isoformat(), end.isoformat(), player_id)


def hitter_quality(player_id: int | None, game_date: date) -> HitterQuality:
    if not player_id:
        return NEUTRAL

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{player_id}_{game_date.isoformat()}.json"
    if cache_path.exists():
        try:
            d = json.loads(cache_path.read_text())
            return HitterQuality(**d)
        except Exception:
            cache_path.unlink(missing_ok=True)

    end = game_date - timedelta(days=1)
    start = end - timedelta(days=WINDOW_DAYS)
    quality = NEUTRAL
    try:
        df = _fetch_batter(player_id, start, end)
        if df is not None and not df.empty and "type" in df.columns:
            batted = df[df["type"] == "X"]
            n = int(len(batted))
            if n >= MIN_BATTED:
                xw = 0.0
                if "estimated_woba_using_speedangle" in batted.columns:
                    vals = batted["estimated_woba_using_speedangle"].dropna()
                    xw = float(vals.mean()) if len(vals) else 0.0
                barrel = 0.0
                if "launch_speed_angle" in batted.columns:
                    bvals = batted["launch_speed_angle"].dropna()
                    barrel = float((bvals == 6).mean()) if len(bvals) else 0.0

                hit_mult = 1.0
                if xw > 0:
                    # sqrt shrink so a hot/cold month nudges rather than dominates
                    hit_mult = max(0.88, min(1.15, (xw / LEAGUE_XWOBACON) ** 0.5))
                hr_mult = 1.0
                if barrel > 0:
                    hr_mult = max(0.70, min(1.60, (barrel / LEAGUE_BARREL) ** 0.5))

                quality = HitterQuality(
                    hit_mult=round(hit_mult, 4),
                    hr_mult=round(hr_mult, 4),
                    n_batted=n,
                    xwobacon=round(xw, 4),
                    barrel_rate=round(barrel, 4),
                )
    except Exception:
        quality = NEUTRAL

    try:
        cache_path.write_text(json.dumps(quality.__dict__))
    except Exception:
        pass
    return quality


if __name__ == "__main__":
    import sys
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 592450  # Aaron Judge
    gd = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date.today()
    q = hitter_quality(pid, gd)
    print(q)
