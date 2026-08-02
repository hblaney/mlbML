import { resolveBuffstreamsForGame } from "@/lib/buffstreams";
import { getTeam, normalizeTeamId } from "@/lib/data";
import { loadPredictionBoard } from "@/lib/model-output";
import { getMatchupWatchStream } from "@/lib/watch-streams";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const gameId = new URL(request.url).searchParams.get("gameId");
  const focusTeamId = new URL(request.url).searchParams.get("teamId");

  if (!gameId) {
    return Response.json({ error: "gameId is required" }, { status: 400 });
  }

  const board = await loadPredictionBoard();
  const game = board.find((item) => item.id === gameId);

  if (!game) {
    return Response.json({ error: "Game not found on today's board" }, { status: 404 });
  }

  const awayTeamId = normalizeTeamId(game.awayTeam);
  const homeTeamId = normalizeTeamId(game.homeTeam);
  const teamId = normalizeTeamId(focusTeamId ?? homeTeamId);

  const buffstreams = await resolveBuffstreamsForGame({
    ...game,
    awayTeam: awayTeamId,
    homeTeam: homeTeamId
  });

  const stream = getMatchupWatchStream({
    focusTeamId: teamId,
    awayTeamId,
    homeTeamId,
    buffstreams
  });

  if (!stream) {
    return Response.json({ error: "No stream configured for this matchup" }, { status: 404 });
  }

  const away = getTeam(awayTeamId);
  const home = getTeam(homeTeamId);

  return Response.json({
    gameId,
    title: `${away.abbreviation} @ ${home.abbreviation}`,
    teamId,
    ...stream
  });
}
