import { getAdvancedBets, getBacktestedParlaysByLegCount, getBestBets, getBestParlaysByLegCount } from "@/lib/data";
import { loadParlayBacktest, loadPredictionBoard } from "@/lib/model-output";
import { formatOdds, formatPercent } from "@/lib/odds";

export const dynamic = "force-dynamic";

export default async function BestBetsPage() {
  const board = await loadPredictionBoard();
  const bets = getBestBets(board);
  const advancedBets = getAdvancedBets(board);
  const parlayBacktest = await loadParlayBacktest();
  const backtestedStrategies = parlayBacktest?.best_by_leg_count ?? [];
  const recommendedStrategies = parlayBacktest?.recommended_by_leg_count ?? [];
  const parlays = recommendedStrategies.length > 0
    ? getBacktestedParlaysByLegCount(board, recommendedStrategies)
    : getBestParlaysByLegCount(board);

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Positive expected value</p>
        <h1>Best Bets</h1>
        <p className="lead">
          These are not simply the most likely winners. They are sides where the model probability is higher than
          the sportsbook implied probability from a real market feed.
        </p>
        <p className="muted">
          Betting content is informational only. If live odds are unavailable, this page will not invent prices.
        </p>
      </section>

      <section className="panel">
        <h2>Recommended Parlays</h2>
        <p className="muted">
          These use historically profitable strategy settings with enough samples when a parlay backtest is available.
          Parlays assume independent game outcomes, so treat them as a risk/reward screen, not a guarantee.
        </p>
        {parlayBacktest ? (
          <p className="muted">
            Backtested on {parlayBacktest.model_prediction_rows} predictions from {parlayBacktest.date_range.start} to{" "}
            {parlayBacktest.date_range.end}.
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
                        <strong>{leg.team.abbreviation} ML</strong> vs {leg.opponent.abbreviation} · {leg.matchup} ·{" "}
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
          <p className="muted">No positive-EV parlay candidates found from today&apos;s real-odds board.</p>
        )}
      </section>

      {backtestedStrategies.length > 0 ? (
        <section className="panel">
          <h2>Parlay Strategy Backtest</h2>
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
              {backtestedStrategies.map((strategy) => (
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

      <section className="panel">
        <h2>Advanced Markets</h2>
        <p className="muted">
          Experimental run line and totals picks using real odds. Moneyline remains separated below because these markets
          need their own deeper backtests before they should drive staking.
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
                    <strong>{bet.matchup}</strong>
                    <p>{bet.label}</p>
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
                    <p>{bet.team.name} {bet.side} vs {bet.opponent.name}</p>
                    <p className="muted">{new Date(bet.game.startsAt).toLocaleString()}</p>
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
          <p className="muted">
            No positive-edge bets are available because no real moneyline odds were found. Add an `ODDS_API_KEY` or another
            live odds provider before trusting EV or best-bet calculations.
          </p>
        )}
      </section>
    </main>
  );
}
