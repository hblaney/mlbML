import Link from "next/link";
import {
  getAdvancedBets,
  getBestBets,
  getBestDailyTicket,
  getSortedPredictions,
  getOptimizedStakePctForTicket,
  getRatchetStakePct,
  OPTIMIZED_STAKE_BY_LEG_COUNT,
  LIVE_BETTING_STRATEGY
} from "@/lib/data";
import { loadPredictionBoard, loadBettingPlan, loadLiveBankroll, loadStrategyGuard, loadBestTicketWalkforward, loadPredictionBoardMetadata, loadAccuracyOutput, loadModelHealth, loadLockedTicket } from "@/lib/model-output";
import { confidenceFromPickProbability } from "@/lib/confidence";
import { formatOdds, formatPercent } from "@/lib/odds";
import { formatStandingRecord, loadLiveStandings } from "@/lib/standings";
import { formatCentralGameTime } from "@/lib/time";

export const dynamic = "force-dynamic";

const STRATEGY_LABELS: Record<string, string> = {
  market_agree_parlay: "sim_edge_parlay (live · Monte Carlo win% vs market)",
  daily_top3_prob: "daily_top3_prob (legacy · 3 singles by win probability)",
  daily_top3_evscore: "daily_top3_evscore (legacy · EV×prob ranking)",
  daily_best_single: "daily_best_single (selective quality single)",
  parlay_first: "parlay_first (legacy · parlay-heavy)",
  best_ticket: "best_ticket (legacy · max-score incl. singles)",
  power_parlay: "power_parlay (legacy · selective H/E only)",
  high_elite_76_parlay: "high_elite_76_parlay (legacy)",
};

