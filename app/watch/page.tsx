import { WatchHub } from "@/components/WatchHub";
import { toWatchBoardGames } from "@/lib/watch-board-game";
import { loadLiveGameStatesForBoard } from "@/lib/live-game";
import { loadPredictionBoard } from "@/lib/model-output";
import { getWatchTeams } from "@/lib/team-media";
import { buildWatchTeamStatuses } from "@/lib/watch-team-status";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function WatchPage() {
  const watchTeams = getWatchTeams();
  const board = await loadPredictionBoard();
  const liveByGameId = await loadLiveGameStatesForBoard(board);
  const teams = buildWatchTeamStatuses(watchTeams, board, liveByGameId);
  const games = toWatchBoardGames(board);

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Team streams</p>
        <h1>Watch</h1>
        <div className="hero-actions">
          <a className="button" href="#multi-view">
            Multi-view
          </a>
        </div>
      </section>

      <WatchHub games={games} teams={teams} />
    </main>
  );
}
