import { GamePrediction } from "./data";

export type LiveGameTeamLine = {
  teamId: string;
  runs: number;
  hits: number;
  errors: number;
};

export type LiveGameState = {
  status: string;
  abstractStatus?: string;
  inning: string;
  away?: LiveGameTeamLine;
  home?: LiveGameTeamLine;
  probablePitchers?: {
    away?: string;
    home?: string;
  };
  recentPlays: string[];
};

type LiveFeedResponse = {
  gameData?: {
    status?: {
      detailedState?: string;
      abstractGameState?: string;
      codedGameState?: string;
    };
    probablePitchers?: {
      away?: { fullName?: string };
      home?: { fullName?: string };
    };
  };
  liveData?: {
    linescore?: {
      currentInningOrdinal?: string;
      inningState?: string;
      teams?: {
        away?: { runs?: number; hits?: number; errors?: number };
        home?: { runs?: number; hits?: number; errors?: number };
      };
    };
    plays?: {
      allPlays?: {
        result?: { description?: string };
        about?: { inning?: number; halfInning?: string };
      }[];
    };
  };
};

type ScheduleGame = {
  gamePk?: number;
  status?: {
    detailedState?: string;
    abstractGameState?: string;
    codedGameState?: string;
  };
  teams?: {
    away?: { score?: number; team?: { id?: number } };
    home?: { score?: number; team?: { id?: number } };
  };
  linescore?: {
    currentInningOrdinal?: string;
    inningState?: string;
    teams?: {
      away?: { runs?: number; hits?: number; errors?: number };
      home?: { runs?: number; hits?: number; errors?: number };
    };
  };
  probablePitchers?: {
    away?: { fullName?: string };
    home?: { fullName?: string };
  };
};

type ScheduleResponse = {
  dates?: { games?: ScheduleGame[] }[];
};

export function getGamePk(game: GamePrediction) {
  if (game.gamePk != null && Number.isFinite(Number(game.gamePk))) {
    return String(game.gamePk);
  }
  const match = game.id.match(/-(\d+)$/);
  return match?.[1] ?? null;
}

function isFinalStatus(detailed: string, abstract?: string, coded?: string) {
  const detailedLower = detailed.toLowerCase();
  const abstractLower = (abstract ?? "").toLowerCase();
  const codedUpper = (coded ?? "").toUpperCase();
  return (
    abstractLower === "final" ||
    codedUpper === "F" ||
    detailedLower.includes("final") ||
    detailedLower.includes("game over") ||
    detailedLower.includes("completed")
  );
}

function isLiveStatus(detailed: string, abstract?: string) {
  const detailedLower = detailed.toLowerCase();
  const abstractLower = (abstract ?? "").toLowerCase();
  if (isFinalStatus(detailed, abstract)) {
    return false;
  }
  return (
    abstractLower === "live" ||
    detailedLower.includes("progress") ||
    detailedLower.includes("live") ||
    detailedLower.includes("manager challenge")
  );
}

function formatInningFromParts(
  detailed: string,
  abstract: string | undefined,
  coded: string | undefined,
  linescore?: { currentInningOrdinal?: string; inningState?: string }
) {
  if (isFinalStatus(detailed, abstract, coded)) {
    return "Final";
  }
  if (!linescore?.currentInningOrdinal) {
    return "Pregame";
  }
  return [linescore.inningState, linescore.currentInningOrdinal].filter(Boolean).join(" ");
}

function formatInning(feed: LiveFeedResponse) {
  const status = feed.gameData?.status;
  return formatInningFromParts(
    status?.detailedState ?? "",
    status?.abstractGameState,
    status?.codedGameState,
    feed.liveData?.linescore
  );
}

export function formatInningNatural(inning: string) {
  if (inning.toLowerCase() === "final") {
    return "final";
  }

  const match = inning.match(/^(Top|Bottom)\s+(\d+(?:st|nd|rd|th))$/i);

  if (!match) {
    return inning.toLowerCase();
  }

  const half = match[1].toLowerCase() === "top" ? "top" : "bottom";
  return `${half} of the ${match[2]}`;
}

export function formatInningWithArrow(inning: string) {
  if (inning.toLowerCase() === "final") {
    return "Final";
  }

  const match = inning.match(/^(Top|Bottom)\s+(\d+(?:st|nd|rd|th))$/i);

  if (!match) {
    return inning;
  }

  const arrow = match[1].toLowerCase() === "top" ? "↑" : "↓";
  return `${arrow} ${match[2]}`;
}

export function isGameFinal(state: LiveGameState | null | undefined) {
  if (!state) {
    return false;
  }

  return isFinalStatus(state.status, state.abstractStatus) || state.inning.toLowerCase() === "final";
}

export function isGameLive(state: LiveGameState | null | undefined) {
  if (!state) {
    return false;
  }

  if (isGameFinal(state)) {
    return false;
  }

  const status = state.status.toLowerCase();
  if (status.includes("postponed") || status.includes("cancelled") || status.includes("suspended")) {
    return false;
  }

  if (isLiveStatus(state.status, state.abstractStatus)) {
    return true;
  }

  const inning = state.inning.toLowerCase();
  return inning !== "pregame" && !inning.includes("warmup") && !inning.includes("delayed start");
}

/** True when a board game's first pitch was long enough ago that "starts at 6:15" is nonsense. */
export function gameStartIsStale(startsAt: string, nowMs = Date.now()) {
  const start = new Date(startsAt).getTime();
  if (!Number.isFinite(start)) {
    return false;
  }
  // Regulation games rarely finish under ~2h; 3h covers rain delays without marking pregame as final.
  return nowMs - start >= 3 * 60 * 60 * 1000;
}

