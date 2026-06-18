import { resolveBuffstreamsForGame } from "@/lib/buffstreams";
import { getTeam } from "@/lib/data";
import { loadPredictionBoard } from "@/lib/model-output";
import { getTeamWatchStream } from "@/lib/watch-streams";

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

  const buffstreams = await resolveBuffstreamsForGame(game);
  const teamId = focusTeamId ?? game.homeTeam;
  const opponentId = teamId === game.homeTeam ? game.awayTeam : game.homeTeam;
  const stream = getTeamWatchStream(teamId, opponentId, buffstreams);

  if (!stream) {
    return Response.json({ error: "No stream configured for this matchup" }, { status: 404 });
  }

  const away = getTeam(game.awayTeam);
  const home = getTeam(game.homeTeam);

  return Response.json({
    gameId,
    title: `${away.abbreviation} @ ${home.abbreviation}`,
    teamId,
    ...stream
  });
}
