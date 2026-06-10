import Link from "next/link";
import {
  getAdvancedBets,
  getBacktestedParlaysByLegCount,
  getBestBets,
  getBestParlaysByLegCount
} from "@/lib/data";
import { loadParlayBacktest, loadPredictionBoard } from "@/lib/model-output";
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
  const parlayBacktest = await loadParlayBacktest();
  const singleStrategy = parlayBacktest?.recommended_single_strategy;
  const oddsMetadata = parlayBacktest?.odds_metadata;
  const recommendedStrategies = parlayBacktest?.recommended_by_leg_count ?? [];
  const parlays = recommendedStrategies.length > 0
    ? getBacktestedParlaysByLegCount(board, recommendedStrategies)
    : getBestParlaysByLegCount(board);
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

      <section className="panel">
        <h2>Moneyline Best Bets</h2>
        {singleStrategy ? (
          <p className="muted">
            Moneyline filter backtest: {singleStrategy.bets} bets, {singleStrategy.wins}-{singleStrategy.losses} record,{" "}
            {formatPercent(singleStrategy.roi)} ROI. Requires {formatPercent(singleStrategy.min_probability)}+ model
            probability, {formatPercent(singleStrategy.min_edge)}+ edge, and odds no longer than ±
            {singleStrategy.max_abs_odds}.
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
        <h2>Safer Parlay Candidates</h2>
        {parlayBacktest ? (
          <p className="muted">
            Strategy backtest: {parlayBacktest.model_prediction_rows} predictions, {parlayBacktest.date_range.start} to{" "}
            {parlayBacktest.date_range.end}. Parlays require at least two legs, 60%+ model probability,
            near-favorite market pricing, positive ROI, and a 50%+ historical hit rate.
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
            No parlay ticket cleared today&apos;s safety filter. The page needs at least two qualifying legs on different
            games.
          </p>
        )}
      </section>

      <section className="panel">
        <h2>Advanced Markets</h2>
        <p className="muted">
          Run line and totals are separated from moneyline until their backtests are deeper.
        </p>
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
