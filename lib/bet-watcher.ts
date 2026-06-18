import type { GamePrediction } from "./data";
import { getTeam } from "./data";
import { isGameFinal, isGameLive, type LiveGameState } from "./live-game";
import { decimalOdds, formatOdds } from "./odds";

export type LegKind = "moneyline" | "over" | "under";

export type BetLeg = {
  id: string;
  gameId: string;
  kind: LegKind;
  teamId?: string;
  line?: number;
  odds?: number;
};

export type LegStatus = "pending" | "winning" | "losing" | "won" | "lost";

export type LegEvaluation = {
  legId: string;
  status: LegStatus;
  detail: string;
  scoreLine: string;
};

export type ParlayStatus = "pending" | "alive" | "won" | "dead";

export type ParlayEvaluation = {
  legs: LegEvaluation[];
  status: ParlayStatus;
  wonLegs: number;
  totalLegs: number;
  headline: string;
};

function gameRuns(live: LiveGameState | null) {
  if (!live?.away || !live?.home) {
    return null;
  }

  return {
    away: live.away.runs,
    home: live.home.runs,
    total: live.away.runs + live.home.runs
  };
}

function teamRuns(teamId: string, game: GamePrediction, live: LiveGameState | null) {
  const runs = gameRuns(live);
  if (!runs) {
    return null;
  }

  if (teamId === game.awayTeam) {
    return { team: runs.away, opponent: runs.home };
  }

  if (teamId === game.homeTeam) {
    return { team: runs.home, opponent: runs.away };
  }

  return null;
}

function formatMatchupScore(game: GamePrediction, live: LiveGameState | null) {
  const runs = gameRuns(live);
  if (!runs) {
    return `${getTeam(game.awayTeam).abbreviation} @ ${getTeam(game.homeTeam).abbreviation}`;
  }

  return `${getTeam(game.awayTeam).abbreviation} ${runs.away} – ${runs.home} ${getTeam(game.homeTeam).abbreviation}`;
}

function evaluateMoneylineLeg(
  leg: BetLeg,
  game: GamePrediction,
  live: LiveGameState | null
): Omit<LegEvaluation, "legId"> {
  const team = leg.teamId ? getTeam(leg.teamId) : null;
  const scoreLine = formatMatchupScore(game, live);

  if (!team) {
    return { status: "pending", detail: "Pick a team", scoreLine };
  }

  const runs = teamRuns(team.id, game, live);
  if (!runs) {
    return { status: "pending", detail: `${team.abbreviation} ML · waiting for first pitch`, scoreLine };
  }

  const final = isGameFinal(live);

  if (final) {
    if (runs.team > runs.opponent) {
      return { status: "won", detail: `${team.abbreviation} ML · final win`, scoreLine };
    }

    return { status: "lost", detail: `${team.abbreviation} ML · final loss`, scoreLine };
  }

  if (runs.team > runs.opponent) {
    return { status: "winning", detail: `${team.abbreviation} ML · leading`, scoreLine };
  }

  if (runs.team < runs.opponent) {
    return { status: "losing", detail: `${team.abbreviation} ML · trailing`, scoreLine };
  }

  return { status: "pending", detail: `${team.abbreviation} ML · tied`, scoreLine };
}

function evaluateTotalLeg(
  leg: BetLeg,
  game: GamePrediction,
  live: LiveGameState | null,
  kind: "over" | "under"
): Omit<LegEvaluation, "legId"> {
  const line = leg.line;
  const scoreLine = formatMatchupScore(game, live);
  const runs = gameRuns(live);
  const label = line == null ? `${kind === "over" ? "Over" : "Under"}` : `${kind === "over" ? "O" : "U"}${line}`;

  if (line == null || !runs) {
    return { status: "pending", detail: `${label} · waiting for live total`, scoreLine };
  }

  const final = isGameFinal(live);
  const total = runs.total;

  if (kind === "over") {
    if (total > line) {
      return { status: "won", detail: `${label} · hit (${total} runs)`, scoreLine };
    }

    if (final) {
      return { status: "lost", detail: `${label} · missed (${total} runs)`, scoreLine };
    }

    return { status: "pending", detail: `${label} · need ${line + 0.5 - total} more (${total} runs)`, scoreLine };
  }

  if (total >= line) {
    return { status: "lost", detail: `${label} · dead (${total} runs)`, scoreLine };
  }

  if (final) {
    return { status: "won", detail: `${label} · hit (${total} runs)`, scoreLine };
  }

  return { status: "winning", detail: `${label} · still alive (${total} runs)`, scoreLine };
}

