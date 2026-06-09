import Link from "next/link";
import { GameCard } from "@/components/GameCard";
import { accuracySnapshots, getBestBets } from "@/lib/data";
import { loadPredictionBoard } from "@/lib/model-output";
import { formatPercent } from "@/lib/odds";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const board = await loadPredictionBoard();
  const bestBets = getBestBets(board);
  const weekly = accuracySnapshots.find((item) => item.range === "Last 7 Days");

  return (
    <main className="shell">
      <section className="hero">
        <div>
          <p className="eyebrow">Daily MLB model</p>
          <h1>Predictions without the sportsbook noise.</h1>
          <p className="lead">
            MLB Edge turns team form, starters, bullpen load, market prices, and model history into daily game
            projections, best bets, stats, and stream-ready watch pages.
          </p>
          <div className="links">
            <Link className="button" href="/best-bets">View best bets</Link>
            <Link href="/accuracy">Model accuracy</Link>
          </div>
        </div>

        <aside className="panel strong">
          <p className="muted">Model health</p>
          <div className="metric">{weekly ? formatPercent(weekly.accuracy) : "Pending"}</div>
          <p className="muted">Last 7 days · public record</p>
          <div className="grid two">
            <div>
              <p className="muted">Positive EV plays</p>
              <strong>{bestBets.length}</strong>
            </div>
            <div>
              <p className="muted">Model version</p>
              <strong>{board[0]?.modelVersion}</strong>
            </div>
          </div>
        </aside>
      </section>

      <section className="stack">
        <div className="matchup">
          <h2>Today&apos;s Board</h2>
          <span className="muted">{board.length} games loaded</span>
        </div>
        {board.length > 0 ? (
          <div className="grid">
            {board.map((game) => (
              <GameCard game={game} key={game.id} />
            ))}
          </div>
        ) : (
          <section className="panel">
            <p>Today&apos;s board could not be generated yet.</p>
            <p className="muted">
              Refresh in a moment. If it still fails, the MLB API or local Python environment is unavailable.
            </p>
          </section>
        )}
      </section>
    </main>
  );
}