export default async function BestBetsPage() {
  const board = await loadPredictionBoard();
  const boardMeta = await loadPredictionBoardMetadata();
  const standings = await loadLiveStandings();
  const standingsByTeamId = new Map(standings.map((standing) => [standing.teamId, standing]));
  const [bettingPlan, strategyGuard, liveBankroll, ticketWalkforward, accuracyOutput, modelHealth, lockedTicket] = await Promise.all([
    loadBettingPlan(),
    loadStrategyGuard(),
    loadLiveBankroll(),
    loadBestTicketWalkforward(),
    loadAccuracyOutput(),
    loadModelHealth(),
    loadLockedTicket()
  ]);
  const bets = getBestBets(board);
  const advancedBets = getAdvancedBets(board);
  const usingModelOnlyPicks = bets.some((bet) => bet.modelOnly) || advancedBets.some((bet) => bet.modelOnly);
  const bestTicket = getBestDailyTicket(board);
  const topPredictions = getSortedPredictions(board).slice(0, 5);
  const stakeByLeg = bettingPlan?.stake_by_leg_count;
  const ratchetTiers = bettingPlan?.ratchet_tiers;
  const activeStrategy = bettingPlan?.strategy ?? LIVE_BETTING_STRATEGY;
  const liveStats = strategyGuard?.comparisons[activeStrategy]?.season_to_date;
  const bankroll = liveBankroll?.wallet_balance ?? liveBankroll?.balance ?? 10.0;
  // If ratchet tiers are defined, use ratchet-aware stake percentages; else fall back to fixed leg-count stakes
  const stakeSingle = ratchetTiers
    ? getRatchetStakePct(bankroll, 1, ratchetTiers)
    : (stakeByLeg?.["1"] ?? OPTIMIZED_STAKE_BY_LEG_COUNT[1]);
  const stakeParlay2 = ratchetTiers
    ? getRatchetStakePct(bankroll, 2, ratchetTiers)
    : (stakeByLeg?.["2"] ?? OPTIMIZED_STAKE_BY_LEG_COUNT[2]);
  const stakeParlay3 = ratchetTiers
    ? getRatchetStakePct(bankroll, 3, ratchetTiers)
    : (stakeByLeg?.["3"] ?? OPTIMIZED_STAKE_BY_LEG_COUNT[3]);
  const ratchetLabel = ratchetTiers
    ? (() => {
        const tier = [...ratchetTiers].reverse().find(t => bankroll >= t.min_balance) ?? ratchetTiers[0];
        const nextTier = ratchetTiers.find(t => t.min_balance > bankroll);
        return nextTier
          ? `Ratchet tier: ${formatPercent(tier.parlay_pct)} parlay / ${formatPercent(tier.single_pct)} single (steps down at $${nextTier.min_balance})`
          : `Ratchet tier: ${formatPercent(tier.parlay_pct)} parlay / ${formatPercent(tier.single_pct)} single (max protection tier)`;
      })()
    : null;
  const stakeTierLabel = ratchetTiers
    ? `${formatPercent(stakeSingle)} single / ${formatPercent(stakeParlay2)} parlay`
    : `${formatPercent(stakeSingle)} single / ${formatPercent(stakeParlay2)} two-leg / ${formatPercent(stakeParlay3)} three-leg`;
  const startedAt = liveBankroll?.started_at;
  const boardGeneratedAt = boardMeta.board_generated_at;
  const modelTrainedThrough = boardMeta.trained_through;
  const modelVersion = boardMeta.model_version;
  const pipelineVersion = boardMeta.pipeline_version;
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

  const accuracyStale =
    accuracyOutput?.trained_through &&
    modelTrainedThrough &&
    accuracyOutput.trained_through < modelTrainedThrough;
  const seasonPickAccuracy = accuracyOutput?.current_season?.market_backed_accuracy ?? null;
  const highConfAccuracy = accuracyOutput?.current_season?.high_confidence_accuracy ?? null;
  // Ratchet staking is the live mode; prove-out only when explicitly flagged active in the JSON.
  const proveOutActive =
    liveBankroll?.staking !== "ratchet" && (liveBankroll?.prove_out?.active ?? false);
  const proveOutStake = liveBankroll?.prove_out?.flat_stake_usd ?? 5;
  const formatBankroll = (value: number) =>
    value >= 100
      ? `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
      : `$${value.toFixed(2)}`;

  // Show live plan vs legacy high_elite side-by-side for comparison.
  const liveInGuard = Boolean(strategyGuard?.comparisons[activeStrategy]);
  const SHOWN_STRATEGIES = new Set([activeStrategy, "edge_value_ticket", "best_ticket", "high_elite_76_parlay"]);
  const comparisonRows = strategyGuard
    ? Object.entries(strategyGuard.comparisons)
        .filter(([id]) => SHOWN_STRATEGIES.has(id))
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
        <p className="eyebrow">Daily ticket</p>
        <h1>Best Bets</h1>
        <p className="lead">
          One bet per day from <strong>{activeStrategy}</strong>: edge-first ranking (not raw win %), stake a percentage of
          your bankroll ({stakeTierLabel} of wallet by ticket type), all legs same calendar day.
        </p>
        {topPredictions.length > 0 ? (
          <p className="muted">
            Top picks by model win %:{" "}
            {topPredictions.map((game) => game.predictedTeam?.toUpperCase()).join(", ")}
          </p>
        ) : null}
        {ratchetLabel && (
          <p className="muted">{ratchetLabel}</p>
        )}
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
        {boardAgeMinutes !== null && boardAgeMinutes > 60 ? (
          <p className="warning">
            Board is <strong>{boardAgeMinutes} minutes old</strong> (last update{" "}
            {boardGeneratedAt ? formatCentralGameTime(boardGeneratedAt) : "unknown"}). Auto-refresh runs hourly
            10&nbsp;AM–10&nbsp;PM Central — hard refresh in a few minutes or check back after the next hour.
          </p>
        ) : boardAgeMinutes !== null ? (
          <p className="muted">
            Board auto-refreshed {boardAgeMinutes} min ago
            {boardGeneratedAt ? ` · ${formatCentralGameTime(boardGeneratedAt)}` : ""}.
          </p>
        ) : null}
        {modelTrainedThrough ? (
          <p className="muted">
            Model trained through <strong>{modelTrainedThrough}</strong>
            {modelVersion ? (
              <>
                {" "}
                (<span>{modelVersion}</span>
                {pipelineVersion ? ` · ${pipelineVersion}` : ""})
              </>
            ) : null}
            {seasonPickAccuracy != null ? (
              <>
                {" "}
                · 2026 pick accuracy <strong>{formatPercent(seasonPickAccuracy)}</strong> overall
                {highConfAccuracy != null ? ` · ${formatPercent(highConfAccuracy)} on High/Elite only` : ""}
              </>
            ) : null}
            {accuracyStale ? (
              <>
                {" "}
                · <span className="warning">accuracy audit stale — full retrain pending</span>
              </>
            ) : null}
          </p>
        ) : null}
        {unstableStarterGames > 0 ? (
          <p className="warning">
            {unstableStarterGames} game{unstableStarterGames === 1 ? "" : "s"}{" "}
            {unstableStarterGames === 1 ? "has" : "have"} uncertain or changed probable starters — those legs are
            excluded from parlays (pick and confidence unchanged).
          </p>
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
                <table className="table">
                  <thead>
                    <tr>
                      <th>Leg</th>
                      <th>Conf</th>
                      <th>Odds</th>
                      <th>Model</th>
                      <th>Edge</th>
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
                        <td>{formatPercent(leg.pickProbability)}</td>
                        <td className={leg.edge > 0 ? "positive" : "warning"}>{formatPercent(leg.edge)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
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
              <table className="table">
                <thead>
                  <tr>
                    <th>Pick</th>
                    <th>Odds</th>
                    <th>Model</th>
                    <th>Edge</th>
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
                      <td className={bet.edge > 0 ? "positive" : "warning"}>{formatPercent(bet.edge)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted">Three separate singles, not a parlay. Stake each one separately.</p>
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
            Each day the system picks the highest-scoring qualified 2/3/4-leg parlay or +EV single
            · prove-out sizing <strong>18% parlay / 12% single</strong> below $200 (~$1.20 single / ~$1.80 parlay at $10).
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
                <td>{formatPercent(stakeSingle)}</td>
                <td>${(bankroll * stakeSingle).toFixed(2)}</td>
              </tr>
              <tr>
                <td>2-leg parlay</td>
                <td>{formatPercent(stakeParlay2)}</td>
                <td>${(bankroll * stakeParlay2).toFixed(2)}</td>
              </tr>
              <tr>
                <td>3-leg parlay</td>
                <td>{formatPercent(stakeParlay3)}</td>
                <td>${(bankroll * stakeParlay3).toFixed(2)}</td>
              </tr>
            </tbody>
          </table>

          {ratchetTiers && (
            <>
              <p className="eyebrow" style={{ marginTop: "1.25rem" }}>Ratchet staking schedule</p>
              <table className="table">
                <thead>
                  <tr>
                    <th>Bankroll range</th>
                    <th>Parlay stake</th>
                    <th>Single stake</th>
                    <th>Mode</th>
                  </tr>
                </thead>
                <tbody>
                  {ratchetTiers.map((tier, i) => {
                    const isActive = bankroll >= tier.min_balance && (tier.max_balance === null || bankroll <= tier.max_balance);
                    return (
                      <tr key={i} style={isActive ? { fontWeight: 600 } : undefined}>
                        <td>
                          ${tier.min_balance.toLocaleString()}
                          {tier.max_balance !== null ? ` – $${tier.max_balance.toLocaleString()}` : "+"}
                          {isActive ? " ◀ current" : ""}
                        </td>
                        <td>{formatPercent(tier.parlay_pct)}</td>
                        <td>{formatPercent(tier.single_pct)}</td>
                        <td>{i === 0 ? "Max growth" : i === 1 ? "Moderate" : "Conservative"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}

          <div className="section-heading compact" style={{ marginTop: "1.5rem" }}>
            <div>
              <p className="eyebrow">2026 backtest</p>
              <h2>Season sim (if you started opening day)</h2>
            </div>
            <span>
              {bettingPlan.backtest_period.start} → {bettingPlan.backtest_period.end}
            </span>
          </div>
          <div className="grid">
            <article>
              <p className="muted">$32 → end (growth compound, honest model)</p>
              <div className="metric positive">~$8,700</div>
              <p className="muted">50–31 full season · 28–13 forward proxy · best_ticket plan</p>
            </article>
            <article>
              <p className="muted">Typical stake at $32 (prove-out)</p>
              <div className="metric">~$6</div>
              <p className="muted">18% parlay / 12% single · first 20 locked tickets</p>
            </article>
          </div>
          <p className="muted">
            Walk-forward sim on the honest model (no pitcher leakage). Backtest, not a guarantee — requires
            betting the locked ticket every qualified day and reinvesting wins.
          </p>

          {liveInGuard ? (
            <>
              <table className="table">
                <thead>
                  <tr>
                    <th>Strategy</th>
                    <th>Record</th>
                    <th>$10 → end</th>
                    <th>$100 → end</th>
                  </tr>
                </thead>
                <tbody>
                  {comparisonRows.map((row) => (
                    <tr key={row.id}>
                      <td>{row.isLive ? `★ ${row.label}` : row.label}</td>
                      <td>{row.record}</td>
                      <td className={row.isLive ? "positive" : ""}>{formatBankroll(row.end10)}</td>
                      <td className={row.isLive ? "positive" : ""}>{formatBankroll(row.end100)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted">{strategyGuard.guard.message}</p>
            </>
          ) : null}
        </section>
      ) : null}

      {ticketWalkforward && ticketWalkforward.strategy === activeStrategy ? (
        <section className="panel">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">System ticket audit (backtest)</p>
              <h2>{activeStrategy} — last 14 days</h2>
            </div>
            <span>
              {ticketWalkforward.last_14_days.start} → {ticketWalkforward.last_14_days.end}
            </span>
          </div>
          <p className="muted">
            Backtest replay only — historical audit of the same <strong>{activeStrategy}</strong> rules you bet on
            Robinhood. Season ticket record <strong>{ticketWalkforward.best_ticket_accuracy.record}</strong> (
            {formatPercent(ticketWalkforward.best_ticket_accuracy.hit_rate)}).
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
