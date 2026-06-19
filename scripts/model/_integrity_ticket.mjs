import { readFileSync } from "fs";
import { getBestDailyTicket } from "../../lib/data.ts";

const board = JSON.parse(readFileSync(process.argv.at(-1), "utf8")).predictions;
const ticket = getBestDailyTicket(board);
if (!ticket) {
  console.log("null");
  process.exit(0);
}
if (ticket.kind === "single") {
  console.log(
    JSON.stringify({
      kind: "single",
      legs: [ticket.bet.team.abbreviation],
      confidences: [ticket.bet.game.confidence],
      pick_probabilities: [ticket.bet.game.pickProbability ?? ticket.bet.modelProbability],
    })
  );
} else {
  console.log(
    JSON.stringify({
      kind: "parlay",
      legs: ticket.parlay.legs.map((leg) => leg.team.abbreviation),
      confidences: ticket.parlay.legs.map((leg) => leg.game.confidence),
      pick_probabilities: ticket.parlay.legs.map(
        (leg) => leg.game.pickProbability ?? leg.modelProbability
      ),
    })
  );
}
