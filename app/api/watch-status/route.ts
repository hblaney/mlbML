import { loadLiveGameStatesForBoard } from "@/lib/live-game";
import { loadPredictionBoard } from "@/lib/model-output";
import { getWatchTeams } from "@/lib/team-media";
import { buildWatchTeamStatuses } from "@/lib/watch-team-status";

export const dynamic = "force-dynamic";
export const revalidate = 0;

/** Fresh status lines for the /watch team grid (polled by the client). */
export async function GET() {
  const watchTeams = getWatchTeams();
  const board = await loadPredictionBoard();
  const liveByGameId = await loadLiveGameStatesForBoard(board);
  const teams = buildWatchTeamStatuses(watchTeams, board, liveByGameId);

  return Response.json(
    {
      generatedAt: new Date().toISOString(),
      teams: teams.map((team) => ({
        id: team.id,
        statusLine: team.statusLine ?? null
      }))
    },
    {
      headers: {
        "Cache-Control": "no-store, max-age=0"
      }
    }
  );
}
