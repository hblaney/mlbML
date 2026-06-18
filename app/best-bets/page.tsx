import Link from "next/link";
import {
  getAdvancedBets,
  getBestBets,
  getBestDailyTicket,
  getOptimizedStakePctForTicket,
  OPTIMIZED_STAKE_BY_LEG_COUNT,
  LIVE_BETTING_STRATEGY
} from "@/lib/data";
import { loadPredictionBoard, loadBettingPlan, loadLiveBankroll, loadStrategyGuard, loadBestTicketWalkforward, loadPredictionBoardMetadata } from "@/lib/model-output";
import { formatOdds, formatPercent } from "@/lib/odds";
import { formatStandingRecord, loadLiveStandings } from "@/lib/standings";
import { formatCentralGameTime } from "@/lib/time";

export const dynamic = "force-dynamic";

const STRATEGY_LABELS: Record<string, string> = {
  corr_nl_reject_both: "corr_nl_reject_both (live)",
  no_low_parlay_223s: "no_low_parlay_223s",
  best_ticket: "best_ticket (selective)",
  no_low_skip_forced: "no_low_skip_forced"
};

export default async function BestBetsPage() {
  const board = await loadPredictionBoard();
  const boardMeta = await loadPredictionBoardMetadata();
  const standings = await loadLiveStandings();
  const standingsByTeamId = new Map(standings.map((standing) => [standing.teamId, standing]));
  const [bettingPlan, strategyGuard, liveBankroll, ticketWalkforward] = await Promise.all([
    loadBettingPlan(),
    loadStrategyGuard(),
    loadLiveBankroll(),
    loadBestTicketWalkforward()
  ]);
  const bets = getBestBets(board);
  const advancedBets = getAdvancedBets(board);
  const usingModelOnlyPicks = bets.some((bet) => bet.modelOnly) || advancedBets.some((bet) => bet.modelOnly);
  const bestTicket = getBestDailyTicket(board);
  const stakeByLeg = bettingPlan?.stake_by_leg_count;
  const ticketStakePct = getOptimizedStakePctForTicket(bestTicket, stakeByLeg);
  const activeStrategy = bettingPlan?.strategy ?? LIVE_BETTING_STRATEGY;
  const liveStats = strategyGuard?.comparisons[activeStrategy]?.season_to_date;
  const bankroll = liveBankroll?.wallet_balance ?? liveBankroll?.balance ?? 23.28;
  const startedAt = liveBankroll?.started_at;
  const boardGeneratedAt = boardMeta.board_generated_at;
  const boardAgeMinutes = boardGeneratedAt
    ? Math.max(0, Math.round((Date.now() - new Date(boardGeneratedAt).getTime()) / 60_000))
    : null;
  const unstableStarterGames = board.filter((game) => game.pitcherChanged || game.starterCertain === false).length;

  const formatBankroll = (value: number) =>
    value >= 100
      ? `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
      : `$${value.toFixed(2)}`;

  const comparisonRows = strategyGuard
    ? Object.entries(strategyGuard.comparisons)
        .map(([id, row]) => ({
          id,
          label: STRATEGY_LABELS[id] ?? id,
          record: row.season_to_date.record,
          end10: row.season_to_date.end / 10,
          end100: row.season_to_date.end,
          end14d10: row.rolling_14d.end / 10,
          isLive: id === activeStrategy
        }))
        .sort((left, right) => right.end100 - left.end100)
    : [];

  const recordFor = (teamId: string) => formatStandingRecord(standingsByTeamId.get(teamId));
  const teamLink = (team: { id: string; name: string; abbreviation: string }) => (
    <Link className="team-stream-link" href={`/watch/${team.id}`} title={`Open ${team.name} stream page`}>
      {team.name}
    </Link>
  );
  const teamAbbrevLink = (team: { id: string; name: string; abbreviation: string }) => (
    <Link className="team-stream-link" href={`/watch/${team.id}`} title={`Open ${team.name} stream page`}>
      {team.abbreviation}
    </Link>
  );

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Daily ticket</p>
        <h1>Best Bets</h1>
        <p className="lead">
          One bet per day from <strong>{activeStrategy}</strong>: stake a percentage of your bankroll (35% / 40% / 30% by
          ticket type), all legs same calendar day.
        </p>
        <p className="muted">
          Your bankroll: <strong>{formatBankroll(bankroll)}</strong>
          {startedAt ? ` · live tracking since ${startedAt}` : ""}
          {liveBankroll && liveBankroll.record !== "0-0" ? (
            <>
              {" "}
              · system ticket <strong>{liveBankroll.record}</strong>
              {liveBankroll.hit_rate != null ? ` (${formatPercent(liveBankroll.hit_rate)})` : ""}
            </>
          ) : liveBankroll?.today_ticket ? (
            " · first ticket pending"
          ) : (
            ""
          )}
        </p>
        {liveBankroll && (liveBankroll.tickets?.length || liveBankroll.today_ticket) ? (
          <p className="muted">
            Site auto-logs every system ticket when games finish — you don&apos;t need to track this manually.
            {liveBankroll.hit_rate != null && liveBankroll.backtest_ticket_hit_rate != null ? (
              <>
                {" "}
                Backtest over same window was ~{formatPercent(liveBankroll.backtest_ticket_hit_rate)} on tickets.
              </>
            ) : null}
          </p>
        ) : null}
        {usingModelOnlyPicks ? (
          <p className="muted">
            Live sportsbook odds aren&apos;t on today&apos;s board yet — picks use model pricing until odds load.
          </p>
        ) : null}
        {boardAgeMinutes !== null && boardAgeMinutes > 120 ? (
          <p className="warning">
            Board is <strong>{boardAgeMinutes} minutes old</strong> — refresh before betting. Starters and lines change.
          </p>
        ) : boardAgeMinutes !== null ? (
          <p className="muted">Board refreshed {boardAgeMinutes} min ago{boardGeneratedAt ? ` (${boardGeneratedAt})` : ""}.</p>
        ) : null}
        {unstableStarterGames > 0 ? (
          <p className="warning">
            {unstableStarterGames} game{unstableStarterGames === 1 ? "" : "s"}{" "}
            {unstableStarterGames === 1 ? "has" : "have"} uncertain or changed probable starters — those legs are
            excluded from parlays and confidence is capped.
          </p>
        ) : null}
      </section>

      {bestTicket ? (
        <section className="panel strong">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Bet this</p>
              <h2>
                {bestTicket.kind === "single"
                  ? "Single Moneyline"
                  : bestTicket.kind === "parlay" && bestTicket.parlay.legCount === 3
                    ? "Premium 3-Leg Parlay"
                    : "2-Leg Parlay"}
              </h2>
            </div>
            <span>Stake {formatPercent(ticketStakePct)} of bankroll</span>
          </div>
          <p className="muted">
            <strong>corr_nl_reject_both</strong> · stakes{" "}
            <strong>
              {formatPercent(OPTIMIZED_STAKE_BY_LEG_COUNT[1])} single /{" "}
              {formatPercent(OPTIMIZED_STAKE_BY_LEG_COUNT[2])} two-leg /{" "}
              {formatPercent(OPTIMIZED_STAKE_BY_LEG_COUNT[3])} three-leg
            </strong>{" "}
            of wallet. Stake <strong>{formatPercent(ticketStakePct)}</strong> ={" "}
            <strong>{formatBankroll(bankroll * ticketStakePct)}</strong> on this ticket. Model predicted winner
            only — one bet per day.
          </p>
          {bestTicket.kind === "parlay" && bestTicket.parlay.strategy === "forced_top_2" ? (
            <p className="muted">
              No strict 65%+ parlay pair today — using top-2 positive-EV legs. Backtest shows always betting beats
              sitting out on thin slates.
            </p>
          ) : null}
          {bestTicket.kind === "single" ? (
            <div className="grid two">
              <article>
                <p className="muted">Matchup</p>
                <strong>{bestTicket.bet.matchup}</strong>
                <p>
                  {teamLink(bestTicket.bet.team)} ({recordFor(bestTicket.bet.team.id)}) vs{" "}
                  {teamLink(bestTicket.bet.opponent)} ({recordFor(bestTicket.bet.opponent.id)})
                </p>
                <p className="muted">{formatCentralGameTime(bestTicket.bet.game.startsAt)}</p>
              </article>
              <article>
                <p className="muted">Line</p>
                <div className="metric">{formatOdds(bestTicket.bet.odds)}</div>
                <p className="muted">
                  Model {formatPercent(bestTicket.bet.modelProbability)} · Edge {formatPercent(bestTicket.bet.edge)}
                </p>
              </article>
            </div>
          ) : (
            <div className="stack">
              <table className="table">
                <thead>
                  <tr>
                    <th>Leg</th>
                    <th>Odds</th>
                    <th>Model</th>
                    <th>Edge</th>
                  </tr>
                </thead>
                <tbody>
                  {bestTicket.parlay.legs.map((leg) => (
                    <tr key={leg.id}>
                      <td>
                        <strong>{leg.team.abbreviation} ML</strong>
                        <p className="muted">{leg.matchup}</p>
                      </td>
                      <td>{formatOdds(leg.odds)}</td>
                      <td>{formatPercent(leg.modelProbability)}</td>
                      <td className={leg.edge > 0 ? "positive" : "warning"}>{formatPercent(leg.edge)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted">
                Combined {formatPercent(bestTicket.parlay.probability)} at {formatOdds(bestTicket.parlay.americanOdds)}
              </p>
            </div>
          )}
        </section>
      ) : (
        <section className="panel strong">
          <h2>No ticket today</h2>
          <p className="muted">No positive-EV ticket cleared today&apos;s filters. Sitting out is valid.</p>
        </section>
      )}

      {liveBankroll && (liveBankroll.tickets?.length || liveBankroll.today_ticket) ? (
        <section className="panel">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Live system record</p>
              <h2>Your tickets (auto-tracked)</h2>
            </div>
            <span>
              {liveBankroll.record}
              {liveBankroll.hit_rate != null ? ` · ${formatPercent(liveBankroll.hit_rate)}` : ""}
            </span>
          </div>
          <p className="muted">
            Started {formatBankroll(liveBankroll.starting_balance)} on {liveBankroll.started_at} → system track{" "}
            {formatBankroll(liveBankroll.balance)} ({formatBankroll(liveBankroll.profit)}).
            {liveBankroll.wallet_balance != null ? (
              <>
                {" "}
                Your wallet: <strong>{formatBankroll(liveBankroll.wallet_balance)}</strong> — stakes use this.
              </>
            ) : null}
          </p>
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Ticket</th>
                <th>Stake</th>
                <th>Result</th>
                <th>Balance</th>
              </tr>
            </thead>
            <tbody>
              {liveBankroll.today_ticket?.status === "pending" ? (
                <tr>
                  <td>{liveBankroll.today_ticket.date}</td>
                  <td>
                    <strong>{liveBankroll.today_ticket.label}</strong>
                    <p className="muted">{liveBankroll.today_ticket.legs.join(" + ")}</p>
                  </td>
                  <td>{formatBankroll(liveBankroll.today_ticket.stake_amount)}</td>
                  <td className="muted">Pending</td>
                  <td>—</td>
                </tr>
              ) : null}
              {[...(liveBankroll.tickets ?? [])].reverse().map((ticket) => (
                <tr key={ticket.date}>
                  <td>{ticket.date}</td>
                  <td>
                    <strong>{ticket.label}</strong>
                    <p className="muted">{ticket.legs.join(" + ")}</p>
                  </td>
                  <td>{formatBankroll(ticket.stake_amount)}</td>
                  <td className={ticket.won ? "positive" : "warning"}>
                    {ticket.won ? "WIN" : "LOSS"} ({formatBankroll(ticket.profit ?? 0)})
                  </td>
                  <td>{ticket.balance_after != null ? formatBankroll(ticket.balance_after) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {bettingPlan && strategyGuard ? (
        <section className="panel strong">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Live plan</p>
              <h2>{activeStrategy}</h2>
            </div>
            <span>Updated {bettingPlan.generated_at}</span>
          </div>
          <p className="lead">
            Medium+ legs only on parlays · reject same-division and same-time pairs · one ticket/day · highest score
            wins among legal 2-leg, 3-leg, or single.
          </p>
          <ol className="muted">
            {bettingPlan.strategy_rules.map((rule) => (
              <li key={rule}>{rule}</li>
            ))}
          </ol>

          <table className="table">
            <thead>
              <tr>
                <th>Ticket type</th>
                <th>% of bankroll</th>
                <th>@ your bankroll</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Single</td>
                <td>{formatPercent(bettingPlan.stake_by_leg_count["1"] ?? OPTIMIZED_STAKE_BY_LEG_COUNT[1])}</td>
                <td>${(bankroll * (bettingPlan.stake_by_leg_count["1"] ?? 0.35)).toFixed(2)}</td>
              </tr>
              <tr>
                <td>2-leg parlay</td>
                <td>{formatPercent(bettingPlan.stake_by_leg_count["2"] ?? OPTIMIZED_STAKE_BY_LEG_COUNT[2])}</td>
                <td>${(bankroll * (bettingPlan.stake_by_leg_count["2"] ?? 0.4)).toFixed(2)}</td>
              </tr>
              <tr>
                <td>3-leg parlay</td>
                <td>{formatPercent(bettingPlan.stake_by_leg_count["3"] ?? OPTIMIZED_STAKE_BY_LEG_COUNT[3])}</td>
                <td>${(bankroll * (bettingPlan.stake_by_leg_count["3"] ?? 0.3)).toFixed(2)}</td>
              </tr>
            </tbody>
          </table>

          <div className="section-heading compact" style={{ marginTop: "1.5rem" }}>
            <div>
              <p className="eyebrow">2026 backtest</p>
              <h2>Season sim (if you started opening day)</h2>
            </div>
            <span>
              {strategyGuard.period.season_start} → {strategyGuard.period.end}
            </span>
          </div>
          <p className="muted">
            All rows use the <strong>same</strong> walk-forward model and <strong>same</strong> 35/40/30% compounding.
            Older tables on this site used 30% caps and different rules — ignore those. Live plan wins on full-season $
            100 compound ({liveStats ? formatBankroll(liveStats.end) : "—"}).
          </p>

          {liveStats ? (
            <div className="grid">
              <article>
                <p className="muted">Season sim from $10 (Mar 20 start)</p>
                <div className="metric positive">{formatBankroll(liveStats.end / 10)}</div>
                <p className="muted">
                  {liveStats.record} · not your live tracker
                </p>
              </article>
              <article>
                <p className="muted">$100 bankroll (season sim)</p>
                <div className="metric positive">{formatBankroll(liveStats.end)}</div>
                <p className="muted">Best among tested rules at same stakes</p>
              </article>
            </div>
          ) : null}

          <table className="table">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Record</th>
                <th>$10 → end</th>
                <th>$100 → end</th>
                <th>Last 14d ($10) — short window</th>
              </tr>
            </thead>
            <tbody>
              {comparisonRows.map((row) => (
                <tr key={row.id}>
                  <td>{row.isLive ? `★ ${row.label}` : row.label}</td>
                  <td>{row.record}</td>
                  <td className={row.isLive ? "positive" : ""}>{formatBankroll(row.end10)}</td>
                  <td className={row.isLive ? "positive" : ""}>{formatBankroll(row.end100)}</td>
                  <td>{formatBankroll(row.end14d10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">{strategyGuard.guard.message}</p>
          <p className="muted">
            Sort the table by <strong>$100 → end</strong> for the decision that matters. The 14-day column is noisy —
            we only consider switching after another rule beats the live plan for 14 straight daily runs.
          </p>
        </section>
      ) : null}

      {ticketWalkforward ? (
        <section className="panel">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Walk-forward ledger</p>
              <h2>Best tickets — last 14 days</h2>
            </div>
            <span>
              {ticketWalkforward.last_14_days.start} → {ticketWalkforward.last_14_days.end}
            </span>
          </div>
          <p className="muted">
            Strict walk-forward replay using the full {ticketWalkforward.feature_count}-feature model (registry +
            Statcast + injuries when live). Strategy: {ticketWalkforward.strategy}. Season ticket record{" "}
            <strong>{ticketWalkforward.best_ticket_accuracy.record}</strong> (
            {formatPercent(ticketWalkforward.best_ticket_accuracy.hit_rate)}). Game picks{" "}
            {formatPercent(ticketWalkforward.game_prediction_accuracy.accuracy)}.
          </p>
          <div className="grid">
            <article>
              <p className="muted">Last 14 days tickets</p>
              <div className="metric">{ticketWalkforward.last_14_days.record}</div>
              <p className="muted">{formatPercent(ticketWalkforward.last_14_days.hit_rate)} hit rate</p>
            </article>
            <article>
              <p className="muted">Season tickets</p>
              <div className="metric">{ticketWalkforward.best_ticket_accuracy.record}</div>
              <p className="muted">{ticketWalkforward.best_ticket_accuracy.bet_days} bet days</p>
            </article>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Ticket</th>
                <th>Legs</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {ticketWalkforward.last_14_days.tickets.map((ticket) => (
                <tr key={ticket.date}>
                  <td>{ticket.date}</td>
                  <td>
                    <strong>{ticket.label}</strong>
                    <p className="muted">{ticket.ticket_type}</p>
                  </td>
                  <td>
                    {ticket.legs.map((leg) => (
                      <p key={`${ticket.date}-${leg.team}`}>
                        {leg.team} ({formatPercent(leg.model_probability)}) — {leg.matchup}
                      </p>
                    ))}
                  </td>
                  <td className={ticket.won ? "positive" : "warning"}>{ticket.result}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      <section className="panel">
        <p className="muted">Reference only — your daily bet is the ticket above, not every row here.</p>
        {bets.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Matchup / Side</th>
                <th>Odds</th>
                <th>Model</th>
                <th>Edge</th>
              </tr>
            </thead>
            <tbody>
              {bets.map((bet) => (
                <tr key={bet.id}>
                  <td>
                    <strong>{bet.matchup}</strong>
                    <p>
                      {teamLink(bet.team)} ({recordFor(bet.team.id)}) vs {teamLink(bet.opponent)} (
                      {recordFor(bet.opponent.id)})
                    </p>
                    <p className="muted">{formatCentralGameTime(bet.game.startsAt)}</p>
                  </td>
                  <td>{formatOdds(bet.odds)}</td>
                  <td>{formatPercent(bet.modelProbability)}</td>
                  <td className={bet.edge > 0 ? "positive" : "warning"}>{formatPercent(bet.edge)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">No moneyline edges on today&apos;s board yet.</p>
        )}
      </section>

      {advancedBets.length > 0 ? (
        <section className="panel">
          <h2>Advanced markets</h2>
          <p className="muted">Totals and run lines — not part of the daily moneyline ticket.</p>
          <table className="table">
            <thead>
              <tr>
                <th>Market</th>
                <th>Pick</th>
                <th>Odds</th>
                <th>Edge</th>
              </tr>
            </thead>
            <tbody>
              {advancedBets.map((bet) => (
                <tr key={bet.id}>
                  <td>{bet.market}</td>
                  <td>
                    <strong>
                      {teamAbbrevLink(bet.team)} vs {teamAbbrevLink(bet.opponent)}
                    </strong>
                    <p>
                      {bet.label} · {formatCentralGameTime(bet.game.startsAt)}
                    </p>
                  </td>
                  <td>{formatOdds(bet.odds)}</td>
                  <td className="positive">{formatPercent(bet.edge)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
    </main>
  );
}