export function evaluateLeg(
  leg: BetLeg,
  game: GamePrediction,
  live: LiveGameState | null
): LegEvaluation {
  const base =
    leg.kind === "moneyline"
      ? evaluateMoneylineLeg(leg, game, live)
      : evaluateTotalLeg(leg, game, live, leg.kind);

  return { legId: leg.id, ...base };
}

export function evaluateParlay(
  legs: BetLeg[],
  gamesById: Map<string, GamePrediction>,
  liveByGameId: Map<string, LiveGameState | null>
): ParlayEvaluation {
  const evaluations = legs.map((leg) => {
    const game = gamesById.get(leg.gameId);
    if (!game) {
      return {
        legId: leg.id,
        status: "pending" as LegStatus,
        detail: "Game not found on today's board",
        scoreLine: "—"
      };
    }

    return evaluateLeg(leg, game, liveByGameId.get(leg.gameId) ?? null);
  });

  const wonLegs = evaluations.filter((item) => item.status === "won").length;
  const lostLeg = evaluations.some((item) => item.status === "lost");
  const allWon = evaluations.length > 0 && evaluations.every((item) => item.status === "won");
  const anyLive = [...liveByGameId.values()].some((state) => isGameLive(state));

  let status: ParlayStatus = "pending";
  let headline = "Waiting for games";

  if (lostLeg) {
    status = "dead";
    headline = `Parlay dead · ${wonLegs}/${legs.length} legs cleared`;
  } else if (allWon) {
    status = "won";
    headline = `Parlay cashed · ${wonLegs}/${legs.length} legs`;
  } else if (wonLegs > 0 || anyLive) {
    status = "alive";
    headline = `Still alive · ${wonLegs}/${legs.length} legs cleared`;
  }

  return {
    legs: evaluations,
    status,
    wonLegs,
    totalLegs: legs.length,
    headline
  };
}

export function combinedAmericanOdds(legs: BetLeg[]) {
  const decimals = legs.map((leg) => (leg.odds == null ? null : decimalOdds(leg.odds)));
  if (decimals.some((value) => value === null)) {
    return null;
  }

  const combined = decimals.reduce<number>((product, value) => product * (value as number), 1);
  if (combined <= 1) {
    return null;
  }

  if (combined >= 2) {
    return Math.round((combined - 1) * 100);
  }

  return Math.round(-100 / (combined - 1));
}

export function profitFromAmericanOdds(stake: number, americanOdds: number) {
  if (stake <= 0) {
    return 0;
  }

  return stake * (decimalOdds(americanOdds) - 1);
}

export function formatLegSummary(leg: BetLeg, game: GamePrediction) {
  const away = getTeam(game.awayTeam);
  const home = getTeam(game.homeTeam);

  if (leg.kind === "moneyline" && leg.teamId) {
    const team = getTeam(leg.teamId);
    const odds = leg.odds == null ? "" : ` ${formatOdds(leg.odds)}`;
    return `${team.abbreviation} ML${odds} · ${away.abbreviation} @ ${home.abbreviation}`;
  }

  const line = leg.line == null ? "?" : leg.line;
  const prefix = leg.kind === "over" ? `O${line}` : `U${line}`;
  const odds = leg.odds == null ? "" : ` ${formatOdds(leg.odds)}`;
  return `${prefix}${odds} · ${away.abbreviation} @ ${home.abbreviation}`;
}

export function uniqueGameIds(legs: BetLeg[]) {
  return [...new Set(legs.map((leg) => leg.gameId))];
}

export function createLegId() {
  return `leg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}
