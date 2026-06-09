import Link from "next/link";
import {
  getAdvancedBets,
  getBacktestedParlaysByLegCount,
  getBestBets,
  getBestParlaysByLegCount
} from "@/lib/data";
import { loadParlayBacktest, loadPredictionBoard } from "@/lib/model-output";
import { formatOdds, formatPercent } from "@/lib/odds";
import { formatStandingRecord, loadLiveStandings } from "@/lib/standings";
import { formatCentralGameTime } from "@/lib/time";

export const dynamic = "force-dynamic";

export default async function BestBetsPage() {
  const board = await loadPredictionBoard();
  const standings = await loadLiveStandings();
  const standingsByTeamId = new Map(standings.map((standing) => [standing.teamId, standing]));
  const bets = getBestBets(board);
  const advancedBets = getAdvancedBets(board);
  const parlayBacktest = await loadParlayBacktest();
  const recommendedStrategies = parlayBacktest?.recommended_by_leg_count ?? [];
  const parlays = recommendedStrategies.length > 0
    ? getBacktestedParlaysByLegCount(board, recommendedStrategies)
    : getBestParlaysByLegCount(board);
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
      <section className="panel strong">
        <p className="eyebrow">Positive expected value</p>
        <h1>Best Bets</h1>
        <p className="lead">
          Market prices where the model and sportsbook disagree.
        </p>
      </section>

      <section className="panel">
        <h2>Moneyline Edges</h2>
        {bets.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Matchup / Side</th>
                <th>Odds</th>
                <th>Model</th>
                <th>Book</th>
                <th>Edge</th>
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
          <p className="muted">No positive moneyline edges with live odds right now.</p>
        )}
      </section>

      <section className="panel">
        <h2>Safer Parlay Candidates</h2>
        {parlayBacktest ? (
          <p className="muted">
            Strategy backtest: {parlayBacktest.model_prediction_rows} predictions, {parlayBacktest.date_range.start} to{" "}
            {parlayBacktest.date_range.end}. Parlays require at least two legs, 60%+ model probability, and
            near-favorite market pricing for each leg.
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
            No safer parlay candidates passed today&apos;s filter. Medium-confidence value plays can still show as singles,
            but they will not be forced into the parlay section.
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
