import Link from "next/link";
import {
  getAdvancedBets,
  getBestBets,
  getBestDailyTicket,
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
  const bestTicket = getBestDailyTicket(board);
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

      {bestTicket ? (
        <section className="panel strong">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Best ticket today</p>
              <h2>
                {bestTicket.kind === "single"
                  ? `${bestTicket.bet.team.abbreviation} ML`
                  : `${bestTicket.parlay.legCount}-Leg Parlay`}
              </h2>
            </div>
            <span>{bestTicket.qualified ? "Qualified ROI pick" : "Best available ROI pick"}</span>
          </div>
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
                <p className="muted">Ticket math</p>
                <div className="metric">{formatOdds(bestTicket.bet.odds)}</div>
                <p className="muted">
                  Model {formatPercent(bestTicket.bet.modelProbability)} · Edge {formatPercent(bestTicket.bet.edge)} · EV
                  ${bestTicket.bet.ev.toFixed(2)} / $100
                </p>
              </article>
            </div>
          ) : (
            <div className="stack">
              <p className="muted">
                {bestTicket.parlay.strategy === "anchor"
                  ? "Anchor ticket: one edge leg paired with one High/Elite confidence leg."
                  : bestTicket.parlay.strategy === "premium"
                    ? "Premium 3-leg ticket: only shown when the model is very confident across multiple qualified legs."
                    : "Edge ticket: both legs clear the qualified parlay filters."}
              </p>
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
                Combined {formatPercent(bestTicket.parlay.probability)} at {formatOdds(bestTicket.parlay.americanOdds)} · EV
                ${bestTicket.parlay.ev.toFixed(2)} / $100
              </p>
            </div>
          )}
        </section>
      ) : (
        <section className="panel">
          <h2>Best Ticket Today</h2>
          <p className="muted">No positive-EV single or parlay ticket cleared today&apos;s filters. Sitting out is valid.</p>
        </section>
      )}

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
              <p className="muted">2-Leg Parlays</p>
              <div className="metric">
                {recommendationPerformance.by_category.parlay_2
                  ? formatPercent(recommendationPerformance.by_category.parlay_2.roi)
                  : "-"}
              </div>
              <p className="muted">
                {recommendationPerformance.by_category.parlay_2
                  ? `${recommendationPerformance.by_category.parlay_2.wins}-${recommendationPerformance.by_category.parlay_2.losses} record`
                  : "No history"}
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
        <h2>Daily 2-Leg Parlays</h2>
        {recommendationPerformance ? (
          <p className="muted">
            Historical daily parlay ledger: 2-leg {recommendationPerformance.by_category.parlay_2?.wins ?? 0}-
            {recommendationPerformance.by_category.parlay_2?.losses ?? 0} (
            {formatPercent(recommendationPerformance.by_category.parlay_2?.roi ?? 0)} ROI).
            Anchor tickets pair one edge leg with one High/Elite confidence leg when the combined parlay stays positive EV.
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
                    {parlay.strategy === "anchor" ? (
                      <p className="muted">Anchor parlay · edge leg plus High/Elite confidence leg</p>
                    ) : parlay.strategy === "premium" ? (
                      <p className="muted">Premium 3-leg parlay · very high combined confidence</p>
                    ) : (
                      <p className="muted">Edge parlay · every leg clears standalone edge filter</p>
                    )}
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
            No alternate parlay ticket cleared today&apos;s filters. Use the Best Ticket section above for the top ROI play.
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
