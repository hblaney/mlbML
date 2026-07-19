import { readFileSync } from 'fs';
import { getBestDailyTicket } from '../../lib/data.ts';
const board = JSON.parse(readFileSync(process.argv.at(-1), 'utf8')).predictions;
const ticket = getBestDailyTicket(board);
if (!ticket) { console.log('null'); process.exit(0); }
if (ticket.kind === 'single') {
  const bet = ticket.bet;
  console.log(JSON.stringify({ kind: 'single', label: `${bet.team.abbreviation} ML`, legs: [bet.team.abbreviation], leg_count: 1, odds: bet.odds, model_probability: bet.modelProbability }));
} else if (ticket.kind === 'multi_single') {
  const bets = ticket.bets;
  console.log(JSON.stringify({ kind: 'multi_single', label: bets.map((bet) => `${bet.team.abbreviation} ML`).join(' + '), legs: bets.map((bet) => bet.team.abbreviation), leg_count: bets.length, odds: null, model_probability: null }));
} else {
  const legs = ticket.parlay.legs;
  console.log(JSON.stringify({ kind: 'parlay', label: legs.map((leg) => `${leg.team.abbreviation} ML`).join(' + '), legs: legs.map((leg) => leg.team.abbreviation), leg_count: legs.length, odds: ticket.parlay.americanOdds, model_probability: ticket.parlay.probability }));
}
