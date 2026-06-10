import Link from "next/link";
import {
  getAdvancedBets,
  getBestBets,
  getDailyParlayTickets
} from "@/lib/data";
import { loadParlayBacktest, loadPredictionBoard, loadRecommendationPerformance } from "@/lib/model-output";
import { decimalOdds, formatOdds, formatPercent } from "@/lib/odds";
import { formatStandingRecord, loadLiveStandings } from "@/lib/standings";
import { formatCentralGameTime } from "@/lib/time";

export const dynamic = "force-dynamic";

export default async function BestBetsPage() {
  const board = await loadPredictionBoard();
  const standings = await loadLiveStandings();
  const standingsByTeamId = new Map(standings.map((standing) => [standing.teamId, standing]));
  const bets = getBestBets(board);
  const advancedBets = getAdvancedBets(board);
  const usingModelOnlyPicks = bets.some((bet) => bet.modelOnly) || advancedBets.some((bet) => bet.modelOnly);
  const [parlayBacktest, recommendationPerformance] = await Promise.all([
    loadParlayBacktest(),
    loadRecommendationPerformance()
  ]);
  const oddsMetadata = parlayBacktest?.odds_metadata ?? recommendationPerformance?.odds_metadata;
  const parlays = getDailyParlayTickets(board);
  const topMoneylineBet = getBestBets(board)[0] ?? null;
  const topAdvancedBet = getAdvancedBets(board)[0] ?? null;
  const recordFor = (teamId: string) => formatStandingRecord(standingsByTeamId.get(teamId));
  const profitForStake = (odds: number, stake = 100) => (decimalOdds(odds) - 1) * stake;
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
        <p className="eyebrow">Qualified betting edges</p>
        <h1>Best Bets</h1>
        <p className="lead">
          Qualified edges first, followed by the best available positive model edges when the slate does not clear the
          stricter backtested filter.
        </p>
        {oddsMetadata?.odds_data_stale ? (
          <p className="muted">
            ROI backtests are limited by imported historical odds through {oddsMetadata.odds_data_end}. Today&apos;s board
            still uses live odds, but profit validation needs newer historical odds imported to include recent games.
          </p>
        ) : null}
        {usingModelOnlyPicks ? (
          <p className="muted">
            Live sportsbook odds aren&apos;t on today&apos;s board, so picks below use model win rates and standard
            reference pricing (-110 / 8.5 total) instead of market EV.
          </p>
        ) : null}
      </section>

      {recommendationPerformance ? (
        <section className="panel">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Historical track record</p>
              <h2>Model Paper Portfolio</h2>
            </div>
            <span>
              {recommendationPerformance.date_range.start} to {recommendationPerformance.date_range.end}
            </span>
          </div>
          <div className="grid">
            <article>
              <p className="muted">Portfolio ROI</p>
              <div className={recommendationPerformance.cumulative.roi >= 0 ? "metric positive" : "metric negative"}>
                {formatPercent(recommendationPerformance.cumulative.roi)}
              </div>
              <p className="muted">
                ${recommendationPerformance.cumulative.profit.toFixed(2)} on {recommendationPerformance.cumulative.bets} tickets
              </p>
            </article>
            <article>
              <p className="muted">Daily Moneyline</p>
              <div className="metric">
                {recommendationPerformance.by_category.moneyline
                  ? formatPercent(recommendationPerformance.by_category.moneyline.roi)
                  : "-"}
              </div>
              <p className="muted">
                {recommendationPerformance.by_category.moneyline
                  ? `${recommendationPerformance.by_category.moneyline.wins}-${recommendationPerformance.by_category.moneyline.losses} record`
                  : "No history"}
              </p>
            </article>
            <article>
              <p className="muted">Daily Advanced</p>
              <div className="metric">
                {recommendationPerformance.by_category.advanced
                  ? formatPercent(recommendationPerformance.by_category.advanced.roi)
                  : "-"}
              </div>
              <p className="muted">
                {recommendationPerformance.by_category.advanced
                  ? `${recommendationPerformance.by_category.advanced.wins}-${recommendationPerformance.by_category.advanced.losses} record`
                  : "No history"}
              </p>
            </article>
            <article>
              <p className="muted">3-4 Leg Parlays</p>
              <div className="metric">
                {recommendationPerformance.by_category.parlay_3 || recommendationPerformance.by_category.parlay_4
                  ? formatPercent(
                      ((recommendationPerformance.by_category.parlay_3?.profit ?? 0) +
                        (recommendationPerformance.by_category.parlay_4?.profit ?? 0)) /
                        Math.max(
                          ((recommendationPerformance.by_category.parlay_3?.bets ?? 0) +
                            (recommendationPerformance.by_category.parlay_4?.bets ?? 0)) *
                            recommendationPerformance.stake,
                          1
                        )
                    )
                  : "-"}
              </div>
              <p className="muted">
                3-leg: {recommendationPerformance.by_category.parlay_3?.wins ?? 0}-
                {recommendationPerformance.by_category.parlay_3?.losses ?? 0} · 4-leg:{" "}
                {recommendationPerformance.by_category.parlay_4?.wins ?? 0}-
                {recommendationPerformance.by_category.parlay_4?.losses ?? 0}
              </p>
            </article>
          </div>
        </section>
      ) : null}

      <section className="panel">
        <h2>Moneyline Best Bets</h2>
        {recommendationPerformance?.by_category.moneyline ? (
          <p className="muted">
            Daily moneyline track record: {recommendationPerformance.by_category.moneyline.bets} tickets,{" "}
            {recommendationPerformance.by_category.moneyline.wins}-{recommendationPerformance.by_category.moneyline.losses}{" "}
            record, {formatPercent(recommendationPerformance.by_category.moneyline.roi)} ROI.
            {topMoneylineBet?.qualified ? " Today&apos;s top pick clears the qualified filter." : " Today&apos;s top pick is the best available edge."}
          </p>
        ) : null}
        {bets.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Matchup / Side</th>
                <th>Odds</th>
                <th>Model</th>
                <th>Book</th>
                <th>Edge</th>
                <th>Wins / $100</th>
                <th>EV / $100</th>
              </tr>
            </thead>
            <tbody>
              {bets.map((bet) => (
                <tr key={bet.id}>
                  <td>
                    <strong>{bet.matchup}</strong>
                    <p>
                      {teamLink(bet.team)} ({recordFor(bet.team.id)}) {bet.side} vs {teamLink(bet.opponent)} (
                      {recordFor(bet.opponent.id)})
                    </p>
                    <p className="muted">{formatCentralGameTime(bet.game.startsAt)}</p>
                    {bet.qualified ? <p className="muted">Qualified edge · clears backtested filter</p> : null}
                    {!bet.qualified && !bet.modelOnly ? <p className="muted">Best available edge · below strict filter</p> : null}
                    {bet.modelOnly ? <p className="muted">Model pick · fair line shown</p> : null}
                  </td>
                  <td>{formatOdds(bet.odds)}</td>
                  <td>{formatPercent(bet.modelProbability)}</td>
                  <td>{formatPercent(bet.bookProbability)}</td>
                  <td className={bet.edge > 0 ? "positive" : "warning"}>{formatPercent(bet.edge)}</td>
                  <td className="positive">${profitForStake(bet.odds).toFixed(2)}</td>
                  <td className={bet.ev > 0 ? "positive" : "negative"}>${bet.ev.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">
            No moneyline edges are available yet. Check back after live odds are loaded or tomorrow&apos;s board drops.
          </p>
        )}
      </section>

      <section className="panel">
        <h2>Daily 3-4 Leg Parlays</h2>
        {recommendationPerformance ? (
          <p className="muted">
            Historical daily parlay ledger: 3-leg {recommendationPerformance.by_category.parlay_3?.wins ?? 0}-
            {recommendationPerformance.by_category.parlay_3?.losses ?? 0} (
            {formatPercent(recommendationPerformance.by_category.parlay_3?.roi ?? 0)} ROI), 4-leg{" "}
            {recommendationPerformance.by_category.parlay_4?.wins ?? 0}-
            {recommendationPerformance.by_category.parlay_4?.losses ?? 0} (
            {formatPercent(recommendationPerformance.by_category.parlay_4?.roi ?? 0)} ROI).
          </p>
        ) : null}
        {parlays.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Legs</th>
                <th>Ticket</th>
                <th>Probability</th>
                <th>Odds</th>
                <th>Profit / $100</th>
                <th>EV / $100</th>
              </tr>
            </thead>
            <tbody>
              {parlays.map((parlay) => (
                <tr key={parlay.id}>
                  <td>{parlay.legCount}</td>
                  <td>
                    {parlay.legs.map((leg) => (
                      <p key={leg.id}>
                        <strong>{teamAbbrevLink(leg.team)} ML</strong> ({recordFor(leg.team.id)}) vs{" "}
                        {teamAbbrevLink(leg.opponent)} ({recordFor(leg.opponent.id)}) · {leg.matchup} ·{" "}
                        {formatOdds(leg.odds)} · {formatPercent(leg.modelProbability)}
                      </p>
                    ))}
                  </td>
                  <td>{formatPercent(parlay.probability)}</td>
                  <td>{formatOdds(parlay.americanOdds)}</td>
                  <td className="positive">${parlay.payoutProfit.toFixed(2)}</td>
                  <td className={parlay.ev > 0 ? "positive" : "negative"}>${parlay.ev.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">
            No 3- or 4-leg parlay ticket is available yet. The page needs enough qualifying legs on different games.
          </p>
        )}
      </section>

      <section className="panel">
        <h2>Advanced Markets</h2>
        {recommendationPerformance?.by_category.advanced ? (
          <p className="muted">
            Daily totals track record: {recommendationPerformance.by_category.advanced.bets} tickets,{" "}
            {recommendationPerformance.by_category.advanced.wins}-{recommendationPerformance.by_category.advanced.losses}{" "}
            record, {formatPercent(recommendationPerformance.by_category.advanced.roi)} ROI.
            {topAdvancedBet ? " Today&apos;s top advanced pick is shown below." : ""}
          </p>
        ) : (
          <p className="muted">Run line and totals are separated from moneyline. Historical totals backtests are shown above when available.</p>
        )}
        {advancedBets.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Market</th>
                <th>Matchup / Pick</th>
                <th>Odds</th>
                <th>Model</th>
                <th>Book</th>
                <th>Edge</th>
                <th>EV / $100</th>
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
                    {bet.market === "Total" ? (
                      <p className="muted">Projected total: {bet.game.projectedTotal?.toFixed(1)}</p>
                    ) : null}
                    {bet.modelOnly ? <p className="muted">Model lean · reference line</p> : null}
                  </td>
                  <td>{formatOdds(bet.odds)}</td>
                  <td>{formatPercent(bet.modelProbability)}</td>
                  <td>{formatPercent(bet.bookProbability)}</td>
                  <td className="positive">{formatPercent(bet.edge)}</td>
                  <td className={bet.ev > 0 ? "positive" : "negative"}>${bet.ev.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">No positive-EV run line or totals picks passed today&apos;s advanced-market filters.</p>
        )}
      </section>

    </main>
  );
}
