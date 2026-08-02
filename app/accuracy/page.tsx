import Link from "next/link";
import {
  loadAccuracyOutput,
  loadFullPredictionHistory,
  loadLiveBankroll,
  loadLiveModelPerformance
} from "@/lib/model-output";
import { formatPercent } from "@/lib/odds";
import { normalizeTeamId, teams } from "@/lib/data";

export const dynamic = "force-dynamic";

function teamLabel(label: string) {
  const normalized = normalizeTeamId(label);
  const lower = label.toLowerCase();
  const team = teams.find(
    (item) =>
      item.id === normalized ||
      item.abbreviation.toLowerCase() === lower ||
      item.name.toLowerCase() === lower ||
      item.shortName.toLowerCase() === lower
  );
  return team?.abbreviation ?? label.toUpperCase();
}

function formatBankroll(value: number) {
  if (value >= 100) {
    return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  }
  return `$${value.toFixed(2)}`;
}

function summarize(rows: { correct: number | boolean }[]) {
  const wins = rows.filter((row) => Boolean(row.correct)).length;
  const total = rows.length;
  return {
    wins,
    losses: total - wins,
    total,
    hitRate: total > 0 ? wins / total : null
  };
}

export default async function AccuracyPage() {
  const [live, accuracy, bankroll, history] = await Promise.all([
    loadLiveModelPerformance(),
    loadAccuracyOutput(),
    loadLiveBankroll(),
    loadFullPredictionHistory()
  ]);

  const through =
    live?.trained_through ?? accuracy?.trained_through ?? live?.date_range?.end ?? null;
  const season = live?.season ?? accuracy?.season ?? "2026";

  const overall = live?.overall;
  const high = live?.high_confidence;
  const yesterday = live?.yesterday ?? null;
  const last7 = live?.last_7_days ?? accuracy?.last_7_days ?? null;

  const byConfidence = (["Elite", "High", "Medium", "Low"] as const).map((tier) => {
    const row = live?.by_confidence?.[tier];
    if (row) {
      return {
        tier,
        wins: row.wins,
        losses: row.losses,
        bets: row.bets,
        hitRate: row.hit_rate
      };
    }
    return { tier, wins: 0, losses: 0, bets: 0, hitRate: null as number | null };
  });

  const gradedTickets = [...(bankroll?.tickets ?? [])]
    .filter((ticket) => ticket.won != null)
    .reverse()
    .slice(0, 12);

  const recentDays = (() => {
    const today = new Date().toISOString().slice(0, 10);
    const cutoff = new Date(Date.now() - 14 * 86_400_000).toISOString().slice(0, 10);
    const rows = history.filter(
      (row) => row.actual && row.date >= cutoff && row.date < today && row.date.startsWith(season)
    );
    const byDate = new Map<string, typeof rows>();
    for (const row of rows) {
      const list = byDate.get(row.date) ?? [];
      list.push(row);
      byDate.set(row.date, list);
    }
    return [...byDate.entries()]
      .sort(([a], [b]) => b.localeCompare(a))
      .map(([date, dayRows]) => {
        const all = summarize(dayRows);
        const highRows = dayRows.filter(
          (row) => row.confidence === "High" || row.confidence === "Elite"
        );
        const highDay = summarize(highRows);
        return { date, all, highDay, picks: dayRows };
      });
  })();

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Model</p>
        <h1>Accuracy</h1>
        <p className="lead">
          Market-backed moneyline picks{through ? ` through ${through}` : ""}.
          {overall ? (
            <>
              {" "}
              Season <strong>{overall.wins}-{overall.losses}</strong> (
              {formatPercent(overall.hit_rate)}).
            </>
          ) : null}{" "}
          <Link href="/best-bets">Today&apos;s bet →</Link>
        </p>
      </section>

      <section className="grid">
        <article className="panel">
          <p className="muted">{season} season</p>
          <div className="metric">
            {overall ? formatPercent(overall.hit_rate) : "—"}
          </div>
          <p className="muted">
            {overall ? `${overall.wins}-${overall.losses} on ${overall.bets} games` : "No graded season yet"}
          </p>
        </article>
        <article className="panel">
          <p className="muted">High / Elite</p>
          <div
            className={
              (high?.hit_rate ?? 0) >= 0.55 ? "metric positive" : "metric warning"
            }
          >
            {high && high.bets > 0 && high.hit_rate != null ? formatPercent(high.hit_rate) : "—"}
          </div>
          <p className="muted">
            {high && high.bets > 0
              ? `${high.wins}-${high.losses} on ${high.bets} bet-lane picks`
              : "No High/Elite samples yet"}
          </p>
        </article>
        <article className="panel">
          <p className="muted">Yesterday</p>
          <div
            className={
              (yesterday?.hit_rate ?? 0) >= 0.55 ? "metric positive" : "metric warning"
            }
          >
            {yesterday && yesterday.bets > 0 && yesterday.hit_rate != null
              ? formatPercent(yesterday.hit_rate)
              : "—"}
          </div>
          <p className="muted">
            {yesterday && yesterday.bets > 0
              ? `${yesterday.wins}-${yesterday.losses} on ${yesterday.bets}`
              : "No slate graded"}
          </p>
        </article>
        <article className="panel">
          <p className="muted">Last 7 days</p>
          <div
            className={
              (last7?.hit_rate ?? 0) >= 0.55 ? "metric positive" : "metric warning"
            }
          >
            {last7 && last7.bets > 0 && last7.hit_rate != null
              ? formatPercent(last7.hit_rate)
              : "—"}
          </div>
          <p className="muted">
            {last7 && last7.bets > 0
              ? `${last7.wins}-${last7.losses} on ${last7.bets}`
              : "No recent grades"}
          </p>
        </article>
      </section>

      <section className="panel">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Breakdown</p>
            <h2>By confidence</h2>
          </div>
          <span className="muted">{season}</span>
        </div>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Confidence</th>
                <th>W-L</th>
                <th>Hit rate</th>
                <th>Picks</th>
              </tr>
            </thead>
            <tbody>
              {byConfidence.map((row) => (
                <tr key={row.tier}>
                  <td>{row.tier}</td>
                  <td>
                    {row.bets > 0 ? `${row.wins}-${row.losses}` : "—"}
                  </td>
                  <td
                    className={
                      row.hitRate != null && row.hitRate >= 0.55 ? "positive" : "warning"
                    }
                  >
                    {row.hitRate != null && row.bets > 0 ? formatPercent(row.hitRate) : "—"}
                  </td>
                  <td>{row.bets}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {bankroll ? (
        <section className="panel">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Live tickets</p>
              <h2>
                {bankroll.record}
                {bankroll.hit_rate != null ? ` · ${formatPercent(bankroll.hit_rate)}` : ""}
              </h2>
            </div>
            <span className="muted">{formatBankroll(bankroll.wallet_balance ?? bankroll.balance)}</span>
          </div>
          <p className="muted">
            Graded daily tickets only — not every board pick.{" "}
            <Link href="/best-bets">Moneyline →</Link>
          </p>
          {gradedTickets.length > 0 ? (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Ticket</th>
                    <th>Result</th>
                    <th className="hide-sm">P/L</th>
                  </tr>
                </thead>
                <tbody>
                  {gradedTickets.map((ticket) => (
                    <tr key={`${ticket.date}-${ticket.label}`}>
                      <td>{ticket.date}</td>
                      <td>
                        <strong>{ticket.label}</strong>
                      </td>
                      <td className={ticket.won ? "positive" : "warning"}>
                        {ticket.won ? "WIN" : "LOSS"}
                      </td>
                      <td className="hide-sm">
                        {ticket.profit != null
                          ? formatBankroll(ticket.profit)
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted">No graded live tickets yet.</p>
          )}
        </section>
      ) : null}

      <section className="panel">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Recent slates</p>
            <h2>Last 14 days</h2>
          </div>
          <span className="muted">{recentDays.length} days</span>
        </div>
        {recentDays.length > 0 ? (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>W-L</th>
                  <th>Hit rate</th>
                  <th className="hide-sm">High / Elite</th>
                  <th className="hide-sm">Sample picks</th>
                </tr>
              </thead>
              <tbody>
                {recentDays.map((day) => (
                  <tr key={day.date}>
                    <td>{day.date}</td>
                    <td>
                      {day.all.wins}-{day.all.losses}
                    </td>
                    <td
                      className={
                        day.all.hitRate != null && day.all.hitRate >= 0.55
                          ? "positive"
                          : "warning"
                      }
                    >
                      {day.all.hitRate != null ? formatPercent(day.all.hitRate) : "—"}
                    </td>
                    <td className="hide-sm">
                      {day.highDay.total > 0
                        ? `${day.highDay.wins}-${day.highDay.losses}`
                        : "—"}
                    </td>
                    <td className="hide-sm muted">
                      {day.picks
                        .slice(0, 4)
                        .map((pick) => {
                          const side = pick.predicted ?? (pick.probability >= 0.5 ? pick.home : pick.away);
                          return `${teamLabel(side)}${pick.correct ? "✓" : "✗"}`;
                        })
                        .join(" · ")}
                      {day.picks.length > 4 ? ` · +${day.picks.length - 4}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">No graded slates in the last two weeks.</p>
        )}
      </section>
    </main>
  );
}
