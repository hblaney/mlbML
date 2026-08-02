import Link from "next/link";
import {
  getBestBets,
  getBestDailyTicket,
  getOptimizedStakePctForTicket,
  getRatchetStakePct,
  OPTIMIZED_STAKE_BY_LEG_COUNT,
  LIVE_BETTING_STRATEGY
} from "@/lib/data";
import {
  loadPredictionBoard,
  loadBettingPlan,
  loadLiveBankroll,
  loadPredictionBoardMetadata,
  loadModelHealth,
  loadLockedTicket,
} from "@/lib/model-output";
import { formatOdds, formatPercent } from "@/lib/odds";
import { formatStandingRecord, loadLiveStandings } from "@/lib/standings";
import { formatCentralGameTime } from "@/lib/time";

export const dynamic = "force-dynamic";

export default async function BestBetsPage() {
  const board = await loadPredictionBoard();
  const boardMeta = await loadPredictionBoardMetadata();
  const standings = await loadLiveStandings();
  const standingsByTeamId = new Map(standings.map((standing) => [standing.teamId, standing]));
  const [bettingPlan, liveBankroll, modelHealth, lockedTicket] = await Promise.all([
    loadBettingPlan(),
    loadLiveBankroll(),
    loadModelHealth(),
    loadLockedTicket(),
  ]);
  const bets = getBestBets(board);
  const usingModelOnlyPicks = bets.some((bet) => bet.modelOnly);
  const bestTicket = getBestDailyTicket(board);
  const stakeByLeg = bettingPlan?.stake_by_leg_count;
  const ratchetTiers = bettingPlan?.ratchet_tiers;
  const activeStrategy = bettingPlan?.strategy ?? LIVE_BETTING_STRATEGY;
  const bankroll = liveBankroll?.wallet_balance ?? liveBankroll?.balance ?? 10.0;
  const stakeSingle = ratchetTiers
    ? getRatchetStakePct(bankroll, 1, ratchetTiers)
    : (stakeByLeg?.["1"] ?? OPTIMIZED_STAKE_BY_LEG_COUNT[1]);
  const stakeParlay2 = ratchetTiers
    ? getRatchetStakePct(bankroll, 2, ratchetTiers)
    : (stakeByLeg?.["2"] ?? OPTIMIZED_STAKE_BY_LEG_COUNT[2]);
  const stakeParlay3 = ratchetTiers
    ? getRatchetStakePct(bankroll, 3, ratchetTiers)
    : (stakeByLeg?.["3"] ?? OPTIMIZED_STAKE_BY_LEG_COUNT[3]);
  const boardGeneratedAt = boardMeta.board_generated_at;
  const boardAgeMinutes = boardGeneratedAt
    ? Math.max(0, Math.round((Date.now() - new Date(boardGeneratedAt).getTime()) / 60_000))
    : null;
  const unstableStarterGames = board.filter((game) => game.pitcherChanged || game.starterCertain === false).length;

  // ── Live system status (so a stale board is obvious before you bet) ──────────
  const centralToday = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Chicago" }).format(new Date());
  const officialLock = lockedTicket?.date === centralToday ? lockedTicket : null;
  const officialTicket = officialLock?.ticket ?? null;
  const lockedAtLabel = officialLock?.locked_at
    ? new Intl.DateTimeFormat("en-US", {
        timeZone: "America/Chicago",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }).format(new Date(officialLock.locked_at))
    : null;
  const liveTicketLabel = bestTicket
    ? bestTicket.kind === "single"
      ? `${bestTicket.bet.team.abbreviation} ML`
      : bestTicket.kind === "multi_single"
        ? bestTicket.bets.map((bet) => `${bet.team.abbreviation} ML`).join(" + ")
      : bestTicket.parlay.legs.map((leg) => `${leg.team.abbreviation} ML`).join(" + ")
    : null;
  const ticketMismatch =
    officialTicket &&
    officialTicket.kind !== "skip" &&
    liveTicketLabel &&
    officialTicket.label !== liveTicketLabel;
  const displayLegCount = officialTicket?.leg_count ?? (bestTicket
    ? (bestTicket.kind === "single" ? 1 : bestTicket.kind === "multi_single" ? bestTicket.bets.length : bestTicket.parlay.legCount)
    : 2);
  const ticketLegCount = displayLegCount;
  const ticketStakePct = ratchetTiers
    ? bestTicket?.kind === "multi_single" || officialTicket?.kind === "multi_single"
      ? 0.5
      : getRatchetStakePct(bankroll, ticketLegCount, ratchetTiers)
    : getOptimizedStakePctForTicket(bestTicket, stakeByLeg);
  const perSingleStakePct = displayLegCount > 1 ? ticketStakePct / displayLegCount : ticketStakePct;
  const boardIsToday = boardMeta.generated_at === centralToday;
  const STALE_AGE_MIN = 180; // 3h without a refresh during the day = something is off
  const freshness: "fresh" | "aging" | "stale" = !boardIsToday
    ? "stale"
    : boardAgeMinutes != null && boardAgeMinutes > STALE_AGE_MIN
      ? "aging"
      : "fresh";
  const boardUpdatedLabel = boardGeneratedAt
    ? new Intl.DateTimeFormat("en-US", {
        timeZone: "America/Chicago",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }).format(new Date(boardGeneratedAt))
    : null;
  const boardAgeLabel =
    boardAgeMinutes == null
      ? null
      : boardAgeMinutes < 60
        ? `${boardAgeMinutes} min ago`
        : `${Math.floor(boardAgeMinutes / 60)}h ${boardAgeMinutes % 60}m ago`;
  const healthStatus = modelHealth?.overall_status ?? null;
  const statusOk = freshness === "fresh" && (healthStatus === "healthy" || healthStatus == null);

  const proveOutActive =
    liveBankroll?.staking !== "ratchet" && (liveBankroll?.prove_out?.active ?? false);
  const proveOutStake = liveBankroll?.prove_out?.flat_stake_usd ?? 5;
  const formatBankroll = (value: number) =>
    value >= 100
      ? `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
      : `$${value.toFixed(2)}`;

  const recordFor = (teamId: string) => formatStandingRecord(standingsByTeamId.get(teamId));
  const teamLink = (team: { id: string; name: string; abbreviation: string }) => (
    <Link className="team-stream-link" href={`/watch/${team.id}`} title={`Open ${team.name} stream page`}>
      {team.name}
    </Link>
  );

  return (
    <main className="shell stack">
      <section
        className="panel"
        style={{
          borderLeft: `4px solid ${statusOk ? "#16a34a" : freshness === "stale" ? "#dc2626" : "#d97706"}`,
        }}
      >
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">System status</p>
            <h2 style={{ margin: 0 }}>
              {statusOk
                ? "Live · board is current"
                : freshness === "stale"
                  ? "Board is not today's slate"
                  : "Board may be stale"}
            </h2>
          </div>
          <span className={statusOk ? "positive" : "warning"}>
            {statusOk ? "FRESH" : freshness === "stale" ? "STALE" : "CHECK"}
          </span>
        </div>
        <p className="muted">
          {boardUpdatedLabel
            ? <>Board updated <strong>{boardUpdatedLabel} CT</strong>{boardAgeLabel ? ` (${boardAgeLabel})` : ""}.</>
            : "Board update time unavailable."}
          {" "}
          {freshness === "stale" ? (
            <>The published board is from <strong>{boardMeta.generated_at ?? "an earlier day"}</strong>, not today
              ({centralToday}). The automated 11&nbsp;AM CT job rebuilds it daily — if this persists, the run may have
              failed. Don&apos;t place today&apos;s ticket from this board yet.</>
          ) : freshness === "aging" ? (
            <>It hasn&apos;t refreshed in over {Math.floor((boardAgeMinutes ?? 0) / 60)}h, so moneylines may have moved.
              The hourly refresh should update it shortly.</>
          ) : (
            <>Auto-refreshes daily at 11&nbsp;AM CT plus hourly through the day — no manual run needed.</>
          )}
          {healthStatus ? (
            <>
              {" "}Model self-check: <strong className={healthStatus === "healthy" ? "positive" : "warning"}>{healthStatus}</strong>.
            </>
          ) : null}
        </p>
      </section>
      <section className="panel strong">
        <p className="eyebrow">Moneyline</p>
        <h1>Daily ticket</h1>
        <p className="lead">
          One locked card per day. Bankroll <strong>{formatBankroll(bankroll)}</strong>
          {liveBankroll && liveBankroll.record !== "0-0" ? (
            <>
              {" "}
              · record <strong>{liveBankroll.record}</strong>
              {liveBankroll.hit_rate != null ? ` (${formatPercent(liveBankroll.hit_rate)})` : ""}
            </>
          ) : null}
          . Full history on <Link href="/history">Record</Link>.
        </p>
        {unstableStarterGames > 0 ? (
          <p className="warning">
            {unstableStarterGames} game{unstableStarterGames === 1 ? "" : "s"} with uncertain starters —
            those legs are excluded from parlays.
          </p>
        ) : null}
        {usingModelOnlyPicks ? (
          <p className="muted">Sportsbook odds still loading — picks use model pricing for now.</p>
        ) : null}
      </section>

      {officialTicket ? (
        <section className="panel strong">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Official ticket — locked</p>
              <h2>
                {officialTicket.kind === "skip"
                  ? "No bet today"
                  : officialTicket.kind === "single"
                    ? "Single Moneyline"
                    : officialTicket.kind === "multi_single"
                      ? "3 Moneyline Singles"
                    : officialTicket.leg_count === 3
                      ? "Premium 3-Leg Parlay"
                      : "2-Leg Parlay"}
              </h2>
            </div>
            <span className="positive">LOCKED{lockedAtLabel ? ` ${lockedAtLabel} CT` : ""}</span>
          </div>
          <p className="muted">
            This is the <strong>only</strong> card to bet from today. It was frozen at the first morning publish and
            will <strong>not</strong> change when the model retrains or the board refreshes later in the day.
            {officialLock?.model_version ? ` Model at lock: ${officialLock.model_version}.` : ""}
          </p>
          {ticketMismatch ? (
            <p className="warning">
              The live board currently shows a different ticket ({liveTicketLabel}). Ignore that — bet{" "}
              <strong>{officialTicket.label}</strong> only (what was locked this morning).
            </p>
          ) : null}
          {officialTicket.kind === "skip" ? (
            <p className="lead">No High/Elite picks with edge qualified at lock time. Skip today.</p>
          ) : (
            <>
              <p className="muted">
                <strong>{officialTicket.label}</strong> · stake{" "}
                <strong>{formatBankroll(bankroll * ticketStakePct)}</strong> ({formatPercent(ticketStakePct)} of{" "}
                {formatBankroll(bankroll)}
                {officialTicket.kind === "multi_single"
                  ? `, split ${formatBankroll(bankroll * perSingleStakePct)} each`
                  : ""}
                )
              </p>
              {officialTicket.leg_details && officialTicket.leg_details.length > 0 ? (
                <div className="table-scroll">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Leg</th>
                      <th>Conf</th>
                      <th>Odds</th>
                      <th className="hide-sm">Model</th>
                      <th className="hide-sm">Edge</th>
                    </tr>
                  </thead>
                  <tbody>
                    {officialTicket.leg_details.map((leg) => (
                      <tr key={leg.team}>
                        <td>
                          <strong>{leg.team} ML</strong>
                          <p className="muted">{leg.matchup}</p>
                        </td>
                        <td>{leg.confidence}</td>
                        <td>{formatOdds(leg.odds)}</td>
                        <td className="hide-sm">{formatPercent(leg.pickProbability)}</td>
                        <td className={`hide-sm ${leg.edge > 0 ? "positive" : "warning"}`}>
                          {formatPercent(leg.edge)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              ) : (
                <p className="lead">{officialTicket.legs.join(" + ")}</p>
              )}
              {officialTicket.model_probability != null && officialTicket.odds != null ? (
                <p className="muted">
                  Combined {formatPercent(officialTicket.model_probability)} at{" "}
                  {formatOdds(officialTicket.odds)}
                </p>
              ) : null}
            </>
          )}
        </section>
      ) : null}

      {!officialTicket && bestTicket ? (
        <section className="panel strong">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Bet this</p>
              <h2>
                {bestTicket.kind === "single"
                  ? "Single Moneyline"
                  : bestTicket.kind === "multi_single"
                    ? "3 Moneyline Singles"
                  : bestTicket.kind === "parlay" && bestTicket.parlay.legCount === 3
                    ? "Premium 3-Leg Parlay"
                    : "2-Leg Parlay"}
              </h2>
            </div>
            <span>{proveOutActive ? `Bet $${proveOutStake} flat` : `Stake ${formatPercent(ticketStakePct)} of bankroll`}</span>
          </div>
          <p className="muted">
            <strong>{activeStrategy}</strong> ·{" "}
            {proveOutActive ? (
              <>
                Your Robinhood bet: <strong>${proveOutStake.toFixed(0)} flat</strong> on this ticket — copy legs
                exactly.
              </>
            ) : (
              <>
                Stakes{" "}
                <strong>
                  {formatPercent(stakeSingle)} single / {formatPercent(stakeParlay2)} two-leg /{" "}
                  {formatPercent(stakeParlay3)} three-leg
                </strong>{" "}
                of wallet ({formatBankroll(bankroll * ticketStakePct)} total
                {bestTicket.kind === "multi_single"
                  ? `, ${formatBankroll(bankroll * perSingleStakePct)} each`
                  : " on this ticket"}
                ).
              </>
            )}{" "}
            Model predicted winners only.
          </p>
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
          ) : bestTicket.kind === "multi_single" ? (
            <div className="stack">
              <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Pick</th>
                    <th>Odds</th>
                    <th>Model</th>
                    <th className="hide-sm">Edge</th>
                  </tr>
                </thead>
                <tbody>
                  {bestTicket.bets.map((bet) => (
                    <tr key={bet.id}>
                      <td>
                        <strong>{bet.team.abbreviation} ML</strong>
                        <p className="muted">{bet.matchup}</p>
                      </td>
                      <td>{formatOdds(bet.odds)}</td>
                      <td>{formatPercent(bet.modelProbability)}</td>
                      <td className={`hide-sm ${bet.edge > 0 ? "positive" : "warning"}`}>
                        {formatPercent(bet.edge)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
              <p className="muted">Three separate singles, not a parlay. Stake each one separately.</p>
            </div>
          ) : (
            <div className="stack">
              <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Leg</th>
                    <th>Odds</th>
                    <th>Model</th>
                    <th className="hide-sm">Edge</th>
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
                      <td className={`hide-sm ${leg.edge > 0 ? "positive" : "warning"}`}>
                        {formatPercent(leg.edge)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
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
              <p className="eyebrow">Recent tickets</p>
              <h2>Last few results</h2>
            </div>
            <Link href="/history" className="muted">
              Full record →
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
                {liveBankroll.today_ticket?.status === "pending" ? (
                  <tr>
                    <td>{liveBankroll.today_ticket.date}</td>
                    <td>
                      <strong>{liveBankroll.today_ticket.label}</strong>
                    </td>
                    <td className="muted">Pending</td>
                  </tr>
                ) : null}
                {[...(liveBankroll.tickets ?? [])]
                  .reverse()
                  .slice(0, 7)
                  .map((ticket) => (
                    <tr key={ticket.date}>
                      <td>{ticket.date}</td>
                      <td>
                        <strong>{ticket.label}</strong>
                      </td>
                      <td className={ticket.won ? "positive" : "warning"}>
                        {ticket.won ? "WIN" : "LOSS"}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <section className="panel">
        <div className="section-heading compact">
          <h2>Other ML edges</h2>
          <span className="muted">Reference only</span>
        </div>
        {bets.length > 0 ? (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Matchup</th>
                  <th>Odds</th>
                  <th>Model</th>
                  <th className="hide-sm">Edge</th>
                </tr>
              </thead>
              <tbody>
                {bets.slice(0, 10).map((bet) => (
                  <tr key={bet.id}>
                    <td>
                      <strong>{bet.matchup}</strong>
                      <p className="muted small">{formatCentralGameTime(bet.game.startsAt)}</p>
                    </td>
                    <td>{formatOdds(bet.odds)}</td>
                    <td>{formatPercent(bet.modelProbability)}</td>
                    <td className={`hide-sm ${bet.edge > 0 ? "positive" : "warning"}`}>
                      {formatPercent(bet.edge)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">No moneyline edges on today&apos;s board yet.</p>
        )}
      </section>
    </main>
  );
}
