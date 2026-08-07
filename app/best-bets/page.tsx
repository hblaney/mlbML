import Link from "next/link";
import {
  getBestDailyTicket,
  getRatchetStakePct,
  getSortedPredictions,
  getTeam,
  LIVE_BETTING_STRATEGY,
  OPTIMIZED_STAKE_BY_LEG_COUNT,
  type BestBet,
  type DailyTicket
} from "@/lib/data";
import { loadLiveBankroll, loadBettingPlan, loadPredictionBoard, loadRecentLockedTicketDays } from "@/lib/model-output";
import { formatOdds, formatPercent } from "@/lib/odds";
import { formatStandingRecord, loadLiveStandings } from "@/lib/standings";
import { formatCentralGameTime } from "@/lib/time";

export const dynamic = "force-dynamic";

function ticketLegs(ticket: DailyTicket): BestBet[] {
  if (ticket.kind === "single") return [ticket.bet];
  if (ticket.kind === "multi_single") return ticket.bets;
  return ticket.parlay.legs;
}

function ticketTitle(ticket: DailyTicket): string {
  const legs = ticketLegs(ticket);
  if (legs.length === 1) return `${legs[0].team.abbreviation} moneyline`;
  return `${legs.map((leg) => `${leg.team.abbreviation} ML`).join(" + ")}`;
}

function ticketOdds(ticket: DailyTicket): number | null {
  if (ticket.kind === "single") return ticket.bet.odds;
  if (ticket.kind === "parlay") return ticket.parlay.americanOdds;
  return null;
}

function ticketModelProb(ticket: DailyTicket): number | null {
  if (ticket.kind === "single") return ticket.bet.modelProbability;
  if (ticket.kind === "parlay") return ticket.parlay.probability;
  return null;
}

