import { loadAccuracyOutput } from "@/lib/model-output";
import { formatPercent } from "@/lib/odds";

export default async function AccuracyPage() {
  const output = await loadAccuracyOutput();
  const recentWeeks = output
    ? Object.entries(output.weekly_accuracy).slice(-8)
    : [];

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Public backtesting</p>
        <h1>Model Accuracy</h1>
        <p className="lead">
          Walk-forward results from the saved model history.
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
      ) : (
        <section className="panel">
          <p>Run the model first:</p>
          <p><code>python3 scripts/model/backtest.py</code></p>
        </section>
      )}
    </main>
  );
}
