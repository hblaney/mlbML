import Link from "next/link";
import { LIVE_BETTING_STRATEGY } from "@/lib/data";
import {
  loadAccuracyOutput,
  loadClvOutput,
  loadModelHealth,
  loadFullPredictionHistory,
  loadLiveBankroll,
  loadLiveModelPerformance,
  loadBettingPlan,
  loadStrategyGuard
} from "@/lib/model-output";
import { formatPercent } from "@/lib/odds";
import { normalizeTeamId, teams } from "@/lib/data";

export const dynamic = "force-dynamic";

function teamIdForLabel(label: string) {
  const normalized = normalizeTeamId(label);
  const lowerLabel = label.toLowerCase();
  const team = teams.find(
    (item) =>
      item.id === normalized ||
      item.abbreviation.toLowerCase() === lowerLabel ||
      item.name.toLowerCase() === lowerLabel ||
      item.shortName.toLowerCase() === lowerLabel
  );

  return team?.id ?? normalized;
}

function teamHistoryLink(label: string) {
  const teamId = teamIdForLabel(label);

  return (
    <Link className="team-stream-link" href={`/watch/${teamId}`} title={`Open ${label} stream page`}>
      {label}
    </Link>
  );
}

function currency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD"
  }).format(value);
}

function summarizeRows(rows: { correct: number }[]) {
  const wins = rows.filter((row) => row.correct).length;
  const total = rows.length;

  return {
    wins,
    losses: total - wins,
    total,
    accuracy: total > 0 ? wins / total : null
  };
}

function formatBankroll(value: number) {
  if (value >= 1_000_000) {
    return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  }
  if (value >= 100) {
    return currency(value);
  }
  return `$${value.toFixed(2)}`;
}

function ticketTypeLabel(legCount: number) {
  if (legCount === 1) {
    return "Single";
  }
  if (legCount === 2) {
    return "2-leg parlay";
  }
  if (legCount === 3) {
    return "3-leg parlay";
  }
  return `${legCount}-leg`;
}

