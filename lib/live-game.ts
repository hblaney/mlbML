import { GamePrediction } from "./data";

export type LiveGameTeamLine = {
  teamId: string;
  runs: number;
  hits: number;
  errors: number;
};

export type LiveGameState = {
  status: string;
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
    status?: { detailedState?: string };
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

function getGamePk(game: GamePrediction) {
  const match = game.id.match(/-(\d+)$/);
  return match?.[1];
}

function formatInning(feed: LiveFeedResponse) {
  const linescore = feed.liveData?.linescore;

  if (!linescore?.currentInningOrdinal) {
    return "Pregame";
  }

  return [linescore.inningState, linescore.currentInningOrdinal].filter(Boolean).join(" ");
}

export async function loadLiveGameState(game?: GamePrediction): Promise<LiveGameState | null> {
  const gamePk = game ? getGamePk(game) : null;

  if (!game || !gamePk) {
    return null;
  }

  try {
    const response = await fetch(`https://statsapi.mlb.com/api/v1.1/game/${gamePk}/feed/live`, {
      next: { revalidate: 20 }
    });

    if (!response.ok) {
      return null;
    }

    const feed = (await response.json()) as LiveFeedResponse;
    const linescore = feed.liveData?.linescore;
    const plays = feed.liveData?.plays?.allPlays ?? [];

    return {
      status: feed.gameData?.status?.detailedState ?? "Game status unavailable",
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
