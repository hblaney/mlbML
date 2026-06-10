import { GamePrediction, getTeam } from "./data";
import { formatInningWithArrow, isGameFinal, isGameLive, LiveGameState } from "./live-game";
import { formatCentralGameSchedule } from "./time";

export type WatchTeamCard = {
  id: string;
  name: string;
  abbreviation: string;
  primary: string;
  logoUrl: string | null;
  statusLine?: string | null;
};

type WatchTeamBase = Omit<WatchTeamCard, "statusLine">;

function getOpponentAbbrev(game: GamePrediction, teamId: string) {
  const opponentId = game.homeTeam === teamId ? game.awayTeam : game.homeTeam;
  return getTeam(opponentId).abbreviation;
}

function pickTeamGame(
  teamId: string,
  board: GamePrediction[],
  liveByGameId: Map<string, LiveGameState | null>
) {
  const teamGames = board.filter((game) => game.awayTeam === teamId || game.homeTeam === teamId);

  if (teamGames.length === 0) {
    return null;
  }

  const liveGame = teamGames.find((game) => isGameLive(liveByGameId.get(game.id)));
  if (liveGame) {
    return liveGame;
  }

  const upcomingGames = teamGames
    .filter((game) => !isGameFinal(liveByGameId.get(game.id)))
    .sort((left, right) => new Date(left.startsAt).getTime() - new Date(right.startsAt).getTime());

  return upcomingGames[0] ?? teamGames[0];
}

function formatLiveStatusLine(game: GamePrediction, liveGame: LiveGameState) {
  const away = getTeam(game.awayTeam);
  const home = getTeam(game.homeTeam);
  const awayRuns = liveGame.away?.runs ?? 0;
  const homeRuns = liveGame.home?.runs ?? 0;
  const inning = formatInningWithArrow(liveGame.inning);

  return `${inning} · ${away.abbreviation} ${awayRuns}-${homeRuns} ${home.abbreviation}`;
}

function formatScheduledStatusLine(game: GamePrediction, teamId: string) {
  return formatCentralGameSchedule(game.startsAt, getOpponentAbbrev(game, teamId));
}

export function formatWatchGameStatusLine(
  game: GamePrediction,
  liveGame: LiveGameState | null | undefined,
  teamId: string
) {
  if (liveGame && isGameLive(liveGame)) {
    return formatLiveStatusLine(game, liveGame);
  }

  return formatScheduledStatusLine(game, teamId);
}

export function buildWatchTeamStatuses(
  teams: WatchTeamBase[],
  board: GamePrediction[],
  liveByGameId: Map<string, LiveGameState | null>
): WatchTeamCard[] {
  return teams.map((team) => {
    const game = pickTeamGame(team.id, board, liveByGameId);

    if (!game) {
      return { ...team, statusLine: null };
    }

    const liveGame = liveByGameId.get(game.id);

    if (liveGame && isGameLive(liveGame)) {
      return {
        ...team,
        statusLine: formatLiveStatusLine(game, liveGame)
      };
    }

    return {
      ...team,
      statusLine: formatScheduledStatusLine(game, team.id)
    };
  });
}
