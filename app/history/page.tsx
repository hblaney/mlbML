import Link from "next/link";
import {
  loadAccuracyOutput,
  loadFullPredictionHistory,
  loadParlayBacktest,
  loadRecommendationPerformance,
  type DailyRecommendationSnapshot,
  type RecommendationSummary
} from "@/lib/model-output";
import { formatOdds, formatPercent } from "@/lib/odds";
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

function recommendationByDate(daily: DailyRecommendationSnapshot[]) {
  return new Map(daily.map((snapshot) => [snapshot.date, snapshot]));
}

function categoryLabel(category: string) {
  if (category === "moneyline") {
    return "Moneyline";
  }
  if (category === "advanced") {
    return "Advanced";
  }
  if (category === "parlay_3") {
    return "3-Leg Parlay";
  }
  if (category === "parlay_4") {
    return "4-Leg Parlay";
  }
  return category;
}

export default async function HistoryPage() {
  const output = await loadAccuracyOutput();
  const fullHistory = await loadFullPredictionHistory();
  const parlayBacktest = await loadParlayBacktest();
  const recommendationPerformance = await loadRecommendationPerformance();
  const parlayStrategies = parlayBacktest?.best_by_leg_count ?? [];
  const recentWeeks = output ? Object.entries(output.weekly_accuracy).slice(-8) : [];
  const predictionRows = fullHistory.length > 0 ? fullHistory : output?.prediction_history ?? output?.recent_predictions ?? [];
  const eliteConfidenceRows = predictionRows.filter((row) => row.confidence === "Elite");
  const eliteConfidenceSummary = summarizeRows(eliteConfidenceRows);
  const highConfidenceRows = predictionRows.filter((row) => row.confidence === "High" || row.confidence === "Elite");
  const highConfidenceSummary = summarizeRows(highConfidenceRows);
  const confidenceSummaries = (["Elite", "High", "Medium", "Low"] as const).map((confidence) => ({
    confidence,
    ...summarizeRows(predictionRows.filter((row) => row.confidence === confidence))
  }));
  const rowsByDate = predictionRows.reduce<Record<string, typeof predictionRows>>((groups, row) => {
    groups[row.date] = [...(groups[row.date] ?? []), row];
    return groups;
  }, {});

  const recommendationDays = recommendationByDate(recommendationPerformance?.daily ?? []);
  const recentRecommendationWeeks = recommendationPerformance
    ? Object.entries(recommendationPerformance.weekly).slice(-8)
    : [];
  const recentRecommendationMonths = recommendationPerformance
    ? Object.entries(recommendationPerformance.monthly).slice(-6)
    : [];
  const recentCheckpoints = recommendationPerformance?.checkpoints.slice(-12).reverse() ?? [];

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
          Model accuracy, daily picks, outcomes, and strategy backtests.
        </p>
      </section>

      {output ? (
        <>
          <section className="grid">
            <article className="panel">
              <p className="muted">Overall</p>
              <div className="metric">{formatPercent(output.overall_accuracy)}</div>
              <p>{output.evaluated_games.toFixed(0)} games evaluated</p>
            </article>
            <article className="panel">
              <p className="muted">Days at 60%+</p>
              <div className="metric">{output.days_at_or_above_60pct.toFixed(0)}</div>
              <p className="muted">Daily hit-rate buckets</p>
            </article>
            <article className="panel">
              <p className="muted">Weeks at 60%+</p>
              <div className="metric">{output.weeks_at_or_above_60pct.toFixed(0)}</div>
              <p className="muted">Weekly hit-rate buckets</p>
            </article>
          </section>

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

      {recommendationPerformance ? (
        <>
          <section className="panel">
            <div className="section-heading compact">
              <div>
                <p className="eyebrow">Model paper portfolio</p>
                <h2>Recommended Bet Profitability</h2>
              </div>
              <span>
                {recommendationPerformance.date_range.start} to {recommendationPerformance.date_range.end}
              </span>
            </div>
            <div className="grid">
              <article>
                <p className="muted">Paper Balance</p>
                <div className={recommendationPerformance.cumulative.return_pct >= 0 ? "metric positive" : "metric negative"}>
                  {currency(recommendationPerformance.cumulative.balance)}
                </div>
                <p className="muted">
                  Started at {currency(recommendationPerformance.starting_bankroll)} · {currency(recommendationPerformance.cumulative.profit)} P/L
                </p>
              </article>
              <article>
                <p className="muted">Portfolio ROI</p>
                <div className={recommendationPerformance.cumulative.roi >= 0 ? "metric positive" : "metric negative"}>
                  {formatPercent(recommendationPerformance.cumulative.roi)}
                </div>
                <p className="muted">{recommendationPerformance.cumulative.bets} paper tickets at {currency(recommendationPerformance.stake)} each</p>
              </article>
              <article>
                <p className="muted">Daily Tickets</p>
                <div className="metric">{recommendationPerformance.daily.length}</div>
                <p className="muted">Moneyline, advanced, and 3-4 leg parlays per slate day</p>
              </article>
            </div>
          </section>

          <section className="panel">
            <h2>Strategy Track Record</h2>
            <table className="table">
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th>Record</th>
                  <th>Hit Rate</th>
                  <th>ROI</th>
                  <th>Profit</th>
                  <th>Tickets</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(recommendationPerformance.by_category).map(([category, summary]: [string, RecommendationSummary]) => (
                  <tr key={category}>
                    <td>{categoryLabel(category)}</td>
                    <td>{summary.wins}-{summary.losses}</td>
                    <td>{formatPercent(summary.hit_rate)}</td>
                    <td className={summary.roi > 0 ? "positive" : "negative"}>{formatPercent(summary.roi)}</td>
                    <td className={summary.profit > 0 ? "positive" : "negative"}>{currency(summary.profit)}</td>
                    <td>{summary.bets}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {recentCheckpoints.length > 0 ? (
            <section className="panel">
              <h2>Model Bankroll Curve</h2>
              <table className="table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Daily P/L</th>
                    <th>Balance</th>
                    <th>Return</th>
                  </tr>
                </thead>
                <tbody>
                  {recentCheckpoints.map((checkpoint) => (
                    <tr key={checkpoint.date}>
                      <td>{checkpoint.date}</td>
                      <td className={checkpoint.profit >= 0 ? "positive" : "negative"}>{currency(checkpoint.profit)}</td>
                      <td>{currency(checkpoint.balance)}</td>
                      <td className={checkpoint.return_pct >= 0 ? "positive" : "negative"}>{formatPercent(checkpoint.return_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ) : null}

          {recentRecommendationWeeks.length > 0 ? (
            <section className="panel">
              <h2>Weekly Paper P/L</h2>
              <table className="table">
                <thead>
                  <tr>
                    <th>Week</th>
                    <th>Record</th>
                    <th>ROI</th>
                    <th>Profit</th>
                  </tr>
                </thead>
                <tbody>
                  {recentRecommendationWeeks.map(([week, summary]) => (
                    <tr key={week}>
                      <td>{week}</td>
                      <td>{summary.wins}-{summary.losses}</td>
                      <td className={summary.roi > 0 ? "positive" : "negative"}>{formatPercent(summary.roi)}</td>
                      <td className={summary.profit > 0 ? "positive" : "negative"}>{currency(summary.profit)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ) : null}

          {recentRecommendationMonths.length > 0 ? (
            <section className="panel">
              <h2>Monthly Paper P/L</h2>
              <table className="table">
                <thead>
                  <tr>
                    <th>Month</th>
                    <th>Record</th>
                    <th>ROI</th>
                    <th>Profit</th>
                  </tr>
                </thead>
                <tbody>
                  {recentRecommendationMonths.map(([month, summary]) => (
                    <tr key={month}>
                      <td>{month}</td>
                      <td>{summary.wins}-{summary.losses}</td>
                      <td className={summary.roi > 0 ? "positive" : "negative"}>{formatPercent(summary.roi)}</td>
                      <td className={summary.profit > 0 ? "positive" : "negative"}>{currency(summary.profit)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ) : null}
        </>
      ) : null}

      {parlayStrategies.length > 0 ? (
        <section className="panel">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Strategy validation</p>
              <h2>Parlay Backtest</h2>
            </div>
            <span>{parlayBacktest?.date_range.start} to {parlayBacktest?.date_range.end}</span>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>Legs</th>
                <th>Record</th>
                <th>Hit Rate</th>
                <th>ROI</th>
                <th>Profit</th>
                <th>Rule</th>
              </tr>
            </thead>
            <tbody>
              {parlayStrategies.map((strategy) => (
                <tr key={`${strategy.leg_count}-${strategy.min_edge}-${strategy.min_probability}-${strategy.top_n}`}>
                  <td>{strategy.leg_count}</td>
                  <td>{strategy.wins}-{strategy.losses}</td>
                  <td>{formatPercent(strategy.hit_rate)}</td>
                  <td className={strategy.roi > 0 ? "positive" : "negative"}>{formatPercent(strategy.roi)}</td>
                  <td className={strategy.profit > 0 ? "positive" : "negative"}>${strategy.profit.toFixed(2)}</td>
                  <td>
                    edge ≥ {formatPercent(strategy.min_edge)}, model ≥ {formatPercent(strategy.min_probability)}, top {strategy.top_n}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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

              {recommendationDays.get(day.date) ? (
                <div className="stack compact">
                  <p className="eyebrow">Recommended paper bets</p>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Strategy</th>
                        <th>Pick</th>
                        <th>Odds</th>
                        <th>Model</th>
                        <th>Result</th>
                        <th>P/L</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recommendationDays.get(day.date)?.bets.map((bet) => (
                        <tr key={`${day.date}-${bet.category}-${bet.label}`}>
                          <td>{categoryLabel(bet.category)}</td>
                          <td>
                            <strong>{bet.label}</strong>
                            <p className="muted">{bet.matchup}</p>
                            {!bet.qualified ? <p className="muted">Best available · below strict filter</p> : null}
                          </td>
                          <td>{formatOdds(bet.odds)}</td>
                          <td>{formatPercent(bet.model_probability)}</td>
                          <td className={bet.won ? "positive" : "negative"}>{bet.won ? "Win" : "Loss"}</td>
                          <td className={bet.profit >= 0 ? "positive" : "negative"}>{currency(bet.profit)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="muted">
                    Day paper P/L: {currency(recommendationDays.get(day.date)?.summary.profit ?? 0)} ·{" "}
                    {formatPercent(recommendationDays.get(day.date)?.summary.roi ?? 0)} ROI
                  </p>
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
