import Link from "next/link";
import { loadAccuracyOutput, loadFullPredictionHistory, loadParlayBacktest } from "@/lib/model-output";
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

export default async function HistoryPage() {
  const output = await loadAccuracyOutput();
  const fullHistory = await loadFullPredictionHistory();
  const parlayBacktest = await loadParlayBacktest();
  const parlayStrategies = parlayBacktest?.best_by_leg_count ?? [];
  const predictionRows = fullHistory.length > 0 ? fullHistory : output?.prediction_history ?? output?.recent_predictions ?? [];
  const rowsByDate = predictionRows.reduce<Record<string, typeof predictionRows>>((groups, row) => {
    groups[row.date] = [...(groups[row.date] ?? []), row];
    return groups;
  }, {});

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
      const highConfidence = sortedPredictions.filter((row) => row.confidence === "High");
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
        <p className="eyebrow">Prediction history</p>
        <h1>History</h1>
        <p className="lead">
          Daily picks, outcomes, and strategy backtests.
        </p>
      </section>

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
