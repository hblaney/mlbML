import Link from "next/link";
import {
  getBestDailyTicket,
  getRatchetStakePct,
  getSortedPredictions,
  getTeam,
  LIVE_BETTING_STRATEGY,
  OPTIMIZED_STAKE_BY_LEG_COUNT
} from "@/lib/data";
import { loadLiveBankroll, loadBettingPlan, loadPredictionBoard } from "@/lib/model-output";
import { formatOdds, formatPercent } from "@/lib/odds";
import { formatStandingRecord, loadLiveStandings } from "@/lib/standings";
import { formatCentralGameTime } from "@/lib/time";

export const dynamic = "force-dynamic";

export default async function BestBetsPage() {
  const board = await loadPredictionBoard();
  const standings = await loadLiveStandings();
  const standingsByTeamId = new Map(standings.map((standing) => [standing.teamId, standing]));
  const [bettingPlan, liveBankroll] = await Promise.all([loadBettingPlan(), loadLiveBankroll()]);

  const ticket = getBestDailyTicket(board);
  const highPicks = getSortedPredictions(board).filter(
    (game) => game.confidence === "High" || game.confidence === "Elite"
  );

  const bankroll = liveBankroll?.wallet_balance ?? liveBankroll?.balance ?? 10;
  const stakePct =
    bettingPlan?.ratchet_tiers != null
      ? getRatchetStakePct(bankroll, 1, bettingPlan.ratchet_tiers)
      : (bettingPlan?.stake_by_leg_count?.["1"] ?? OPTIMIZED_STAKE_BY_LEG_COUNT[1]);
  const stakeUsd = bankroll * stakePct;

  const formatBankroll = (value: number) =>
    value >= 100
      ? `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
      : `$${value.toFixed(2)}`;

  const recordFor = (teamId: string) => formatStandingRecord(standingsByTeamId.get(teamId));

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Moneyline</p>
        <h1>Today&apos;s bet</h1>
        <p className="lead">
          One High-confidence single when the gates clear — otherwise skip. Wallet{" "}
          <strong>{formatBankroll(bankroll)}</strong>
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

      {ticket?.kind === "single" ? (
        <section className="panel strong">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Bet this</p>
              <h2>
                {ticket.bet.team.abbreviation} moneyline
              </h2>
            </div>
            <span className="positive">{ticket.bet.game.confidence}</span>
          </div>
          <div className="grid two">
            <article>
              <p className="muted">Matchup</p>
              <strong>{ticket.bet.matchup}</strong>
              <p>
                <Link className="team-stream-link" href={`/watch/${ticket.bet.team.id}`}>
                  {ticket.bet.team.name}
                </Link>{" "}
                ({recordFor(ticket.bet.team.id)}) vs{" "}
                <Link className="team-stream-link" href={`/watch/${ticket.bet.opponent.id}`}>
                  {ticket.bet.opponent.name}
                </Link>{" "}
                ({recordFor(ticket.bet.opponent.id)})
              </p>
              <p className="muted">{formatCentralGameTime(ticket.bet.game.startsAt)}</p>
            </article>
            <article>
              <p className="muted">Line</p>
              <div className="metric">{formatOdds(ticket.bet.odds)}</div>
              <p className="muted">
                Model {formatPercent(ticket.bet.modelProbability)} · Edge{" "}
                <span className={ticket.bet.edge > 0 ? "positive" : "warning"}>
                  {formatPercent(ticket.bet.edge)}
                </span>
              </p>
              <p className="muted">
                Suggested stake <strong>{formatBankroll(stakeUsd)}</strong> (
                {formatPercent(stakePct)} of wallet)
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
            Nothing cleared the High lane (p ≥ 55%, form, ERA edge, price edge, market agree, +EV). Sitting
            out is the play.
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
                  const odds = pickIsHome ? game.homeMoneyline : game.awayMoneyline;
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
                      <td>{odds != null ? formatOdds(odds) : "—"}</td>
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

      {liveBankroll?.tickets && liveBankroll.tickets.length > 0 ? (
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
                  .slice(0, 5)
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