export default async function HistoryPage() {
  const output = await loadAccuracyOutput();
  const clv = await loadClvOutput();
  const health = await loadModelHealth();
  const fullHistory = await loadFullPredictionHistory();
  const [strategyGuard, bettingPlan, liveBankroll] = await Promise.all([
    loadStrategyGuard(),
    loadBettingPlan(),
    loadLiveBankroll()
  ]);
  const liveModelPerformance = await loadLiveModelPerformance();
  const recentWeeks = output ? Object.entries(output.weekly_accuracy).slice(-8) : [];
  const predictionRows = fullHistory.length > 0 ? fullHistory : output?.prediction_history ?? output?.recent_predictions ?? [];
  const currentSeason = output?.season ?? liveModelPerformance?.season ?? new Date().getFullYear().toString();
  const seasonMarketRows = predictionRows.filter(
    (row) => row.date.startsWith(currentSeason) && row.marketBacked && row.actual
  );
  const seasonHighRows = seasonMarketRows.filter((row) => row.confidence === "High" || row.confidence === "Elite");
  const seasonSummary = summarizeRows(seasonMarketRows);
  const seasonHighSummary = summarizeRows(seasonHighRows);
  const eliteConfidenceRows = seasonMarketRows.filter((row) => row.confidence === "Elite");
  const eliteConfidenceSummary = summarizeRows(eliteConfidenceRows);
  const highConfidenceRows = seasonHighRows;
  const highConfidenceSummary = seasonHighSummary;
  const confidenceSummaries = (["Elite", "High", "Medium", "Low"] as const).map((confidence) => ({
    confidence,
    ...summarizeRows(seasonMarketRows.filter((row) => row.confidence === confidence))
  }));
  const rowsByDate = predictionRows.reduce<Record<string, typeof predictionRows>>((groups, row) => {
    groups[row.date] = [...(groups[row.date] ?? []), row];
    return groups;
  }, {});

  const activeStrategy = bettingPlan?.strategy ?? strategyGuard?.live_strategy ?? LIVE_BETTING_STRATEGY;
  // Ratchet staking is canonical — describe the tiers rather than the old fixed 35/45/10 leg stakes.
  const ratchetTiers = liveBankroll?.ratchet_tiers ?? bettingPlan?.ratchet_tiers;
  const stakeTierLabel = ratchetTiers && ratchetTiers.length > 0
    ? ratchetTiers
        .map((t) =>
          `${formatPercent(t.parlay_pct)}/${formatPercent(t.single_pct)} ${
            t.max_balance === null ? `$${t.min_balance}+` : `<$${t.max_balance + 1}`
          }`
        )
        .join(" · ")
    : "ratchet staking";
  // Only use the guard's compound sim when it actually reflects the live strategy — otherwise
  // it shows stale trg59 numbers (e.g. $106M) that have nothing to do with the current plan.
  const liveCompound =
    strategyGuard?.live_compound?.strategy === activeStrategy ? strategyGuard.live_compound : undefined;
  const compoundFrom10 = liveCompound?.from_10;
  const compoundCheckpoints = compoundFrom10?.checkpoints ?? [];
  const liveCheckpointsByDate = new Map(compoundCheckpoints.map((checkpoint) => [checkpoint.date, checkpoint]));
  const recentCompoundCheckpoints = compoundCheckpoints.slice(-12).reverse();
  const ticketMix = compoundCheckpoints.reduce<Record<number, number>>((counts, checkpoint) => {
    counts[checkpoint.leg_count] = (counts[checkpoint.leg_count] ?? 0) + 1;
    return counts;
  }, {});
  const primaryAccuracy =
    liveModelPerformance?.overall.hit_rate
    ?? output?.current_season?.market_backed_accuracy
    ?? seasonSummary.accuracy;
  const primaryGames =
    liveModelPerformance?.overall.bets
    ?? output?.current_season?.market_backed_games
    ?? seasonSummary.total;
  const primaryRecord = liveModelPerformance
    ? `${liveModelPerformance.overall.wins}-${liveModelPerformance.overall.losses}`
    : seasonSummary.total > 0
      ? `${seasonSummary.wins}-${seasonSummary.losses}`
      : null;
  const liveHighConfidence = liveModelPerformance?.high_confidence;
  const archiveAccuracy = output?.archive?.overall_accuracy ?? null;
  const archiveGames = output?.archive?.evaluated_games ?? 0;

  const days = Object.entries(rowsByDate)
    .sort(([left], [right]) => right.localeCompare(left))
    .map(([date, predictions]) => {
      const sortedPredictions = [...predictions].sort((left, right) => {
        const leftTime = left.startsAt ?? "";
        const rightTime = right.startsAt ?? "";
        return leftTime.localeCompare(rightTime);
      });
      const correct = sortedPredictions.filter((row) => row.correct).length;
      const total = sortedPredictions.length;
      const highConfidence = sortedPredictions.filter((row) => row.confidence === "High" || row.confidence === "Elite");
      const highCorrect = highConfidence.filter((row) => row.correct).length;

      return {
        date,
        accuracy: total > 0 ? correct / total : 0,
        correct,
        total,
        highAccuracy: highConfidence.length > 0 ? highCorrect / highConfidence.length : null,
        highCorrect,
        highTotal: highConfidence.length,
        predictions: sortedPredictions
      };
    });

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Public backtesting</p>
        <h1>Accuracy</h1>
        <p className="lead">
          Model pick accuracy plus walk-forward backtests for the live daily ticket ({activeStrategy}).
        </p>
      </section>

      {output ? (
        <>
          <section className="grid">
            <article className="panel">
              <p className="muted">2026 Overall</p>
              <div className="metric">{primaryAccuracy !== null ? formatPercent(primaryAccuracy) : "Pending"}</div>
              <p>
                {primaryRecord ? `${primaryRecord} record · ` : ""}
                {primaryGames.toFixed(0)} current-season games
              </p>
            </article>
            <article className="panel">
              <p className="muted">High / Elite Picks</p>
              <div className={(liveHighConfidence?.hit_rate ?? seasonHighSummary.accuracy ?? 0) >= 0.6 ? "metric positive" : "metric warning"}>
                {liveHighConfidence
                  ? formatPercent(liveHighConfidence.hit_rate)
                  : seasonHighSummary.accuracy !== null
                    ? formatPercent(seasonHighSummary.accuracy)
                    : "-"}
              </div>
              <p className="muted">
                {liveHighConfidence
                  ? `${liveHighConfidence.wins}-${liveHighConfidence.losses} on ${liveHighConfidence.bets} High/Elite picks`
                  : seasonHighSummary.total > 0
                    ? `${seasonHighSummary.wins}-${seasonHighSummary.losses} on ${seasonHighSummary.total} High/Elite picks`
                    : "Current-season High/Elite picks"}
              </p>
            </article>
            <article className="panel">
              <p className="muted">Last 7 Days</p>
              {(() => {
                const last7 = liveModelPerformance?.last_7_days ?? output.last_7_days;
                const rate = last7?.hit_rate ?? null;
                return (
                  <>
                    <div className={rate !== null && rate >= 0.55 ? "metric positive" : "metric warning"}>
                      {rate !== null ? formatPercent(rate) : "-"}
                    </div>
                    <p className="muted">
                      {last7 && last7.bets > 0
                        ? `${last7.wins}-${last7.losses} on ${last7.bets} picks`
                        : "No recent graded picks"}
                    </p>
                  </>
                );
              })()}
            </article>
            <article className="panel">
              <p className="muted">All-History Archive</p>
              <div className="metric">{archiveAccuracy !== null ? formatPercent(archiveAccuracy) : "-"}</div>
              <p className="muted">{archiveGames.toFixed(0)} blended 2025–2026 games</p>
            </article>
          </section>

          {health ? (
            <section className="panel">
              <div className="section-heading compact">
                <div>
                  <p className="eyebrow">Model Health</p>
                  <h2>Is the model still calibrated?</h2>
                </div>
                <span
                  className={
                    health.overall_status === "healthy"
                      ? "positive"
                      : health.overall_status === "watch"
                        ? "warning"
                        : "warning"
                  }
                >
                  {health.overall_status.toUpperCase()}
                </span>
              </div>
              <p className="lead">
                A nightly self-check grades the live probability against fixed quality gates on the trailing
                250 picks — calibration error (ECE), discrimination (AUC), log-loss, and accuracy. If the model
                ever drifts out of calibration it drops to <strong>watch</strong> or <strong>degraded</strong> here
                instead of failing silently.
              </p>
              <table className="table">
                <thead>
                  <tr>
                    <th>Window</th>
                    <th>Picks</th>
                    <th>Accuracy</th>
                    <th>Log-loss</th>
                    <th>AUC</th>
                    <th>ECE</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(health.windows).map(([name, w]) => (
                    <tr key={name}>
                      <td>{name}</td>
                      <td>{w.n}</td>
                      <td>{formatPercent(w.accuracy)}</td>
                      <td>{w.log_loss.toFixed(4)}</td>
                      <td>{w.auc.toFixed(3)}</td>
                      <td className={w.ece <= 0.06 ? "positive" : w.ece <= 0.1 ? "" : "warning"}>
                        {w.ece.toFixed(4)}
                      </td>
                      <td className={w.status === "healthy" ? "positive" : "warning"}>{w.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted">
                Recalibration check:{" "}
                {health.recalibration.verdict === "none_raw_is_calibrated"
                  ? "raw model is well-calibrated — no correction applied (a Platt fit on a held-out split did not beat it on both log-loss and ECE)."
                  : health.recalibration.verdict === "apply_platt"
                    ? "a validated Platt recalibration would improve the held-out split and is recommended."
                    : `${health.recalibration.verdict}.`}
                {health.recent_trend.last30_accuracy != null
                  ? ` Last-30 trend: ${formatPercent(health.recent_trend.last30_accuracy)} (season ${
                      health.recent_trend.season_accuracy != null
                        ? formatPercent(health.recent_trend.season_accuracy)
                        : "-"
                    }).`
                  : ""}
              </p>
            </section>
          ) : null}

          {clv && clv.overall.n > 0 ? (
            <section className="panel">
              <div className="section-heading compact">
                <div>
                  <p className="eyebrow">Closing Line Value</p>
                  <h2>Are we beating the market?</h2>
                </div>
                <span>{clv.overall.n} picks with open + close odds</span>
              </div>
              <p className="lead">
                CLV is the pro standard for proving a real edge: it measures how often our picked side&apos;s
                price shortens (moves toward us) by first pitch. Beating the close consistently means sharp
                money agrees with us — independent of whether any single bet won.
              </p>
              <section className="grid">
                <article className="panel">
                  <p className="muted">Beat-close rate</p>
                  <div className={(clv.overall.beat_close_rate ?? 0) >= 0.55 ? "metric positive" : "metric warning"}>
                    {clv.overall.beat_close_rate != null ? formatPercent(clv.overall.beat_close_rate) : "-"}
                  </div>
                  <p className="muted">50% = no edge · &gt;55% = real signal</p>
                </article>
                <article className="panel">
                  <p className="muted">Avg CLV</p>
                  <div className={(clv.overall.avg_clv ?? 0) > 0 ? "metric positive" : "metric warning"}>
                    {clv.overall.avg_clv_pct_points != null
                      ? `${clv.overall.avg_clv_pct_points > 0 ? "+" : ""}${clv.overall.avg_clv_pct_points.toFixed(2)} pp`
                      : "-"}
                  </div>
                  <p className="muted">De-vigged probability points vs the close</p>
                </article>
                <article className="panel">
                  <p className="muted">Win rate when we beat close</p>
                  <div className="metric">
                    {clv.overall.win_rate_when_beat_close != null
                      ? formatPercent(clv.overall.win_rate_when_beat_close)
                      : "-"}
                  </div>
                  <p className="muted">
                    vs {clv.overall.win_rate_when_missed_close != null
                      ? formatPercent(clv.overall.win_rate_when_missed_close)
                      : "-"}{" "}
                    when we don&apos;t — CLV predicts wins
                  </p>
                </article>
              </section>
              <table className="table">
                <thead>
                  <tr>
                    <th>Confidence</th>
                    <th>Picks</th>
                    <th>Beat close</th>
                    <th>Avg CLV</th>
                    <th>Win rate</th>
                  </tr>
                </thead>
                <tbody>
                  {(["Elite", "High", "Medium", "Low"] as const).map((tier) => {
                    const s = clv.by_confidence[tier];
                    if (!s || !s.n) return null;
                    return (
                      <tr key={tier}>
                        <td>{tier}</td>
                        <td>{s.n}</td>
                        <td className={(s.beat_close_rate ?? 0) >= 0.55 ? "positive" : ""}>
                          {s.beat_close_rate != null ? formatPercent(s.beat_close_rate) : "-"}
                        </td>
                        <td className={(s.avg_clv ?? 0) > 0 ? "positive" : "warning"}>
                          {s.avg_clv_pct_points != null
                            ? `${s.avg_clv_pct_points > 0 ? "+" : ""}${s.avg_clv_pct_points.toFixed(2)} pp`
                            : "-"}
                        </td>
                        <td>{s.win_rate != null ? formatPercent(s.win_rate) : "-"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="muted">
                Entry = each game&apos;s opening line (our board is built from morning odds); close = first-pitch
                line. Sample limited to games with both opening and closing prices on file.
              </p>
            </section>
          ) : null}

          <section className="panel">
            <div className="section-heading compact">
              <div>
                <p className="eyebrow">Confidence filter</p>
                <h2>High-Confidence Record</h2>
              </div>
              <span>{highConfidenceSummary.total} picks</span>
            </div>
            {highConfidenceSummary.total > 0 && highConfidenceSummary.accuracy !== null ? (
              <div className="grid two">
                <article>
                  <p className="muted">High + Elite hit rate</p>
                  <div className={highConfidenceSummary.accuracy >= 0.6 ? "metric positive" : "metric warning"}>
                    {formatPercent(highConfidenceSummary.accuracy)}
                  </div>
                  <p className="muted">
                    {highConfidenceSummary.wins}-{highConfidenceSummary.losses} record when market-backed or validated model-only signals reach High or Elite
                  </p>
                </article>
                <article>
                  <p className="muted">Elite-only record</p>
                  <div className={eliteConfidenceSummary.accuracy !== null && eliteConfidenceSummary.accuracy >= 0.6 ? "metric positive" : "metric warning"}>
                    {eliteConfidenceSummary.accuracy !== null ? formatPercent(eliteConfidenceSummary.accuracy) : "-"}
                  </div>
                  <p className="muted">
                    {eliteConfidenceSummary.wins}-{eliteConfidenceSummary.losses} record at 70%+ validated pick probability
                  </p>
                </article>
              </div>
            ) : (
              <p className="muted">No high-confidence prediction history is available yet.</p>
            )}
            <table className="table">
              <thead>
                <tr>
                  <th>Confidence</th>
                  <th>Record</th>
                  <th>Hit Rate</th>
                  <th>Picks</th>
                </tr>
              </thead>
              <tbody>
                {confidenceSummaries.map((summary) => (
                  <tr key={summary.confidence}>
                    <td>{summary.confidence}</td>
                    <td>{summary.wins}-{summary.losses}</td>
                    <td className={summary.accuracy !== null && summary.accuracy >= 0.6 ? "positive" : "warning"}>
                      {summary.accuracy !== null ? formatPercent(summary.accuracy) : "-"}
                    </td>
                    <td>{summary.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="panel">
            <h2>Recent Weekly Performance</h2>
            <table className="table">
              <thead>
                <tr>
                  <th>Week</th>
                  <th>Accuracy</th>
                </tr>
              </thead>
              <tbody>
                {recentWeeks.map(([week, accuracy]) => (
                  <tr key={week}>
                    <td>{week}</td>
                    <td className={accuracy >= 0.6 ? "positive" : "warning"}>{formatPercent(accuracy)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : null}

      {liveBankroll ? (
        <section className="panel strong">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Your live bankroll</p>
              <h2>{formatBankroll(liveBankroll.balance)}</h2>
            </div>
            <span>Started {liveBankroll.started_at}</span>
          </div>
          <p className="muted">
            {liveBankroll.disclaimer ?? "Tracks the Best Bets card — bet this ticket on Robinhood."}
          </p>
          <p className="muted">
            {liveBankroll.strategy} · {stakeTierLabel} · system replay <strong>{liveBankroll.record}</strong>
            {liveBankroll.prove_out?.active
              ? ` · prove-out $${liveBankroll.prove_out.flat_stake_usd} flat (${liveBankroll.prove_out.completed_tickets}/${liveBankroll.prove_out.target_tickets})`
              : ""}
          </p>
          <div className="grid">
            <article>
              <p className="muted">Started with</p>
              <div className="metric">{formatBankroll(liveBankroll.starting_balance)}</div>
              <p className="muted">Today&apos;s tracker only — not the full-season sim</p>
            </article>
            <article>
              <p className="muted">Profit / loss</p>
              <div className={liveBankroll.profit >= 0 ? "metric positive" : "metric negative"}>
                {formatBankroll(liveBankroll.profit)}
              </div>
              <p className="muted">{formatPercent(liveBankroll.return_pct)} return</p>
            </article>
            <article>
              <p className="muted">Today&apos;s stake</p>
              <div className="metric">
                {liveBankroll.today_ticket
                  ? formatBankroll(liveBankroll.today_ticket.stake_amount)
                  : "—"}
              </div>
              <p className="muted">
                {liveBankroll.today_ticket
                  ? `${ticketTypeLabel(liveBankroll.today_ticket.leg_count)} · ${formatPercent(liveBankroll.today_ticket.stake_pct)} of bankroll`
                  : "Ticket pending"}
              </p>
            </article>
          </div>
        </section>
      ) : null}

      {compoundFrom10 && strategyGuard && liveCompound?.strategy === activeStrategy ? (
        <section className="panel">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Season sim</p>
              <h2>If you started $10 on opening day</h2>
            </div>
            <span>
              {strategyGuard.period.season_start} → {strategyGuard.period.end}
            </span>
          </div>
          <p className="muted">
            Walk-forward backtest from Mar 20 — useful reference, not your live tracker above.
          </p>
          <div className="grid">
            <article>
              <p className="muted">$10 bankroll → end</p>
              <div className="metric positive">{formatBankroll(compoundFrom10.end)}</div>
              <p className="muted">
                {compoundFrom10.record} · worst dip {formatBankroll(compoundFrom10.min_bankroll)}
              </p>
            </article>
            <article>
              <p className="muted">Flat $100-per-ticket ROI (picks only)</p>
              <div className="metric positive">{formatPercent(compoundFrom10.flat_roi)}</div>
              <p className="muted">{formatBankroll(compoundFrom10.flat_profit)} on {compoundFrom10.days} tickets</p>
            </article>
            <article>
              <p className="muted">$100 bankroll → end (same stakes)</p>
              <div className="metric positive">{formatBankroll(liveCompound.from_100.end)}</div>
              <p className="muted">{liveCompound.from_100.record} at {stakeTierLabel} compound</p>
            </article>
          </div>
          {Object.keys(ticketMix).length > 0 ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Ticket type</th>
                  <th>Days</th>
                  <th>Stake %</th>
                </tr>
              </thead>
              <tbody>
                {[1, 2, 3]
                  .filter((legCount) => ticketMix[legCount])
                  .map((legCount) => (
                    <tr key={legCount}>
                      <td>{ticketTypeLabel(legCount)}</td>
                      <td>{ticketMix[legCount]}</td>
                      <td>{formatPercent(liveCompound?.stakes?.[String(legCount)] ?? 0)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          ) : null}
          <p className="muted">{strategyGuard.guard.message}</p>
        </section>
      ) : null}

      {liveBankroll && liveBankroll.checkpoints.length > 0 ? (
        <section className="panel">
          <h2>Your Daily Results</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Ticket</th>
                <th>Result</th>
                <th>Day P/L</th>
                <th>Balance</th>
                <th>Return</th>
              </tr>
            </thead>
            <tbody>
              {[...liveBankroll.checkpoints].reverse().map((checkpoint) => (
                <tr key={checkpoint.date}>
                  <td>{checkpoint.date}</td>
                  <td>{ticketTypeLabel(checkpoint.leg_count)}</td>
                  <td className={checkpoint.won ? "positive" : "negative"}>{checkpoint.won ? "Win" : "Loss"}</td>
                  <td className={checkpoint.profit >= 0 ? "positive" : "negative"}>
                    {formatBankroll(checkpoint.profit)}
                  </td>
                  <td>{formatBankroll(checkpoint.balance)}</td>
                  <td className={checkpoint.return_pct >= 0 ? "positive" : "negative"}>
                    {formatPercent(checkpoint.return_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {recentCompoundCheckpoints.length > 0 ? (
        <section className="panel">
          <h2>Season Sim — Recent Days (Mar 20 start)</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Ticket</th>
                <th>Result</th>
                <th>Day P/L</th>
                <th>Balance</th>
                <th>Return</th>
              </tr>
            </thead>
            <tbody>
              {recentCompoundCheckpoints.map((checkpoint) => (
                <tr key={checkpoint.date}>
                  <td>{checkpoint.date}</td>
                  <td>{ticketTypeLabel(checkpoint.leg_count)}</td>
                  <td className={checkpoint.won ? "positive" : "negative"}>{checkpoint.won ? "Win" : "Loss"}</td>
                  <td className={checkpoint.profit >= 0 ? "positive" : "negative"}>
                    {formatBankroll(checkpoint.profit)}
                  </td>
                  <td>{formatBankroll(checkpoint.balance)}</td>
                  <td className={checkpoint.return_pct >= 0 ? "positive" : "negative"}>
                    {formatPercent(checkpoint.return_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {liveModelPerformance ? (
        <section className="panel">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Model grading</p>
              <h2>Pick Accuracy (not bankroll)</h2>
            </div>
            <span>
              {liveModelPerformance.date_range.start} to {liveModelPerformance.date_range.end}
            </span>
          </div>
          <p className="muted">
            Retrained through {liveModelPerformance.trained_through ?? "yesterday"} · market-backed game picks only
          </p>
          <div className="grid">
            <article>
              <p className="muted">Season hit rate</p>
              <div className="metric">{formatPercent(liveModelPerformance.overall.hit_rate)}</div>
              <p className="muted">
                {liveModelPerformance.overall.wins}-{liveModelPerformance.overall.losses} on{" "}
                {liveModelPerformance.overall.bets} graded games
              </p>
            </article>
            <article>
              <p className="muted">High-confidence hit rate</p>
              <div className={liveModelPerformance.high_confidence.hit_rate >= 0.6 ? "metric positive" : "metric warning"}>
                {formatPercent(liveModelPerformance.high_confidence.hit_rate)}
              </div>
              <p className="muted">{liveModelPerformance.high_confidence.bets} High/Elite picks</p>
            </article>
          </div>
        </section>
      ) : null}

      {days.length > 0 ? (
        <section className="stack">
          {days.map((day) => (
            <article className="panel" key={day.date}>
              <div className="split">
                <div>
                  <p className="muted">Date</p>
                  <h2>{day.date}</h2>
                </div>
                <div>
                  <p className="muted">Accuracy</p>
                  <div className={day.accuracy >= 0.6 ? "metric positive" : "metric warning"}>
                    {formatPercent(day.accuracy)}
                  </div>
                  <p className="muted">{day.correct}-{day.total - day.correct} record · {day.total} games</p>
                  {day.highAccuracy !== null ? (
                    <p className={day.highAccuracy >= 0.6 ? "positive" : "warning"}>
                      High confidence: {formatPercent(day.highAccuracy)} · {day.highCorrect}-{day.highTotal - day.highCorrect}
                    </p>
                  ) : (
                    <p className="muted">No high-confidence picks</p>
                  )}
                </div>
              </div>

              {liveBankroll?.checkpoints.find((checkpoint) => checkpoint.date === day.date) ? (
                <div className="stack compact">
                  <p className="eyebrow">Your live ticket</p>
                  {(() => {
                    const checkpoint = liveBankroll.checkpoints.find((item) => item.date === day.date)!;
                    return (
                      <p className="muted">
                        {ticketTypeLabel(checkpoint.leg_count)} · {checkpoint.won ? "Win" : "Loss"} · day P/L{" "}
                        {formatBankroll(checkpoint.profit)} · balance {formatBankroll(checkpoint.balance)}
                      </p>
                    );
                  })()}
                </div>
              ) : liveCheckpointsByDate.get(day.date) ? (
                <div className="stack compact">
                  <p className="eyebrow">Live daily ticket (compound from $10)</p>
                  {(() => {
                    const checkpoint = liveCheckpointsByDate.get(day.date)!;
                    return (
                      <p className="muted">
                        {ticketTypeLabel(checkpoint.leg_count)} · {checkpoint.won ? "Win" : "Loss"} · day P/L{" "}
                        {formatBankroll(checkpoint.profit)} · balance {formatBankroll(checkpoint.balance)}
                      </p>
                    );
                  })()}
                </div>
              ) : null}

              {day.predictions.length > 0 ? (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Matchup</th>
                      <th>Pick</th>
                      <th>Probability</th>
                      <th>Confidence</th>
                      <th>Actual</th>
                      <th>Home Win %</th>
                      <th>Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {day.predictions.map((row, index) => (
                      <tr key={`${row.date}-${row.away}-${row.home}-${index}`}>
                        <td>{teamHistoryLink(row.away)} @ {teamHistoryLink(row.home)}</td>
                        <td>{teamHistoryLink(row.predicted ?? (row.probability >= 0.5 ? row.home : row.away))}</td>
                        <td>{formatPercent(row.pickProbability ?? Math.max(row.probability, 1 - row.probability))}</td>
                        <td>{row.confidence ?? "Low"}</td>
                        <td>{row.actual ?? "Unknown"}</td>
                        <td>{formatPercent(row.probability)}</td>
                        <td className={row.correct ? "positive" : "negative"}>{row.correct ? "Correct" : "Miss"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="muted">Game-level picks are not saved for this date yet. Re-run the backtest to generate full history.</p>
              )}
            </article>
          ))}
        </section>
      ) : (
        <section className="panel">
          <p>Run the model first:</p>
          <p><code>python3 scripts/model/backtest.py</code></p>
        </section>
      )}
    </main>
  );
}
