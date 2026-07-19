import { readFileSync } from 'fs';
import { getBestDailyTicket } from '../../lib/data.ts';
const payload = JSON.parse(readFileSync(process.argv.at(-1), 'utf8'));
const board = payload.predictions ?? [];
const ticket = getBestDailyTicket(board);
if (!ticket) { console.log('null'); process.exit(0); }
const legDetail = (bet) => ({
  team: bet.team.abbreviation,
  matchup: bet.matchup,
  confidence: bet.game.confidence,
  pickProbability: bet.modelProbability,
  edge: bet.edge,
  odds: bet.odds,
  startsAt: bet.game.startsAt,
});
if (ticket.kind === 'single') {
  const bet = ticket.bet;
  console.log(JSON.stringify({
    kind: 'single',
    label: `${bet.team.abbreviation} ML`,
    legs: [bet.team.abbreviation],
    leg_count: 1,
    odds: bet.odds,
    model_probability: ticket.bet.modelProbability,
    leg_details: [legDetail(bet)],
  }));
} else if (ticket.kind === 'multi_single') {
  const bets = ticket.bets;
  console.log(JSON.stringify({
    kind: 'multi_single',
    label: bets.map((bet) => `${bet.team.abbreviation} ML`).join(' + '),
    legs: bets.map((bet) => bet.team.abbreviation),
    leg_count: bets.length,
    odds: null,
    model_probability: null,
    leg_details: bets.map(legDetail),
  }));
} else {
  const legs = ticket.parlay.legs;
  console.log(JSON.stringify({
    kind: 'parlay',
    label: legs.map((leg) => `${leg.team.abbreviation} ML`).join(' + '),
    legs: legs.map((leg) => leg.team.abbreviation),
    leg_count: legs.length,
    odds: ticket.parlay.americanOdds,
    model_probability: ticket.parlay.probability,
    leg_details: legs.map(legDetail),
  }));
}