export default async function BestBetsPage() {
  const board = await loadPredictionBoard();
  const standings = await loadLiveStandings();
  const standingsByTeamId = new Map(standings.map((standing) => [standing.teamId, standing]));
  const [bettingPlan, liveBankroll, recentDays] = await Promise.all([
    loadBettingPlan(),
    loadLiveBankroll(),
    loadRecentLockedTicketDays(14)
  ]);

  const ticket = getBestDailyTicket(board);
  const highPicks = getSortedPredictions(board).filter(
    (game) => game.confidence === "High" || game.confidence === "Elite"
  );

  const bankroll = liveBankroll?.wallet_balance ?? liveBankroll?.balance ?? 10;
  const legCount = ticket ? ticketLegs(ticket).length : 1;
  const stakePct =
    bettingPlan?.ratchet_tiers != null
      ? getRatchetStakePct(bankroll, legCount, bettingPlan.ratchet_tiers)
      : (bettingPlan?.stake_by_leg_count?.[String(legCount)] ??
        OPTIMIZED_STAKE_BY_LEG_COUNT[legCount] ??
        OPTIMIZED_STAKE_BY_LEG_COUNT[1]);
  const stakeUsd = bankroll * stakePct;

  const formatBankroll = (value: number) =>
    value >= 100
      ? `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
      : `$${value.toFixed(2)}`;

  const recordFor = (teamId: string) => formatStandingRecord(standingsByTeamId.get(teamId));
  const odds = ticket ? ticketOdds(ticket) : null;
  const modelProb = ticket ? ticketModelProb(ticket) : null;

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Moneyline</p>
        <h1>Today&apos;s bet</h1>
        <p className="lead">
          Prefer a <strong>2-leg High stack</strong> when two clear; otherwise one High single; else
          skip. Wallet <strong>{formatBankroll(bankroll)}</strong>
          {liveBankroll && liveBankroll.record !== "0-0" ? (
            <>
              {" "}
              · <strong>{liveBankroll.record}</strong>
              {liveBankroll.hit_rate != null ? ` (${formatPercent(liveBankroll.hit_rate)})` : ""}
            </>
          ) : null}
          . <Link href="/accuracy">Accuracy →</Link>
        </p>
      </section>

      {ticket ? (
        <section className="panel strong">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Bet this</p>
              <h2>{ticketTitle(ticket)}</h2>
            </div>
            <span className="positive">
              {ticket.kind === "parlay" ? "2-leg" : "Single"} · High
            </span>
          </div>

          <div className="stack" style={{ gap: 14, marginBottom: 16 }}>
            {ticketLegs(ticket).map((bet) => (
              <article key={`${bet.game.id}-${bet.team.id}`}>
                <p className="muted">
                  {bet.team.abbreviation} ML · {formatOdds(bet.odds)} ·{" "}
                  {formatCentralGameTime(bet.game.startsAt)}
                </p>
                <strong>{bet.matchup}</strong>
                <p>
                  <Link className="team-stream-link" href={`/watch/${bet.team.id}`}>
                    {bet.team.name}
                  </Link>{" "}
                  ({recordFor(bet.team.id)}) vs{" "}
                  <Link className="team-stream-link" href={`/watch/${bet.opponent.id}`}>
                    {bet.opponent.name}
                  </Link>{" "}
                  ({recordFor(bet.opponent.id)})
                </p>
                <p className="muted">
                  Model {formatPercent(bet.modelProbability)} · Edge{" "}
                  <span className={bet.edge > 0 ? "positive" : "warning"}>
                    {formatPercent(bet.edge)}
                  </span>{" "}
                  · {bet.game.confidence}
                </p>
              </article>
            ))}
          </div>

          <div className="grid two">
            <article>
              <p className="muted">{ticket.kind === "parlay" ? "Parlay price" : "Line"}</p>
              <div className="metric">{odds != null ? formatOdds(odds) : "—"}</div>
              <p className="muted">
                Combined model{" "}
                {modelProb != null ? formatPercent(modelProb) : "—"}
              </p>
            </article>
            <article>
              <p className="muted">Suggested stake</p>
              <div className="metric">{formatBankroll(stakeUsd)}</div>
              <p className="muted">
                {formatPercent(stakePct)} of wallet · {legCount}-leg sizing
              </p>
            </article>
          </div>
        </section>
      ) : (
        <section className="panel strong">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Today</p>
              <h2>No bet — skip</h2>
            </div>
            <span className="muted">PASS</span>
          </div>
          <p className="muted">
            Need at least one High lane clear (p ≥ 55%, form, ERA edge, price edge, market agree,
            +EV). Two Highs → 2-leg; one High → single.
          </p>
        </section>
      )}

      <section className="panel">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Board</p>
            <h2>High / Elite picks</h2>
          </div>
          <span className="muted">{highPicks.length} today</span>
        </div>
        {highPicks.length > 0 ? (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Pick</th>
                  <th>Conf</th>
                  <th>Odds</th>
                  <th className="hide-sm">Model</th>
                  <th className="hide-sm">Edge</th>
                </tr>
              </thead>
              <tbody>
                {highPicks.map((game) => {
                  const pickId = game.predictedTeam ?? game.homeTeam;
                  const pickIsHome = pickId === game.homeTeam;
                  const pickTeam = getTeam(pickId);
                  const away = getTeam(game.awayTeam);
                  const home = getTeam(game.homeTeam);
                  const line = pickIsHome ? game.homeMoneyline : game.awayMoneyline;
                  const edge = game.modelEdge ?? 0;
                  return (
                    <tr key={game.id}>
                      <td>
                        <strong>{pickTeam.abbreviation} ML</strong>
                        <p className="muted">
                          {away.abbreviation} @ {home.abbreviation} ·{" "}
                          {formatCentralGameTime(game.startsAt)}
                        </p>
                      </td>
                      <td>{game.confidence}</td>
                      <td>{line != null ? formatOdds(line) : "—"}</td>
                      <td className="hide-sm">{formatPercent(game.pickProbability ?? 0)}</td>
                      <td className={`hide-sm ${edge > 0 ? "positive" : "warning"}`}>
                        {formatPercent(edge)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">No High or Elite moneylines on today&apos;s board.</p>
        )}
        <p className="muted" style={{ marginTop: 12 }}>
          Strategy: <strong>{bettingPlan?.strategy ?? LIVE_BETTING_STRATEGY}</strong> · see the full slate on{" "}
          <Link href="/">Board</Link>.
        </p>
      </section>

      {recentDays.length > 0 ? (
        <section className="panel">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Last 14 days</p>
              <h2>Official system tickets</h2>
            </div>
            <Link className="muted" href="/accuracy">
              Accuracy →
            </Link>
          </div>
          <p className="muted" style={{ marginBottom: 12 }}>
            These are locked High/Elite moneyline tickets from the site — not your personal
            PrizePicks / Underdog slips. A morning <strong>SKIP</strong> can upgrade later the
            same day once odds/Highs clear (today&apos;s card is the live bet up top).
          </p>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Ticket</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {recentDays.map((row) => {
                  const resultClass =
                    row.status === "win"
                      ? "positive"
                      : row.status === "loss"
                        ? "warning"
                        : "muted";
                  const resultLabel =
                    row.status === "win"
                      ? "WIN"
                      : row.status === "loss"
                        ? "LOSS"
                        : row.status === "skip"
                          ? "SKIP"
                          : row.status === "pending"
                            ? "PENDING"
                            : "—";
                  return (
                    <tr key={row.date}>
                      <td>{row.date}</td>
                      <td>
                        <strong>{row.label}</strong>
                      </td>
                      <td className={resultClass}>{resultLabel}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {liveBankroll?.tickets && liveBankroll.tickets.length > 0 ? (
            <p className="muted" style={{ marginTop: 12 }}>
              Graded system record: <strong>{liveBankroll.record}</strong>
              {liveBankroll.hit_rate != null ? ` (${formatPercent(liveBankroll.hit_rate)})` : ""} ·
              last settled {liveBankroll.last_settled_date ?? "—"}.
            </p>
          ) : null}
        </section>
      ) : liveBankroll?.tickets && liveBankroll.tickets.length > 0 ? (
        <section className="panel">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Recent</p>
              <h2>Last graded tickets</h2>
            </div>
            <Link className="muted" href="/accuracy">
              Accuracy →
            </Link>
          </div>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Ticket</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {[...liveBankroll.tickets]
                  .reverse()
                  .slice(0, 14)
                  .map((row) => (
                    <tr key={row.date}>
                      <td>{row.date}</td>
                      <td>
                        <strong>{row.label}</strong>
                      </td>
                      <td className={row.won ? "positive" : "warning"}>{row.won ? "WIN" : "LOSS"}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </main>
  );
}
