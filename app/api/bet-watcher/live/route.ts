import { loadLiveGameState } from "@/lib/live-game";
import { loadPredictionBoard } from "@/lib/model-output";

export const dynamic = "force-dynamic";

type LiveRequestBody = {
  gameIds?: string[];
};

export async function POST(request: Request) {
  let body: LiveRequestBody;

  try {
    body = (await request.json()) as LiveRequestBody;
  } catch {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const gameIds = body.gameIds?.filter(Boolean) ?? [];
  if (gameIds.length === 0) {
    return Response.json({ games: {} });
  }

  const board = await loadPredictionBoard();
  const boardById = new Map(board.map((game) => [game.id, game]));
  const uniqueIds = [...new Set(gameIds)];

  const entries = await Promise.all(
    uniqueIds.map(async (gameId) => {
      const game = boardById.get(gameId);
      if (!game) {
        return [gameId, null] as const;
      }

      return [gameId, await loadLiveGameState(game)] as const;
    })
  );

  return Response.json({
    games: Object.fromEntries(entries),
    refreshedAt: new Date().toISOString()
  });
}
