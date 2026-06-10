import { WatchTeamsGrid } from "@/components/WatchTeamsGrid";
import { loadLiveGameStatesForBoard } from "@/lib/live-game";
import { loadPredictionBoard } from "@/lib/model-output";
import { getWatchTeams } from "@/lib/team-media";
import { buildWatchTeamStatuses } from "@/lib/watch-team-status";

export const dynamic = "force-dynamic";

export default async function WatchPage() {
  const watchTeams = getWatchTeams();
  const board = await loadPredictionBoard();
  const liveByGameId = await loadLiveGameStatesForBoard(board);
  const teams = buildWatchTeamStatuses(watchTeams, board, liveByGameId);

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Team streams</p>
        <h1>Watch</h1>
        <p className="lead">Pick a team to open its stream page. Favorite teams appear first when you are logged in.</p>
      </section>

      <WatchTeamsGrid teams={teams} />
    </main>
  );
}