function chicagoDateIso(value = new Date()) {
  // en-CA yields YYYY-MM-DD
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Chicago",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).format(value);
}

function boardSlateDates(board: GamePrediction[]) {
  const dates = new Set<string>();
  for (const game of board) {
    const fromId = game.id.match(/(\d{4}-\d{2}-\d{2})/)?.[1];
    const fromStarts = game.startsAt
      ? new Intl.DateTimeFormat("en-CA", {
          timeZone: "America/Chicago",
          year: "numeric",
          month: "2-digit",
          day: "2-digit"
        }).format(new Date(game.startsAt))
      : null;
    if (fromId) dates.add(fromId);
    if (fromStarts) dates.add(fromStarts);
  }
  // Always include Chicago "today" so late boards still resolve.
  dates.add(chicagoDateIso());
  return [...dates];
}

function stateFromScheduleGame(game: GamePrediction, row: ScheduleGame): LiveGameState {
  const detailed = row.status?.detailedState ?? "Scheduled";
  const abstract = row.status?.abstractGameState;
  const coded = row.status?.codedGameState;
  const linescore = row.linescore;
  const awayRuns = linescore?.teams?.away?.runs ?? row.teams?.away?.score ?? 0;
  const homeRuns = linescore?.teams?.home?.runs ?? row.teams?.home?.score ?? 0;

  return {
    status: detailed,
    abstractStatus: abstract,
    inning: formatInningFromParts(detailed, abstract, coded, linescore),
    away: {
      teamId: game.awayTeam,
      runs: awayRuns,
      hits: linescore?.teams?.away?.hits ?? 0,
      errors: linescore?.teams?.away?.errors ?? 0
    },
    home: {
      teamId: game.homeTeam,
      runs: homeRuns,
      hits: linescore?.teams?.home?.hits ?? 0,
      errors: linescore?.teams?.home?.errors ?? 0
    },
    probablePitchers: {
      away: row.probablePitchers?.away?.fullName,
      home: row.probablePitchers?.home?.fullName
    },
    recentPlays: []
  };
}

async function fetchScheduleStatesByPk(dates: string[]) {
  const byPk = new Map<string, ScheduleGame>();

  await Promise.all(
    dates.map(async (day) => {
      try {
        const url =
          `https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=${day}` +
          `&hydrate=linescore,probablePitcher`;
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) {
          return;
        }
        const payload = (await response.json()) as ScheduleResponse;
        for (const dateRow of payload.dates ?? []) {
          for (const game of dateRow.games ?? []) {
            if (game.gamePk != null) {
              byPk.set(String(game.gamePk), game);
            }
          }
        }
      } catch {
        // Fall through to per-game live feed.
      }
    })
  );

  return byPk;
}

/**
 * Board-wide live/final states. Prefer one MLB schedule call (reliable for finals)
 * over N live-feed requests that often time out on serverless and leave cards stuck
 * on "starts at 6:15".
 */
export async function loadLiveGameStatesForBoard(board: GamePrediction[]) {
  const scheduleByPk = await fetchScheduleStatesByPk(boardSlateDates(board));
  const entries = await Promise.all(
    board.map(async (game) => {
      const pk = getGamePk(game);
      const scheduled = pk ? scheduleByPk.get(pk) : undefined;
      if (scheduled) {
        return [game.id, stateFromScheduleGame(game, scheduled)] as const;
      }
      // Fallback for missing schedule rows (rare).
      return [game.id, await loadLiveGameState(game)] as const;
    })
  );

  return new Map(entries);
}

export async function loadLiveGameState(game?: GamePrediction): Promise<LiveGameState | null> {
  const gamePk = game ? getGamePk(game) : null;

  if (!game || !gamePk) {
    return null;
  }

  try {
    // Never cache mid-game feeds — stale ISR was leaving buttons stuck in old innings.
    const response = await fetch(`https://statsapi.mlb.com/api/v1.1/game/${gamePk}/feed/live`, {
      cache: "no-store"
    });

    if (!response.ok) {
      return null;
    }

    const feed = (await response.json()) as LiveFeedResponse;
    const linescore = feed.liveData?.linescore;
    const plays = feed.liveData?.plays?.allPlays ?? [];
    const status = feed.gameData?.status;

    return {
      status: status?.detailedState ?? "Game status unavailable",
      abstractStatus: status?.abstractGameState,
      inning: formatInning(feed),
      away: {
        teamId: game.awayTeam,
        runs: linescore?.teams?.away?.runs ?? 0,
        hits: linescore?.teams?.away?.hits ?? 0,
        errors: linescore?.teams?.away?.errors ?? 0
      },
      home: {
        teamId: game.homeTeam,
        runs: linescore?.teams?.home?.runs ?? 0,
        hits: linescore?.teams?.home?.hits ?? 0,
        errors: linescore?.teams?.home?.errors ?? 0
      },
      probablePitchers: {
        away: feed.gameData?.probablePitchers?.away?.fullName,
        home: feed.gameData?.probablePitchers?.home?.fullName
      },
      recentPlays: plays
        .slice(-6)
        .reverse()
        .flatMap((play) => {
          const description = play.result?.description;
          if (!description) {
            return [];
          }

          const half = play.about?.halfInning;
          const inning = play.about?.inning;
          const prefix = half && inning ? `${half} ${inning}: ` : "";
          return `${prefix}${description}`;
        })
    };
  } catch {
    return null;
  }
}
