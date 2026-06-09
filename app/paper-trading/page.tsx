import { PaperTradingClient } from "@/app/paper-trading/PaperTradingClient";
import { loadPredictionBoard } from "@/lib/model-output";

export const dynamic = "force-dynamic";

export default async function PaperTradingPage() {
  const board = await loadPredictionBoard();

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Paper trading</p>
        <h1>Bet with fake money before risking real money.</h1>
        <p className="lead">
          Track a practice bankroll, place paper bets from the current MLB board, and grade your own tickets as games finish.
        </p>
      </section>
      <PaperTradingClient board={board} />
    </main>
  );
}
