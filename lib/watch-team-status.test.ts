import assert from "node:assert/strict";
import { buildWatchTeamStatuses, formatWatchGameStatusLine } from "./watch-team-status";
import type { GamePrediction } from "./data";
import type { LiveGameState } from "./live-game";

function game(partial: Partial<GamePrediction> & Pick<GamePrediction, "id" | "awayTeam" | "homeTeam">): GamePrediction {
  return {
    startsAt: "2026-08-01T23:15:00Z",
    awayPitcher: "A",
    homePitcher: "B",
    modelHomeWinProbability: 0.5,
    modelAwayWinProbability: 0.5,
    homeMoneyline: -110,
    awayMoneyline: -110,
    confidence: "Low",
    modelVersion: "test",
    explanation: [],
    ...partial
  };
}

function live(partial: Partial<LiveGameState>): LiveGameState {
  return {
    status: "In Progress",
    inning: "Top 6th",
    recentPlays: [],
    away: { teamId: "az", runs: 2, hits: 5, errors: 0 },
    home: { teamId: "cle", runs: 2, hits: 4, errors: 0 },
    ...partial
  };
}

const board = [game({ id: "az-cle-1", awayTeam: "az", homeTeam: "cle", gamePk: 824405 })];
const teams = [
  {
    id: "az",
    name: "Arizona Diamondbacks",
    abbreviation: "AZ",
    primary: "#a71930",
    logoUrl: null
  }
];

const staleLive = new Map<string, LiveGameState | null>([
  ["az-cle-1", live({ status: "In Progress", inning: "Top 6th" })]
]);
const finalLive = new Map<string, LiveGameState | null>([
  [
    "az-cle-1",
    live({
      status: "Final",
      abstractStatus: "Final",
      inning: "Final",
      away: { teamId: "az", runs: 12, hits: 14, errors: 0 },
      home: { teamId: "cle", runs: 8, hits: 10, errors: 1 }
    })
  ]
]);

assert.equal(
  formatWatchGameStatusLine(board[0], staleLive.get("az-cle-1"), "az"),
  "↑ 6th · ARI 2-2 CLE"
);

assert.equal(
  formatWatchGameStatusLine(board[0], finalLive.get("az-cle-1"), "az"),
  "Final · ARI 12-8 CLE"
);

const finalCards = buildWatchTeamStatuses(teams, board, finalLive);
assert.equal(finalCards[0].statusLine, "Final · ARI 12-8 CLE");

console.log("watch_team_status_ok");
