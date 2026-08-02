import Link from "next/link";
import { GameCard } from "@/components/GameCard";
import { loadPredictionBoard, loadPredictionBoardMetadata } from "@/lib/model-output";
import { formatStandingRecord, loadLiveStandings } from "@/lib/standings";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const board = await loadPredictionBoard();
  const boardMeta = await loadPredictionBoardMetadata();
  const standings = await loadLiveStandings();
  const recordsByTeamId = Object.fromEntries(
    standings.map((standing) => [standing.teamId, formatStandingRecord(standing)])
  );

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Daily MLB model</p>
        <h1>Today&apos;s MLB predictions.</h1>
        <p className="lead">
          Calibrated win probabilities with betting labels: High/Elite = bet, Medium = lean,
          Low = pass. Trained through {boardMeta.trained_through ?? "pending"} · {board.length}{" "}
          games.
        </p>
        <div className="hero-actions">
          <Link href="/props" className="button">
            Props card
          </Link>
          <Link href="/best-bets" className="button ghost">
            Moneyline ticket
          </Link>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Full slate</p>
            <h2>Today&apos;s Board</h2>
          </div>
          <span>{board.length} games</span>
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
