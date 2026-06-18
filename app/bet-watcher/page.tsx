import { BetWatcherClient } from "@/app/bet-watcher/BetWatcherClient";
import { getBestDailyTicket } from "@/lib/data";
import { BetLeg } from "@/lib/bet-watcher";
import { loadLiveBankroll, loadPredictionBoard } from "@/lib/model-output";

export const dynamic = "force-dynamic";

function legFromTicketBet(bet: {
  game: { id: string };
  team: { id: string };
  odds: number;
}): BetLeg {
  return {
    id: `today-${bet.game.id}-${bet.team.id}`,
    gameId: bet.game.id,
    kind: "moneyline",
    teamId: bet.team.id,
    odds: bet.odds
  };
}

function legsFromTicket(ticket: ReturnType<typeof getBestDailyTicket>): BetLeg[] {
  if (!ticket) {
    return [];
  }

  if (ticket.kind === "single") {
    return [legFromTicketBet(ticket.bet)];
  }

  return ticket.parlay.legs.map((bet) => legFromTicketBet(bet));
}

export default async function BetWatcherPage() {
  const [board, liveBankroll] = await Promise.all([loadPredictionBoard(), loadLiveBankroll()]);
  const bestTicket = getBestDailyTicket(board);
  const todayLegs = legsFromTicket(bestTicket);
  const proveOutStake = liveBankroll?.prove_out?.flat_stake_usd ?? 5;
  const todaySnapshot = liveBankroll?.today_ticket;
  const ticketAmericanOdds =
    todaySnapshot?.odds ??
    (bestTicket?.kind === "parlay"
      ? bestTicket.parlay.americanOdds
      : bestTicket?.kind === "single"
        ? bestTicket.bet.odds
        : null);

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Multi-game command center</p>
        <h1>Bet Watcher</h1>
        <p className="lead">
          Build any same-day ticket — singles, parlays, or custom overs — then watch every game at once and
          track whether your bet is still alive.
        </p>
      </section>

      <BetWatcherClient
        board={board}
        todayTicket={{
          legs: todayLegs,
          stake: todaySnapshot?.stake_amount ?? proveOutStake,
          americanOdds: ticketAmericanOdds,
          label: todaySnapshot?.label ?? "Today's card"
        }}
      />
    </main>
  );
}
