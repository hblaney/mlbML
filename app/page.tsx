import Link from "next/link";
import { GameCard } from "@/components/GameCard";
import { getBestBets } from "@/lib/data";
import { loadModelHealthSummary, loadPredictionBoard, loadPredictionBoardMetadata } from "@/lib/model-output";
import { formatPercent } from "@/lib/odds";
import { formatStandingRecord, loadLiveStandings } from "@/lib/standings";
import { formatCentralDate } from "@/lib/time";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const board = await loadPredictionBoard();
  const boardMeta = await loadPredictionBoardMetadata();
  const standings = await loadLiveStandings();
  const recordsByTeamId = Object.fromEntries(
    standings.map((standing) => [standing.teamId, formatStandingRecord(standing)])
  );
  const bestBets = getBestBets(board);
  const health = await loadModelHealthSummary();
  const weeklyAccuracy = health?.last7Days.accuracy ?? null;

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Daily MLB model</p>
        <h1>Today&apos;s MLB board, priced against the market.</h1>
        <p className="lead">
          Probabilities, real odds, live records, and model edges in one clean slate.
        </p>
        <div className="hero-actions">
          <Link href="/best-bets" className="button">
            View best bets
          </Link>
          <Link href="/history" className="button ghost">
            Model accuracy
          </Link>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Live Card</p>
            <h2>{formatCentralDate()}</h2>
          </div>
          <span>
            Trained through {boardMeta.trained_through ?? "pending"} · auto-retrains daily
          </span>
        </div>
        <div className="grid">
          <article>
            <p className="muted">Model health</p>
            <div className="metric">{weeklyAccuracy !== null ? formatPercent(weeklyAccuracy) : "Pending"}</div>
            <p className="muted">Last 7 days{health?.last7Days.games ? ` · ${health.last7Days.record}` : ""}</p>
          </article>
          <article>
            <p className="muted">EV plays</p>
            <div className="metric">{bestBets.length}</div>
          </article>
          <article>
            <p className="muted">Games</p>
            <div className="metric">{board.length}</div>
          </article>
          <article>
            <p className="muted">Accuracy</p>
            <div className="metric">{weeklyAccuracy !== null ? formatPercent(weeklyAccuracy) : "Pending"}</div>
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Full slate</p>
            <h2>Today&apos;s Board</h2>
          </div>
          <span>{board.length} games loaded</span>
        </div>
        {board.length > 0 ? (
          <div className="grid two">
            {board.map((game) => (
              <GameCard key={game.id} game={game} recordsByTeamId={recordsByTeamId} />
            ))}
          </div>
        ) : (
          <p className="muted">
            Today&apos;s board could not be generated yet. Refresh in a moment. If it still fails, the daily
            automation job or MLB API may be unavailable.
          </p>
        )}
      </section>
    </main>
  );
}
