import Link from "next/link";
import { GameCard } from "@/components/GameCard";
import { accuracySnapshots, getBestBets } from "@/lib/data";
import { loadPredictionBoard } from "@/lib/model-output";
import { formatPercent } from "@/lib/odds";
import { formatStandingRecord, loadLiveStandings } from "@/lib/standings";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const board = await loadPredictionBoard();
  const standings = await loadLiveStandings();
  const recordsByTeamId = Object.fromEntries(
    standings.map((standing) => [standing.teamId, formatStandingRecord(standing)])
  );
  const bestBets = getBestBets(board);
  const weekly = accuracySnapshots.find((item) => item.range === "Last 7 Days");

  return (
    <main className="shell">
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Daily MLB model</p>
          <h1>Today&apos;s MLB board, priced against the market.</h1>
          <p className="lead">
            Probabilities, real odds, live records, and model edges in one clean slate.
          </p>
          <div className="links">
            <Link className="button" href="/best-bets">View best bets</Link>
            <Link href="/accuracy">Model accuracy</Link>
          </div>
        </div>

        <aside className="panel strong hero-ticket">
          <div className="ticket-top">
            <span>Live Card</span>
            <span>{new Date().toLocaleDateString()}</span>
          </div>
          <div className="ticket-main">
            <p className="muted">Model health</p>
            <div className="metric">{weekly ? formatPercent(weekly.accuracy) : "Pending"}</div>
            <p className="muted">Last 7 days</p>
          </div>
          <div className="ticket-grid">
            <div>
              <span>EV plays</span>
              <strong>{bestBets.length}</strong>
            </div>
            <div>
              <span>Games</span>
              <strong>{board.length}</strong>
            </div>
            <div>
              <span>Accuracy</span>
              <strong>{weekly ? formatPercent(weekly.accuracy) : "Pending"}</strong>
            </div>
          </div>
        </aside>
      </section>

      <section className="stack">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Full slate</p>
            <h2>Today&apos;s Board</h2>
          </div>
          <span>{board.length} games loaded</span>
        </div>
        {board.length > 0 ? (
          <div className="grid">
            {board.map((game) => (
              <GameCard game={game} key={game.id} recordsByTeamId={recordsByTeamId} />
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
