import Link from "next/link";
import {
  getAdvancedBets,
  getBestBets,
  getBestDailyTicket,
  getAlwaysTwoLegParlay,
  getDailyParlayTickets,
  getOptimizedStakePctForTicket,
  OPTIMIZED_GROWTH_STAKE_PCT,
  OPTIMIZED_STAKE_BY_LEG_COUNT
} from "@/lib/data";
import { loadPredictionBoard, loadRecommendationPerformance, loadStrategyBacktestResults, loadExhaustiveStrategySearch, loadOosStrategyValidation, loadBettingPlan } from "@/lib/model-output";
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
  const [recommendationPerformance, strategyBacktest, exhaustiveSearch, oosValidation, bettingPlan] = await Promise.all([
    loadRecommendationPerformance(),
    loadStrategyBacktestResults(),
    loadExhaustiveStrategySearch(),
    loadOosStrategyValidation(),
    loadBettingPlan()
  ]);
  const stakeByLeg = bettingPlan?.stake_by_leg_count;
  const oddsMetadata = strategyBacktest?.odds_metadata ?? recommendationPerformance?.odds_metadata;
  const parlays = getDailyParlayTickets(board);
  const bestTicket = getBestDailyTicket(board);
  const ticketStakePct = getOptimizedStakePctForTicket(bestTicket, stakeByLeg);
  const growthParlay = getAlwaysTwoLegParlay(board);
  const formatBankroll = (value: number) =>
    value >= 100
      ? `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
      : `$${value.toFixed(2)}`;
  const backtest10k = strategyBacktest?.winners_by_bankroll["10000.0"] ?? [];
  const backtest10 = strategyBacktest?.winners_by_bankroll["10.0"] ?? [];
  const winner = exhaustiveSearch?.recommendation.one_bet_per_day_fair ?? strategyBacktest?.recommended_summary;
  const fairTop = exhaustiveSearch?.top_fair_10k ?? [];
  const winnerEnd =
    winner && "end" in winner ? winner.end : winner && "end_bankroll" in winner ? winner.end_bankroll : 0;
  const winnerRecord =
    winner && "wins" in winner
      ? `${winner.wins}-${winner.losses}`
      : winner && "record" in winner
        ? winner.record
        : "";
  const winnerLabel =
    winner && "strategy_id" in winner
      ? winner.strategy_id
      : winner && "mode" in winner
        ? winner.mode
        : "";
  const winnerBets = winner && ("days" in winner ? winner.days : "bets" in winner ? winner.bets : 0);
  const winnerMin =
    winner && "min_bankroll" in winner ? winner.min_bankroll : 0;
  const winnerStake =
    winner && "stake_pct" in winner
      ? winner.stake_pct
      : winner && "optimal_stake_pct" in winner
        ? winner.optimal_stake_pct
        : OPTIMIZED_GROWTH_STAKE_PCT;
  const fair10End = exhaustiveSearch?.top_fair_10[0]?.end;
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

      {bettingPlan ? (
        <section className="panel strong">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Daily betting plan</p>
              <h2>Automated Strategy (retuned {bettingPlan.generated_at})</h2>
            </div>
            <span>{bettingPlan.strategy}</span>
          </div>
          <p className="lead">
            One ticket per day: pick the highest-scoring qualified single, always-2 parlay, or premium 3-leg parlay.
            Stakes are re-optimized each morning from walk-forward backtests on the current season.
          </p>
          <ol className="muted">
            {bettingPlan.strategy_rules.map((rule) => (
              <li key={rule}>{rule}</li>
            ))}
          </ol>
          <table className="table">
            <thead>
              <tr>
                <th>Ticket type</th>
                <th>Stake % of bankroll</th>
                <th>Example @ $10</th>
                <th>Example @ 35¢</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Single moneyline</td>
                <td>{formatPercent(bettingPlan.stake_by_leg_count["1"] ?? OPTIMIZED_STAKE_BY_LEG_COUNT[1])}</td>
                <td>${(10 * (bettingPlan.stake_by_leg_count["1"] ?? 0.45)).toFixed(2)}</td>
                <td>{(0.35 * (bettingPlan.stake_by_leg_count["1"] ?? 0.45)).toFixed(2)}¢</td>
              </tr>
              <tr>
                <td>2-leg parlay</td>
                <td>{formatPercent(bettingPlan.stake_by_leg_count["2"] ?? OPTIMIZED_STAKE_BY_LEG_COUNT[2])}</td>
                <td>${(10 * (bettingPlan.stake_by_leg_count["2"] ?? 0.25)).toFixed(2)}</td>
                <td>{(0.35 * (bettingPlan.stake_by_leg_count["2"] ?? 0.25)).toFixed(2)}¢</td>
              </tr>
              <tr>
                <td>3-leg parlay</td>
                <td>{formatPercent(bettingPlan.stake_by_leg_count["3"] ?? OPTIMIZED_STAKE_BY_LEG_COUNT[3])}</td>
                <td>${(10 * (bettingPlan.stake_by_leg_count["3"] ?? 0.5)).toFixed(2)}</td>
                <td>{(0.35 * (bettingPlan.stake_by_leg_count["3"] ?? 0.5)).toFixed(2)}¢</td>
              </tr>
            </tbody>
          </table>
          <p className="muted">
            Model retrains through yesterday&apos;s final scores each morning (GitHub Actions ~5 AM Central). Strategy
            rules and stake tiers refresh via <code>npm run model:daily</code> after new odds and results land.
          </p>
        </section>
      ) : null}

      {bestTicket ? (
        <section className="panel strong">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Best ticket today</p>
              <h2>
                {bestTicket.kind === "single"
                  ? "Single Moneyline"
                  : bestTicket.kind === "parlay" && bestTicket.parlay.legCount === 3
                    ? "Premium 3-Leg Parlay"
                    : "2-Leg Parlay"}
              </h2>
            </div>
            <span>
              {bestTicket.kind === "single"
                ? "Single wins today"
                : bestTicket.kind === "parlay" && bestTicket.parlay.legCount === 3
                  ? "3-leg wins today"
                  : bestTicket.qualified
                    ? "Filtered parlay"
                    : "Top-2 EV fallback"}
            </span>
          </div>
          <p className="muted">
            Stake {formatPercent(ticketStakePct)} of bankroll on this ticket
            {bettingPlan
              ? ` (plan retuned ${bettingPlan.generated_at})`
              : bestTicket.kind === "parlay"
                ? ` (${bestTicket.parlay.legCount}-leg tier)`
                : " (single tier)"}
            .
          </p>
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
                  : bestTicket.parlay.strategy === "forced_top_2"
                    ? "Fallback ticket: top two positive-EV legs on different games (no filtered parlay today)."
                    : bestTicket.parlay.strategy === "premium"
                    ? "Premium 3-leg ticket: only shown when the model is very confident across multiple qualified legs."
                    : bestTicket.parlay.strategy === "premium_4"
                      ? "Premium 4-leg ticket: rare slate with four qualified high-confidence legs."
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

      {exhaustiveSearch || strategyBacktest ? (
        <section className="panel strong">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Strict walk-forward backtest</p>
              <h2>2026 Exhaustive Strategy Search</h2>
            </div>
            <span>
              {(exhaustiveSearch ?? strategyBacktest)!.date_range.start} to{" "}
              {(exhaustiveSearch ?? strategyBacktest)!.date_range.end}
            </span>
          </div>
          <p className="lead">
            {exhaustiveSearch
              ? `${exhaustiveSearch.strategies_tested} rules × stake grid, fair daily cap ${formatPercent(exhaustiveSearch.fair_daily_exposure_cap)}. Winner (one bet/day): `
              : "Every strategy uses real day-by-day picks. Winner: "}
            <strong>
              {winnerLabel || "two_or_three_best"} @ {formatPercent(winnerStake)}
            </strong>
            .
          </p>
          {exhaustiveSearch?.weird_result_analysis ? (
            <p className="muted">{exhaustiveSearch.weird_result_analysis.verdict}</p>
          ) : null}
          <div className="grid">
            {winner ? (
              <article>
                <p className="muted">$10,000 fair compound</p>
                <div className="metric positive">{formatBankroll(winnerEnd)}</div>
                <p className="muted">
                  {winnerRecord} · min balance {formatBankroll(winnerMin)} · {winnerBets} bet days
                </p>
              </article>
            ) : null}
            {fair10End ? (
              <article>
                <p className="muted">$10 fair compound</p>
                <div className="metric positive">{formatBankroll(fair10End)}</div>
                <p className="muted">{winnerLabel} @ {formatPercent(winnerStake)}</p>
              </article>
            ) : backtest10[0] ? (
              <article>
                <p className="muted">$10 compound (actual)</p>
                <div className="metric positive">{formatBankroll(backtest10[0].end_bankroll)}</div>
                <p className="muted">
                  {backtest10[0].mode} @ {formatPercent(backtest10[0].optimal_stake_pct)}
                </p>
              </article>
            ) : null}
            <article>
              <p className="muted">always_2 (previous pick)</p>
              <div className="metric">
                {formatBankroll(
                  exhaustiveSearch?.weird_result_analysis.always_2_fair_10k.end ??
                    backtest10k.find((row) => row.mode === "always_2")?.end_bankroll ??
                    0
                )}
              </div>
              <p className="muted">Same stake, no 3-leg upgrade days</p>
            </article>
          </div>
          {fairTop.length > 0 ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th>Days</th>
                  <th>Record</th>
                  <th>$10k fair</th>
                  <th>Stake</th>
                  <th>Multi-bet days</th>
                  <th>Min bal</th>
                </tr>
              </thead>
              <tbody>
                {fairTop.map((row) => (
                  <tr key={row.strategy_id}>
                    <td>{row.strategy_id === winnerLabel ? `★ ${row.strategy_id}` : row.strategy_id}</td>
                    <td>{row.days}</td>
                    <td>
                      {row.wins}-{row.losses}
                    </td>
                    <td className={row.end >= 10000 ? "positive" : ""}>{formatBankroll(row.end)}</td>
                    <td>{formatPercent(row.stake_pct)}</td>
                    <td>{row.multi_bet_days}</td>
                    <td>{formatBankroll(row.min_bankroll)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : strategyBacktest ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th>Days</th>
                  <th>Record</th>
                  <th>Flat ROI</th>
                  <th>$10k compound</th>
                  <th>Opt stake</th>
                  <th>Min bal</th>
                </tr>
              </thead>
              <tbody>
                {backtest10k.map((row) => (
                  <tr key={row.mode}>
                    <td>{row.mode === "always_2" ? "★ always_2" : row.mode}</td>
                    <td>{row.bets}</td>
                    <td>{row.record}</td>
                    <td>{formatPercent(strategyBacktest.flat_by_mode[row.mode]?.flat_roi ?? 0)}</td>
                    <td className={row.end_bankroll >= 10000 ? "positive" : ""}>{formatBankroll(row.end_bankroll)}</td>
                    <td>{formatPercent(row.optimal_stake_pct)}</td>
                    <td>{formatBankroll(row.min_bankroll)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </section>
      ) : null}

      {oosValidation ? (
        <section className="panel">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Out-of-sample check</p>
              <h2>2025 Holdout vs 2026 (Same Rules, No Re-Tuning)</h2>
            </div>
            <span>
              {oosValidation.period_2025.date_range.start}–{oosValidation.period_2025.date_range.end} vs{" "}
              {oosValidation.period_2026.date_range.start}–{oosValidation.period_2026.date_range.end}
            </span>
          </div>
          <p className="muted">{oosValidation.overfitting_analysis.verdict}</p>
          <p className="muted">
            At {formatPercent(oosValidation.stake_pct)} fair daily cap. Flat ROI is fixed $100/bet (more stable than
            compound). 2025 always-bet parlays had positive flat edge but compound bankroll collapsed on bad streaks.
          </p>
          <table className="table">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>2025 fair $10k</th>
                <th>2025 flat ROI</th>
                <th>2026 fair $10k</th>
                <th>2026 flat ROI</th>
              </tr>
            </thead>
            <tbody>
              {(
                [
                  "two_or_three_best",
                  "two_or_three_or_single",
                  "two_or_three_plus_single",
                  "two_and_three",
                  "always_2",
                  "best_ticket",
                  "single"
                ] as const
              ).map((sid) => {
                const r25 = oosValidation.period_2025.focus_strategies_fair_10k[sid];
                const r26 = oosValidation.period_2026.focus_strategies_fair_10k[sid];
                if (!r25 || !r26) {
                  return null;
                }
                return (
                  <tr key={sid}>
                    <td>{sid}</td>
                    <td>{formatBankroll(r25.end)}</td>
                    <td>{formatPercent(r25.flat_roi ?? 0)}</td>
                    <td className={r26.end >= 10000 ? "positive" : ""}>{formatBankroll(r26.end)}</td>
                    <td>{formatPercent(r26.flat_roi ?? 0)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ) : null}

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
