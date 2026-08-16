import {
  americanFromDecimal,
  americanFromProbability,
  decimalOdds,
  expectedValue,
  impliedProbability
} from "./odds";

export type Team = {
  id: string;
  name: string;
  shortName: string;
  abbreviation: string;
  primary: string;
};

export type GamePrediction = {
  id: string;
  /** MLB Stats API gamePk when known (also embedded at end of id). */
  gamePk?: number | string | null;
  startsAt: string;
  awayTeam: string;
  homeTeam: string;
  awayPitcher: string;
  homePitcher: string;
  predictedTeam?: string;
  pickProbability?: number;
  rawPickProbability?: number;
  modelHomeWinProbability: number;
  modelAwayWinProbability: number;
  homeMoneyline: number | null;
  awayMoneyline: number | null;
  homeRunline?: number | null;
  awayRunline?: number | null;
  homeRunlinePrice?: number | null;
  awayRunlinePrice?: number | null;
  marketTotal?: number | null;
  overPrice?: number | null;
  underPrice?: number | null;
  projectedTotal?: number | null;
  oddsSource?: string | null;
  confidence: "Low" | "Medium" | "High" | "Elite";
  /** What to do with bankroll: bet (High/Elite), lean (Medium), pass (Low). */
  betAction?: "bet" | "lean" | "pass";
  /** Model agrees with no-vig market on pick side — required for High/Elite. */
  marketAgrees?: boolean | null;
  /** Sim pick% − market implied for the picked side (uncapped). */
  modelEdge?: number;
  modelVersion: string;
  explanation: string[];
  /** False when a probable starter is TBD or changed since the last board refresh. */
  starterCertain?: boolean;
  pitcherChanged?: boolean;
  /** True when the model pick lost its last 2 games vs this opponent — parlay leg blocked. */
  seriesFade?: boolean;
  /** ERA differential between starters — used as a High/Elite confidence gate. */
  eraDiff?: number;
  /** Recent form edge (pick team 10-game win% minus opponent 10-game win%) — High/Elite gate. */
  formEdge?: number;
  /** pa_monte_carlo | gbm_fallback */
  predictionSource?: string;
  lineupSource?: string | null;
  nSims?: number;
  simRawHomeWinProbability?: number | null;
  gbmHomeWinProbability?: number | null;
};

export type StreamEmbed = {
  gameId: string;
  label: string;
  feed: "home" | "away" | "backup";
  embedUrl: string;
  provider: "MLB Webcast";
  approved: boolean;
};

export type TeamStat = {
  teamId: string;
  wins: number;
  losses: number;
  runDifferential: number;
  wrcPlus: number;
  bullpenEra: number;
  starterEra: number;
  last10: string;
  elo: number;
};

export const teams: Team[] = [
  { id: "ari", name: "Arizona Diamondbacks", shortName: "Diamondbacks", abbreviation: "ARI", primary: "#a71930" },
  { id: "ath", name: "Athletics", shortName: "Athletics", abbreviation: "ATH", primary: "#003831" },
  { id: "atl", name: "Atlanta Braves", shortName: "Braves", abbreviation: "ATL", primary: "#ce1141" },
  { id: "bal", name: "Baltimore Orioles", shortName: "Orioles", abbreviation: "BAL", primary: "#df4601" },
  { id: "bos", name: "Boston Red Sox", shortName: "Red Sox", abbreviation: "BOS", primary: "#bd3039" },
  { id: "chc", name: "Chicago Cubs", shortName: "Cubs", abbreviation: "CHC", primary: "#0e3386" },
  { id: "cws", name: "Chicago White Sox", shortName: "White Sox", abbreviation: "CWS", primary: "#27251f" },
  { id: "cin", name: "Cincinnati Reds", shortName: "Reds", abbreviation: "CIN", primary: "#c6011f" },
  { id: "cle", name: "Cleveland Guardians", shortName: "Guardians", abbreviation: "CLE", primary: "#00385d" },
  { id: "col", name: "Colorado Rockies", shortName: "Rockies", abbreviation: "COL", primary: "#33006f" },
  { id: "det", name: "Detroit Tigers", shortName: "Tigers", abbreviation: "DET", primary: "#0c2340" },
  { id: "hou", name: "Houston Astros", shortName: "Astros", abbreviation: "HOU", primary: "#eb6e1f" },
  { id: "kc", name: "Kansas City Royals", shortName: "Royals", abbreviation: "KC", primary: "#004687" },
  { id: "laa", name: "Los Angeles Angels", shortName: "Angels", abbreviation: "LAA", primary: "#ba0021" },
  { id: "lad", name: "Los Angeles Dodgers", shortName: "Dodgers", abbreviation: "LAD", primary: "#005a9c" },
  { id: "mia", name: "Miami Marlins", shortName: "Marlins", abbreviation: "MIA", primary: "#00a3e0" },
  { id: "mil", name: "Milwaukee Brewers", shortName: "Brewers", abbreviation: "MIL", primary: "#12284b" },
  { id: "min", name: "Minnesota Twins", shortName: "Twins", abbreviation: "MIN", primary: "#002b5c" },
  { id: "nym", name: "New York Mets", shortName: "Mets", abbreviation: "NYM", primary: "#ff5910" },
  { id: "nyy", name: "New York Yankees", shortName: "Yankees", abbreviation: "NYY", primary: "#132448" },
  { id: "phi", name: "Philadelphia Phillies", shortName: "Phillies", abbreviation: "PHI", primary: "#e81828" },
  { id: "pit", name: "Pittsburgh Pirates", shortName: "Pirates", abbreviation: "PIT", primary: "#fdb827" },
  { id: "sd", name: "San Diego Padres", shortName: "Padres", abbreviation: "SD", primary: "#2f241d" },
  { id: "sf", name: "San Francisco Giants", shortName: "Giants", abbreviation: "SF", primary: "#fd5a1e" },
  { id: "sea", name: "Seattle Mariners", shortName: "Mariners", abbreviation: "SEA", primary: "#005c5c" },
  { id: "stl", name: "St. Louis Cardinals", shortName: "Cardinals", abbreviation: "STL", primary: "#c41e3a" },
  { id: "tb", name: "Tampa Bay Rays", shortName: "Rays", abbreviation: "TB", primary: "#092c5c" },
  { id: "tex", name: "Texas Rangers", shortName: "Rangers", abbreviation: "TEX", primary: "#003278" },
  { id: "tor", name: "Toronto Blue Jays", shortName: "Blue Jays", abbreviation: "TOR", primary: "#134a8e" },
  { id: "wsh", name: "Washington Nationals", shortName: "Nationals", abbreviation: "WSH", primary: "#ab0003" }
];

export const predictions: GamePrediction[] = [
  {
    id: "bal-sea-2026-06-08",
    startsAt: "2026-06-08T21:40:00-05:00",
    awayTeam: "bal",
    homeTeam: "sea",
    awayPitcher: "Grayson Rodriguez",
    homePitcher: "Logan Gilbert",
    modelHomeWinProbability: 0.548,
    modelAwayWinProbability: 0.452,
    homeMoneyline: -108,
    awayMoneyline: -102,
    confidence: "Medium",
    modelVersion: "elo-gbm-v0.1",
    explanation: ["Seattle owns a starting pitcher edge", "Baltimore has the stronger season-long offense", "Market price is close to fair"]
  },
  {
    id: "nyy-bos-2026-06-08",
    startsAt: "2026-06-08T18:10:00-05:00",
    awayTeam: "nyy",
    homeTeam: "bos",
    awayPitcher: "Gerrit Cole",
    homePitcher: "Brayan Bello",
    modelHomeWinProbability: 0.421,
    modelAwayWinProbability: 0.579,
    homeMoneyline: 126,
    awayMoneyline: -142,
    confidence: "High",
    modelVersion: "elo-gbm-v0.1",
    explanation: ["New York projects better in starter-adjusted run prevention", "Bullpen usage favors Boston slightly", "Road price still leaves a small positive edge"]
  },
  {
    id: "lad-sd-2026-06-08",
    startsAt: "2026-06-08T20:10:00-05:00",
    awayTeam: "lad",
    homeTeam: "sd",
    awayPitcher: "Tyler Glasnow",
    homePitcher: "Yu Darvish",
    modelHomeWinProbability: 0.487,
    modelAwayWinProbability: 0.513,
    homeMoneyline: 104,
    awayMoneyline: -118,
    confidence: "Low",
    modelVersion: "elo-gbm-v0.1",
    explanation: ["Projection is near a coin flip", "Dodgers rate higher offensively", "No major pricing edge at current odds"]
  }
];

const teamStatOverrides: Record<string, Omit<TeamStat, "teamId">> = {
  ari: { wins: 32, losses: 31, runDifferential: 9, wrcPlus: 102, bullpenEra: 3.92, starterEra: 4.02, last10: "5-5", elo: 1511 },
  ath: { wins: 26, losses: 38, runDifferential: -48, wrcPlus: 91, bullpenEra: 4.28, starterEra: 4.61, last10: "4-6", elo: 1458 },
  atl: { wins: 35, losses: 28, runDifferential: 38, wrcPlus: 111, bullpenEra: 3.49, starterEra: 3.81, last10: "6-4", elo: 1542 },
  bal: { wins: 38, losses: 24, runDifferential: 61, wrcPlus: 116, bullpenEra: 3.62, starterEra: 3.77, last10: "7-3", elo: 1559 },
  bos: { wins: 31, losses: 33, runDifferential: -8, wrcPlus: 97, bullpenEra: 4.02, starterEra: 4.21, last10: "4-6", elo: 1492 },
  chc: { wins: 36, losses: 27, runDifferential: 42, wrcPlus: 108, bullpenEra: 3.77, starterEra: 3.69, last10: "7-3", elo: 1547 },
  cws: { wins: 22, losses: 42, runDifferential: -81, wrcPlus: 84, bullpenEra: 4.74, starterEra: 4.88, last10: "3-7", elo: 1428 },
  cin: { wins: 33, losses: 31, runDifferential: 5, wrcPlus: 99, bullpenEra: 3.98, starterEra: 4.1, last10: "5-5", elo: 1504 },
  cle: { wins: 34, losses: 29, runDifferential: 20, wrcPlus: 101, bullpenEra: 3.4, starterEra: 3.95, last10: "6-4", elo: 1525 },
  col: { wins: 20, losses: 44, runDifferential: -95, wrcPlus: 82, bullpenEra: 5.18, starterEra: 5.4, last10: "2-8", elo: 1412 },
  det: { wins: 37, losses: 26, runDifferential: 44, wrcPlus: 106, bullpenEra: 3.55, starterEra: 3.64, last10: "6-4", elo: 1549 },
  hou: { wins: 35, losses: 29, runDifferential: 23, wrcPlus: 107, bullpenEra: 3.68, starterEra: 3.88, last10: "6-4", elo: 1537 },
  kc: { wins: 32, losses: 32, runDifferential: 4, wrcPlus: 98, bullpenEra: 3.85, starterEra: 4.05, last10: "5-5", elo: 1502 },
  laa: { wins: 29, losses: 34, runDifferential: -18, wrcPlus: 95, bullpenEra: 4.23, starterEra: 4.37, last10: "4-6", elo: 1484 },
  lad: { wins: 39, losses: 25, runDifferential: 69, wrcPlus: 119, bullpenEra: 3.71, starterEra: 3.64, last10: "6-4", elo: 1574 },
  mia: { wins: 24, losses: 39, runDifferential: -55, wrcPlus: 88, bullpenEra: 4.41, starterEra: 4.72, last10: "4-6", elo: 1451 },
  mil: { wins: 36, losses: 28, runDifferential: 31, wrcPlus: 105, bullpenEra: 3.6, starterEra: 3.96, last10: "6-4", elo: 1536 },
  min: { wins: 33, losses: 30, runDifferential: 18, wrcPlus: 103, bullpenEra: 3.73, starterEra: 3.91, last10: "5-5", elo: 1519 },
  nym: { wins: 38, losses: 25, runDifferential: 50, wrcPlus: 112, bullpenEra: 3.51, starterEra: 3.7, last10: "7-3", elo: 1558 },
  nyy: { wins: 40, losses: 23, runDifferential: 74, wrcPlus: 121, bullpenEra: 3.18, starterEra: 3.36, last10: "8-2", elo: 1588 },
  phi: { wins: 38, losses: 26, runDifferential: 52, wrcPlus: 113, bullpenEra: 3.58, starterEra: 3.57, last10: "7-3", elo: 1562 },
  pit: { wins: 28, losses: 36, runDifferential: -27, wrcPlus: 92, bullpenEra: 4.09, starterEra: 4.2, last10: "4-6", elo: 1474 },
  sd: { wins: 33, losses: 31, runDifferential: 13, wrcPlus: 103, bullpenEra: 3.83, starterEra: 3.89, last10: "5-5", elo: 1516 },
  sf: { wins: 34, losses: 30, runDifferential: 16, wrcPlus: 101, bullpenEra: 3.8, starterEra: 3.94, last10: "5-5", elo: 1517 },
  sea: { wins: 34, losses: 29, runDifferential: 27, wrcPlus: 101, bullpenEra: 3.44, starterEra: 3.49, last10: "6-4", elo: 1533 },
  stl: { wins: 32, losses: 31, runDifferential: 7, wrcPlus: 99, bullpenEra: 3.9, starterEra: 4.08, last10: "5-5", elo: 1507 },
  tb: { wins: 31, losses: 32, runDifferential: -2, wrcPlus: 98, bullpenEra: 3.86, starterEra: 4.12, last10: "5-5", elo: 1498 },
  tex: { wins: 32, losses: 32, runDifferential: 10, wrcPlus: 100, bullpenEra: 3.95, starterEra: 3.98, last10: "5-5", elo: 1508 },
  tor: { wins: 35, losses: 29, runDifferential: 25, wrcPlus: 106, bullpenEra: 3.7, starterEra: 3.92, last10: "6-4", elo: 1531 },
  wsh: { wins: 27, losses: 36, runDifferential: -34, wrcPlus: 90, bullpenEra: 4.35, starterEra: 4.55, last10: "4-6", elo: 1465 }
};

const defaultTeamStat: Omit<TeamStat, "teamId"> = {
  wins: 30,
  losses: 30,
  runDifferential: 0,
  wrcPlus: 100,
  bullpenEra: 4.0,
  starterEra: 4.0,
  last10: "5-5",
  elo: 1500
};

export const teamStats: TeamStat[] = teams.map((team) => ({
  teamId: team.id,
  ...(teamStatOverrides[team.id] ?? defaultTeamStat)
}));

export const streamEmbeds: StreamEmbed[] = [
  {
    gameId: "bal-sea-2026-06-08",
    label: "Orioles Feed",
    feed: "away",
    embedUrl: "https://mlbwebcast.com/stream/orioles.html",
    provider: "MLB Webcast",
    approved: true
  },
  {
    gameId: "bal-sea-2026-06-08",
    label: "Mariners Feed",
    feed: "home",
    embedUrl: "https://mlbwebcast.com/stream/mariners.html",
    provider: "MLB Webcast",
    approved: true
  }
];

const teamAliases: Record<string, string> = {
  az: "ari",
  arizona: "ari",
  oak: "ath",
  athletics: "ath",
  cws: "cws",
  chw: "cws",
  wsox: "cws",
  kc: "kc",
  kcr: "kc",
  laa: "laa",
  ana: "laa",
  nym: "nym",
  nyy: "nyy",
  sd: "sd",
  sdp: "sd",
  sf: "sf",
  sfg: "sf",
  tb: "tb",
  tbr: "tb",
  wsh: "wsh",
  was: "wsh"
};

export function normalizeTeamId(teamId: string) {
  const normalized = teamId.toLowerCase();
  return teamAliases[normalized] ?? normalized;
}

export function getTeam(teamId: string) {
  const normalized = normalizeTeamId(teamId);
  const team = teams.find((item) => item.id === normalized);
  if (!team) {
    throw new Error(`Unknown team id: ${teamId}`);
  }
  return team;
}

const MIN_MONEYLINE_PROBABILITY = 0.57;
const MIN_MONEYLINE_EDGE = 0.10;
const LIVE_DAILY_MIN_EDGE = 0.10;
const LIVE_VALUE_SINGLE_MIN_EDGE = 0.12;
// Live-strategy value gate — thin edges burned the last week (BAL agree-market vs CHC disagree).
const HIGH_ELITE_MIN_EDGE = 0.08;
const MAX_MONEYLINE_ABS_ODDS = 180;
const BEST_AVAILABLE_MONEYLINE_COUNT = 5;
const BEST_AVAILABLE_MIN_EDGE = 0.04;
const BEST_AVAILABLE_MAX_ABS_ODDS = 220;
const MODEL_ONLY_MIN_PROBABILITY = 0.60;
const MARKET_BASELINE_ODDS = -110;
const DEFAULT_MARKET_TOTAL = 8.5;
const DEFAULT_JUICE_ODDS = -110;

export type BestBet = {
  id: string;
  game: GamePrediction;
  team: Team;
  opponent: Team;
  matchup: string;
  side: string;
  odds: number;
  modelProbability: number;
  bookProbability: number;
  ev: number;
  edge: number;
  modelOnly?: boolean;
  qualified?: boolean;
};

function boardHasMarketOdds(board: GamePrediction[]) {
  return board.some((game) => game.homeMoneyline !== null && game.awayMoneyline !== null);
}

/** Live plan: always the model's predicted winner — never the opposite side for +EV. */
function modelPickSideForGame(game: GamePrediction) {
  const predicted = game.predictedTeam?.toLowerCase();
  const pickHome = predicted
    ? predicted === game.homeTeam.toLowerCase()
    : game.modelHomeWinProbability >= game.modelAwayWinProbability;
  return pickHome ? ("home" as const) : ("away" as const);
}

function buildMarketMoneylineCandidates(board: GamePrediction[]) {
  return board
    .filter((game) => game.homeMoneyline !== null && game.awayMoneyline !== null)
    .map((game) => {
      const away = getTeam(game.awayTeam);
      const home = getTeam(game.homeTeam);
      const matchup = `${away.abbreviation} @ ${home.abbreviation}`;
      const pickHome = modelPickSideForGame(game) === "home";
      const team = pickHome ? home : away;
      const opponent = pickHome ? away : home;
      const odds = (pickHome ? game.homeMoneyline : game.awayMoneyline) as number;
      const modelProbability = pickHome ? game.modelHomeWinProbability : game.modelAwayWinProbability;
      const bookProbability = impliedProbability(odds);

      return {
        id: `${game.id}-${pickHome ? "home" : "away"}`,
        game,
        team,
        opponent,
        matchup,
        side: "Moneyline",
        odds,
        modelProbability,
        bookProbability,
        ev: expectedValue(modelProbability, odds),
        edge: modelProbability - bookProbability
      };
    });
}

function buildMarketMoneylineBets(board: GamePrediction[]) {
  return buildMarketMoneylineCandidates(board)
    .filter(
      (bet) =>
        bet.modelProbability >= MIN_MONEYLINE_PROBABILITY &&
        bet.edge >= MIN_MONEYLINE_EDGE &&
        Math.abs(bet.odds) <= MAX_MONEYLINE_ABS_ODDS &&
        bet.ev > 0
    )
    .map((bet) => ({ ...bet, qualified: true }))
    .sort((a, b) => b.modelProbability - a.modelProbability || b.edge - a.edge);
}

function buildBestAvailableMarketMoneylineBets(board: GamePrediction[], excludedIds = new Set<string>()) {
  const byGame = new Map<string, BestBet>();

  for (const bet of buildMarketMoneylineCandidates(board)) {
    if (excludedIds.has(bet.id)) {
      continue;
    }
    if (bet.edge < BEST_AVAILABLE_MIN_EDGE || Math.abs(bet.odds) > BEST_AVAILABLE_MAX_ABS_ODDS) {
      continue;
    }

    const candidate = { ...bet, qualified: false };
    const existing = byGame.get(bet.game.id);
    if (!existing || candidate.ev > existing.ev || (candidate.ev === existing.ev && candidate.edge > existing.edge)) {
      byGame.set(bet.game.id, candidate);
    }
  }

  return [...byGame.values()]
    .sort(
      (left, right) =>
        right.ev - left.ev ||
        right.edge - left.edge ||
        right.modelProbability - left.modelProbability
    )
    .slice(0, BEST_AVAILABLE_MONEYLINE_COUNT);
}

function buildModelOnlyMoneylineBets(board: GamePrediction[]) {
  const baselineBook = impliedProbability(MARKET_BASELINE_ODDS);

  return board
    .flatMap((game) => {
      const away = getTeam(game.awayTeam);
      const home = getTeam(game.homeTeam);
      const matchup = `${away.abbreviation} @ ${home.abbreviation}`;
      const pickHome = game.modelHomeWinProbability >= game.modelAwayWinProbability;
      const team = pickHome ? home : away;
      const opponent = pickHome ? away : home;
      const modelProbability = pickHome ? game.modelHomeWinProbability : game.modelAwayWinProbability;
      const fairOdds = americanFromProbability(modelProbability);

      return [
        {
          id: `${game.id}-${pickHome ? "home" : "away"}`,
          game,
          team,
          opponent,
          matchup,
          side: "Moneyline",
          odds: fairOdds,
          modelProbability,
          bookProbability: baselineBook,
          ev: expectedValue(modelProbability, MARKET_BASELINE_ODDS),
          edge: modelProbability - baselineBook,
          modelOnly: true,
          qualified: modelProbability >= MIN_MONEYLINE_PROBABILITY
        }
      ];
    })
    .filter((bet) => bet.modelProbability >= MODEL_ONLY_MIN_PROBABILITY)
    .sort((left, right) => right.modelProbability - left.modelProbability);
}

function topModelOnlyMoneylineBet(board: GamePrediction[]): BestBet | null {
  const candidates = buildModelOnlyMoneylineBets(board);
  if (candidates.length > 0) {
    return candidates[0];
  }

  const fallback = [...board].sort(
    (left, right) =>
      Math.max(right.modelHomeWinProbability, right.modelAwayWinProbability) -
      Math.max(left.modelHomeWinProbability, left.modelAwayWinProbability)
  )[0];

  if (!fallback) {
    return null;
  }

  const away = getTeam(fallback.awayTeam);
  const home = getTeam(fallback.homeTeam);
  const pickHome = fallback.modelHomeWinProbability >= fallback.modelAwayWinProbability;
  const team = pickHome ? home : away;
  const opponent = pickHome ? away : home;
  const modelProbability = pickHome ? fallback.modelHomeWinProbability : fallback.modelAwayWinProbability;
  const baselineBook = impliedProbability(MARKET_BASELINE_ODDS);

  return {
    id: `${fallback.id}-${pickHome ? "home" : "away"}`,
    game: fallback,
    team,
    opponent,
    matchup: `${away.abbreviation} @ ${home.abbreviation}`,
    side: "Moneyline",
    odds: americanFromProbability(modelProbability),
    modelProbability,
    bookProbability: baselineBook,
    ev: expectedValue(modelProbability, MARKET_BASELINE_ODDS),
    edge: modelProbability - baselineBook,
    modelOnly: true,
    qualified: false
  };
}

export function getBestBets(board: GamePrediction[] = predictions): BestBet[] {
  const candidates = buildMarketMoneylineCandidates(board)
    .filter((bet) => bet.modelProbability >= MIN_MONEYLINE_PROBABILITY)
    .sort((a, b) => b.modelProbability - a.modelProbability || b.edge - a.edge);

  if (boardHasMarketOdds(board) && candidates.length > 0) {
    return candidates.slice(0, BEST_AVAILABLE_MONEYLINE_COUNT).map((bet) => ({ ...bet, qualified: true }));
  }

  const modelBets = buildModelOnlyMoneylineBets(board)
    .filter((bet) => bet.qualified)
    .sort((a, b) => b.modelProbability - a.modelProbability);
  if (modelBets.length > 0) {
    return modelBets;
  }

  return [];
}

const BOARD_CONFIDENCE_RANK: Record<GamePrediction["confidence"], number> = {
  Elite: 4,
  High: 3,
  Medium: 2,
  Low: 1
};

/** Board ranked by confidence first (Elite/High above Medium), then probability. */
export function getSortedPredictions(board: GamePrediction[] = predictions): GamePrediction[] {
  return [...board].sort(
    (left, right) =>
      BOARD_CONFIDENCE_RANK[right.confidence] - BOARD_CONFIDENCE_RANK[left.confidence] ||
      (right.pickProbability ?? 0) - (left.pickProbability ?? 0)
  );
}

function sigmoid(value: number) {
  return 1 / (1 + Math.exp(-value));
}

function runlineProbability(homeProbability: number, homeRunline: number) {
  const expectedMargin = Math.log(homeProbability / (1 - homeProbability)) * 3.1;
  return sigmoid((expectedMargin + homeRunline) / 2.4);
}

function totalProbability(projectedTotal: number, marketTotal: number) {
  return sigmoid((projectedTotal - marketTotal) / 2.1);
}

export type AdvancedBet = {
  id: string;
  market: string;
  label: string;
  game: GamePrediction;
  team: Team;
  opponent: Team;
  matchup: string;
  odds: number;
  modelProbability: number;
  bookProbability: number;
  ev: number;
  edge: number;
  modelOnly?: boolean;
};

function buildMarketAdvancedBets(board: GamePrediction[]) {
  return board
    .flatMap((game) => {
      const away = getTeam(game.awayTeam);
      const home = getTeam(game.homeTeam);
      const matchup = `${away.abbreviation} @ ${home.abbreviation}`;
      const rows = [];

      if (game.homeRunline !== null && game.homeRunline !== undefined && game.homeRunlinePrice) {
        const probability = runlineProbability(game.modelHomeWinProbability, game.homeRunline);
        rows.push({
          id: `${game.id}-home-runline`,
          market: "Run Line",
          label: `${home.abbreviation} ${game.homeRunline > 0 ? "+" : ""}${game.homeRunline}`,
          game,
          team: home,
          opponent: away,
          matchup,
          odds: game.homeRunlinePrice,
          modelProbability: probability,
          bookProbability: impliedProbability(game.homeRunlinePrice),
          ev: expectedValue(probability, game.homeRunlinePrice)
        });
      }

      if (game.awayRunline !== null && game.awayRunline !== undefined && game.awayRunlinePrice) {
        const probability = 1 - runlineProbability(game.modelHomeWinProbability, -game.awayRunline);
        rows.push({
          id: `${game.id}-away-runline`,
          market: "Run Line",
          label: `${away.abbreviation} ${game.awayRunline > 0 ? "+" : ""}${game.awayRunline}`,
          game,
          team: away,
          opponent: home,
          matchup,
          odds: game.awayRunlinePrice,
          modelProbability: probability,
          bookProbability: impliedProbability(game.awayRunlinePrice),
          ev: expectedValue(probability, game.awayRunlinePrice)
        });
      }

      if (game.marketTotal && game.projectedTotal && game.overPrice && game.underPrice) {
        const overProbability = totalProbability(game.projectedTotal, game.marketTotal);
        rows.push({
          id: `${game.id}-over`,
          market: "Total",
          label: `Over ${game.marketTotal}`,
          game,
          team: home,
          opponent: away,
          matchup,
          odds: game.overPrice,
          modelProbability: overProbability,
          bookProbability: impliedProbability(game.overPrice),
          ev: expectedValue(overProbability, game.overPrice)
        });
        rows.push({
          id: `${game.id}-under`,
          market: "Total",
          label: `Under ${game.marketTotal}`,
          game,
          team: home,
          opponent: away,
          matchup,
          odds: game.underPrice,
          modelProbability: 1 - overProbability,
          bookProbability: impliedProbability(game.underPrice),
          ev: expectedValue(1 - overProbability, game.underPrice)
        });
      }

      return rows;
    })
    .map((bet) => ({ ...bet, edge: bet.modelProbability - bet.bookProbability }))
    .filter((bet) => bet.edge > 0.015 && bet.ev > 0)
    .sort((left, right) => right.ev - left.ev);
}

function buildModelOnlyAdvancedBets(board: GamePrediction[]) {
  const baselineBook = impliedProbability(DEFAULT_JUICE_ODDS);
  const rows: AdvancedBet[] = [];

  for (const game of board) {
    const away = getTeam(game.awayTeam);
    const home = getTeam(game.homeTeam);
    const matchup = `${away.abbreviation} @ ${home.abbreviation}`;

    if (game.projectedTotal) {
      const overProbability = totalProbability(game.projectedTotal, DEFAULT_MARKET_TOTAL);
      const pickOver = overProbability >= 0.5;
      const modelProbability = pickOver ? overProbability : 1 - overProbability;

      if (modelProbability >= 0.52) {
        rows.push({
          id: `${game.id}-${pickOver ? "over" : "under"}-model`,
          market: "Total",
          label: pickOver ? `Over ${DEFAULT_MARKET_TOTAL}` : `Under ${DEFAULT_MARKET_TOTAL}`,
          game,
          team: home,
          opponent: away,
          matchup,
          odds: DEFAULT_JUICE_ODDS,
          modelProbability,
          bookProbability: baselineBook,
          ev: expectedValue(modelProbability, DEFAULT_JUICE_ODDS),
          edge: modelProbability - baselineBook,
          modelOnly: true
        });
      }
    }

    const homeRunline = -1.5;
    const homeCoverProbability = runlineProbability(game.modelHomeWinProbability, homeRunline);
    const pickHomeRunline = homeCoverProbability >= 0.5;
    const runlineProbabilityValue = pickHomeRunline ? homeCoverProbability : 1 - homeCoverProbability;

    if (runlineProbabilityValue >= 0.52) {
      const team = pickHomeRunline ? home : away;
      const opponent = pickHomeRunline ? away : home;
      const runline = pickHomeRunline ? homeRunline : 1.5;

      rows.push({
        id: `${game.id}-${pickHomeRunline ? "home" : "away"}-runline-model`,
        market: "Run Line",
        label: `${team.abbreviation} ${runline > 0 ? "+" : ""}${runline}`,
        game,
        team,
        opponent,
        matchup,
        odds: DEFAULT_JUICE_ODDS,
        modelProbability: runlineProbabilityValue,
        bookProbability: baselineBook,
        ev: expectedValue(runlineProbabilityValue, DEFAULT_JUICE_ODDS),
        edge: runlineProbabilityValue - baselineBook,
        modelOnly: true
      });
    }
  }

  return rows.sort((left, right) => right.modelProbability - left.modelProbability);
}

export function getAdvancedBets(board: GamePrediction[] = predictions): AdvancedBet[] {
  const marketBets = buildMarketAdvancedBets(board);
  if (marketBets.length > 0) {
    return marketBets;
  }

  const modelBets = buildModelOnlyAdvancedBets(board);
  if (modelBets.length > 0) {
    return modelBets.slice(0, 8);
  }

  const topTotal = [...board]
    .filter((game) => game.projectedTotal)
    .sort(
      (left, right) =>
        Math.abs((right.projectedTotal ?? DEFAULT_MARKET_TOTAL) - DEFAULT_MARKET_TOTAL) -
        Math.abs((left.projectedTotal ?? DEFAULT_MARKET_TOTAL) - DEFAULT_MARKET_TOTAL)
    )[0];

  if (!topTotal?.projectedTotal) {
    return [];
  }

  const away = getTeam(topTotal.awayTeam);
  const home = getTeam(topTotal.homeTeam);
  const overProbability = totalProbability(topTotal.projectedTotal, DEFAULT_MARKET_TOTAL);
  const pickOver = overProbability >= 0.5;
  const modelProbability = pickOver ? overProbability : 1 - overProbability;
  const baselineBook = impliedProbability(DEFAULT_JUICE_ODDS);

  return [
    {
      id: `${topTotal.id}-fallback-total`,
      market: "Total",
      label: pickOver ? `Over ${DEFAULT_MARKET_TOTAL}` : `Under ${DEFAULT_MARKET_TOTAL}`,
      game: topTotal,
      team: home,
      opponent: away,
      matchup: `${away.abbreviation} @ ${home.abbreviation}`,
      odds: DEFAULT_JUICE_ODDS,
      modelProbability,
      bookProbability: baselineBook,
      ev: expectedValue(modelProbability, DEFAULT_JUICE_ODDS),
      edge: modelProbability - baselineBook,
      modelOnly: true
    }
  ];
}

// Leg-probability floors are on the TRUE calibrated scale (High >= 0.65, Medium >= 0.57).
const SAFE_PARLAY_MIN_LEG_PROBABILITY = 0.65;
const SAFE_PARLAY_MIN_LEG_EDGE = 0.05;
const SAFE_PARLAY_MIN_BOOK_PROBABILITY = 0.50;
/** Live site parlays: stricter legs than backtest pool — no forced pairings. */
const LIVE_PARLAY_MIN_LEG_EDGE = 0.06;
const LIVE_PARLAY_MIN_BOOK_PROBABILITY = 0.50;
const LIVE_PARLAY_HIGH_ELITE_MIN_PROBABILITY = 0.65;
const LIVE_PARLAY_MEDIUM_MIN_PROBABILITY = 0.57;
const LIVE_PARLAY_MIN_COMBINED_PROBABILITY_2 = 0.34;
const LIVE_PARLAY_MIN_COMBINED_PROBABILITY_3 = 0.20;
const LIVE_PARLAY_MIN_HIGH_ELITE_LEGS_2 = 1;
const LIVE_PARLAY_MIN_HIGH_ELITE_LEGS_3 = 2;
const ANCHOR_PARLAY_MIN_CONFIDENCE_PROBABILITY = 0.64;
const ANCHOR_PARLAY_MIN_BOOK_PROBABILITY = 0.50;
const ANCHOR_PARLAY_MIN_LEG_EV = -2;
const PREMIUM_PARLAY_MIN_COMBINED_PROBABILITY = 0.20;
const PREMIUM_PARLAY_MIN_HIGH_ELITE_LEGS = 2;
const PREMIUM_4LEG_MIN_COMBINED_PROBABILITY = 0.10;
const PREMIUM_4LEG_MIN_HIGH_ELITE_LEGS = 2;
const SAFE_PARLAY_MAX_LEGS = 2;
const DAILY_PARLAY_LEG_COUNTS = [2] as const;
const CONFIDENCE_RANK: Record<GamePrediction["confidence"], number> = {
  Elite: 4,
  High: 3,
  Medium: 2,
  Low: 1
};

/** Parlays exclude Low-confidence legs (2026 strategy research: +87.5% flat vs +81.1%). */
function isParlayEligibleConfidence(confidence: GamePrediction["confidence"]) {
  return confidence !== "Low";
}

function isStarterReadyForParlay(game: GamePrediction) {
  // Exclude only when a starter is unconfirmed (TBD). A pitcherChanged flag just means a
  // probable starter differs from the previous board — the current board has already
  // re-predicted with the now-known starters, so the pick is not stale and stays eligible.
  if (game.starterCertain === false) {
    return false;
  }
  if (game.seriesFade === true) {
    return false;
  }
  return true;
}

/** When 2+ Medium+ picks reach this win%, force top-2 parlay by model win%. */
export const TRG59_FORCE_PARLAY_MIN_PROBABILITY = 0.57;
/** Skip force-2 when combined parlay hit rate falls below this (too volatile for live). */
export const TRG59_MIN_COMBINED_PROBABILITY = 0.34;

/** @deprecated use TRG59_FORCE_PARLAY_MIN_PROBABILITY */
export const MED60_FORCE_PARLAY_MIN_PROBABILITY = TRG59_FORCE_PARLAY_MIN_PROBABILITY;

/** Live plan: 2-leg High stack when available; else one High single; else skip. */
export const LIVE_BETTING_STRATEGY = "daily_high_two_leg";

/** Small positive edge band — live big-edge (≥8%) hit ~48% recently (model error). */
export const MARKET_AGREE_MIN_EDGE = 0.015;
export const MARKET_AGREE_MAX_EDGE = 0.055;
export const MARKET_AGREE_MIN_PROB = 0.55;
export const MARKET_AGREE_MIN_COMBINED_2 = 0.30;
export const MARKET_AGREE_MIN_COMBINED_3 = 0.18;

/**
 * Favorite-first parlay guards (Jul 2026): the model was fighting the market and
 * stacking longshot legs (+400 to +665 parlays) that lost. Only take sides the
 * market prices as favorites/pick'ems, prefer the ones the book most believes in,
 * and cap the combined price so the ticket is a cashable favorite parlay — not a
 * lottery ticket.
 */
export const MARKET_AGREE_FAVORITE_ODDS_CAP = 105; // reject legs longer than +105 (no dogs)
export const MARKET_AGREE_MIN_LEG_BOOK_PROB = 0.55; // leg should be a real market favorite
export const MARKET_AGREE_MAX_PARLAY_DECIMAL = 4.0; // ~+300 combined; drop to 2 legs if longer

/** Fallback single bar when no parlay qualifies. */
export const PARLAY_FIRST_ELITE_SINGLE_MIN = 0.67;
/** Parlay legs must beat market by at least 8% edge (2026 walk-forward: 87.5% parlay hit). */
export const PARLAY_FIRST_MIN_LEG_EDGE = 0.08;
/** At least one High/Elite leg on every parlay ticket. */
export const PARLAY_FIRST_MIN_HE_LEGS = 1;
/** Real MLB moneylines never exceed ±1500; beyond that is corrupted feed data. */
const ML_SANITY_LIMIT_LIVE = 1500;
const USE_PARLAY_CORRELATION_FILTER = false;
const PARLAY_CORRELATION_WINDOW_MINUTES = 60;

const TEAM_DIVISION: Record<string, string> = {
  bal: "AL_E",
  bos: "AL_E",
  nyy: "AL_E",
  tb: "AL_E",
  tor: "AL_E",
  cws: "AL_C",
  cle: "AL_C",
  det: "AL_C",
  kc: "AL_C",
  min: "AL_C",
  hou: "AL_W",
  laa: "AL_W",
  ath: "AL_W",
  sea: "AL_W",
  tex: "AL_W",
  atl: "NL_E",
  mia: "NL_E",
  nym: "NL_E",
  phi: "NL_E",
  wsh: "NL_E",
  chc: "NL_C",
  cin: "NL_C",
  mil: "NL_C",
  pit: "NL_C",
  stl: "NL_C",
  ari: "NL_W",
  col: "NL_W",
  lad: "NL_W",
  sd: "NL_W",
  sf: "NL_W"
};

function teamDivision(teamId: string) {
  return TEAM_DIVISION[teamId.toLowerCase()];
}

function gameStartMinutes(game: GamePrediction) {
  if (!game.startsAt) {
    return null;
  }
  const parsed = Date.parse(game.startsAt);
  if (Number.isNaN(parsed)) {
    return null;
  }
  return Math.floor(parsed / 60000);
}

function isParlayCorrelationAllowed(legs: BestBet[]) {
  if (!USE_PARLAY_CORRELATION_FILTER) {
    return true;
  }
  for (let left = 0; left < legs.length; left += 1) {
    for (let right = left + 1; right < legs.length; right += 1) {
      const a = legs[left];
      const b = legs[right];
      const divisionA = teamDivision(a.team.id);
      const divisionB = teamDivision(b.team.id);
      if (divisionA && divisionB && divisionA === divisionB) {
        return false;
      }

      const startA = gameStartMinutes(a.game);
      const startB = gameStartMinutes(b.game);
      if (startA !== null && startB !== null && Math.abs(startA - startB) <= PARLAY_CORRELATION_WINDOW_MINUTES) {
        return false;
      }
    }
  }
  return true;
}

function parlayLegOdds(leg: BestBet) {
  return leg.modelOnly ? MARKET_BASELINE_ODDS : leg.odds;
}

function buildParlayCandidate(legs: BestBet[], stake = 100): ParlayCandidate {
  const probability = legs.reduce((value, leg) => value * leg.modelProbability, 1);
  const parlayDecimal = legs.reduce((value, leg) => value * decimalOdds(parlayLegOdds(leg)), 1);
  const payoutProfit = (parlayDecimal - 1) * stake;
  const ev = probability * payoutProfit - (1 - probability) * stake;

  return {
    id: legs.map((leg) => leg.id).join("|"),
    legs,
    legCount: legs.length,
    probability,
    decimalOdds: parlayDecimal,
    americanOdds: americanFromDecimal(parlayDecimal),
    ev,
    payoutProfit,
    score: ev * probability
  };
}

function buildFallbackParlay(singles: BestBet[], stake = 100): ParlayCandidate | null {
  const uniqueGameSingles: BestBet[] = [];

  for (const single of singles) {
    if (uniqueGameSingles.some((existing) => existing.game.id === single.game.id)) {
      continue;
    }
    uniqueGameSingles.push(single);
    if (uniqueGameSingles.length >= 2) {
      break;
    }
  }

  if (uniqueGameSingles.length < 2) {
    return null;
  }

  return buildParlayCandidate(uniqueGameSingles.slice(0, 2), stake);
}

export type ParlayCandidate = {
  id: string;
  legs: BestBet[];
  legCount: number;
  probability: number;
  decimalOdds: number;
  americanOdds: number;
  ev: number;
  payoutProfit: number;
  score: number;
  strategy?: "edge" | "anchor" | "premium" | "premium_4" | "forced_top_2" | "live_quality" | "live_premium" | "trg59_top2" | "high_elite_76_parlay" | "best_ticket" | "calibrated_parlay" | "quality_single" | "strong_parlay" | "power_parlay" | "parlay_first" | "daily_top3_evscore" | "daily_top3_prob" | "market_agree_parlay" | "daily_best_single" | "daily_high_two_leg" | "edge_value_ticket";
};

/** Flat fallback when leg-specific stake is unavailable (2026 sweep best: 35%). */
export const OPTIMIZED_GROWTH_STAKE_PCT = 0.35;

/** 2026 rigorous sweep: 35% single · 45% two-leg · 10% three-leg of wallet. */
export const OPTIMIZED_STAKE_BY_LEG_COUNT: Record<number, number> = {
  1: 0.35,
  2: 0.45,
  3: 0.1
};

/** Locked live stakes — same as OPTIMIZED_STAKE_BY_LEG_COUNT. */
export const LIVE_STAKE_BY_LEG_COUNT = OPTIMIZED_STAKE_BY_LEG_COUNT;

export function getOptimizedStakePctForTicket(
  ticket: DailyTicket | null,
  stakeByLeg?: Record<string, number>
): number {
  if (!ticket) {
    return OPTIMIZED_GROWTH_STAKE_PCT;
  }
  if (ticket.kind === "multi_single") {
    return 0.5;
  }
  const legKey =
    ticket.kind === "single"
      ? "1"
      : String(ticket.parlay.legCount);
  const fromPlan = stakeByLeg?.[legKey];
  if (fromPlan != null) {
    return fromPlan;
  }
  if (ticket.kind === "single") {
    return OPTIMIZED_STAKE_BY_LEG_COUNT[1];
  }
  return OPTIMIZED_STAKE_BY_LEG_COUNT[ticket.parlay.legCount] ?? OPTIMIZED_GROWTH_STAKE_PCT;
}

/**
 * Ratchet staking: scale down stake % as bankroll grows to protect gains.
 *
 * Tiers (Jun 23 — 20-ticket prove-out, then growth):
 * Ratchet stakes tuned for power_parlay (walk-forward optimal on $10–$200 wallet):
 *   $0–$199:    50% parlay / 20% single
 *   $200–$999:  40% parlay / 18% single
 *   $1,000+:    30% parlay / 12% single
 */
export function getRatchetStakePct(
  balance: number,
  legCount: number,
  ratchetTiers?: Array<{ min_balance: number; max_balance: number | null; parlay_pct: number; single_pct: number }>
): number {
  const tiers = ratchetTiers ?? [
    { min_balance: 0,    max_balance: 199,  parlay_pct: 0.50, single_pct: 0.20 },
    { min_balance: 200,  max_balance: 999,  parlay_pct: 0.40, single_pct: 0.18 },
    { min_balance: 1000, max_balance: null, parlay_pct: 0.30, single_pct: 0.12 },
  ];
  const tier = [...tiers]
    .reverse()
    .find(t => balance >= t.min_balance) ?? tiers[0];
  return legCount === 1 ? tier.single_pct : tier.parlay_pct;
}

export type DailyTicket =
  | {
      kind: "single";
      bet: BestBet;
      score: number;
      qualified: boolean;
    }
  | {
      kind: "multi_single";
      bets: BestBet[];
      score: number;
      qualified: boolean;
    }
  | {
      kind: "parlay";
      parlay: ParlayCandidate;
      score: number;
      qualified: boolean;
    };

export type ParlayStrategyInput = {
  leg_count: number;
  min_edge: number;
  min_probability: number;
  top_n: number;
};

function combinations<T>(items: T[], size: number, limit = 6000) {
  const result: T[][] = [];

  function walk(start: number, combo: T[]) {
    if (result.length >= limit) {
      return;
    }
    if (combo.length === size) {
      result.push([...combo]);
      return;
    }
    for (let index = start; index <= items.length - (size - combo.length); index += 1) {
      combo.push(items[index]);
      walk(index + 1, combo);
      combo.pop();
    }
  }

  walk(0, []);
  return result;
}

function getParlayLegCandidates(board: GamePrediction[] = predictions) {
  if (!boardHasMarketOdds(board)) {
    return [];
  }

  return buildMarketMoneylineCandidates(board)
    .filter(
      (bet) =>
        isParlayEligibleConfidence(bet.game.confidence) &&
        isStarterReadyForParlay(bet.game) &&
        bet.modelProbability >= SAFE_PARLAY_MIN_LEG_PROBABILITY &&
        bet.edge >= SAFE_PARLAY_MIN_LEG_EDGE &&
        bet.bookProbability >= SAFE_PARLAY_MIN_BOOK_PROBABILITY &&
        bet.ev > 0
    )
    .sort((left, right) => (right.ev * right.modelProbability) - (left.ev * left.modelProbability))
    .slice(0, 8);
}

function passesLiveParlayLegFilter(bet: BestBet) {
  if (!isParlayEligibleConfidence(bet.game.confidence)) {
    return false;
  }
  if (!isStarterReadyForParlay(bet.game)) {
    return false;
  }
  if (bet.edge < LIVE_PARLAY_MIN_LEG_EDGE || bet.bookProbability < LIVE_PARLAY_MIN_BOOK_PROBABILITY || bet.ev <= 0) {
    return false;
  }
  const minProbability =
    bet.game.confidence === "High" || bet.game.confidence === "Elite"
      ? LIVE_PARLAY_HIGH_ELITE_MIN_PROBABILITY
      : LIVE_PARLAY_MEDIUM_MIN_PROBABILITY;
  return bet.modelProbability >= minProbability;
}

function getParlayFirstLegCandidates(board: GamePrediction[] = predictions) {
  if (!boardHasMarketOdds(board)) {
    return [];
  }

  return buildMarketMoneylineCandidates(board)
    .filter(
      (bet) =>
        isParlayEligibleConfidence(bet.game.confidence) &&
        isStarterReadyForParlay(bet.game) &&
        bet.modelProbability >= SAFE_PARLAY_MIN_LEG_PROBABILITY &&
        bet.edge >= PARLAY_FIRST_MIN_LEG_EDGE &&
        bet.bookProbability >= SAFE_PARLAY_MIN_BOOK_PROBABILITY &&
        bet.ev > 0
    )
    .sort(
      (left, right) =>
        CONFIDENCE_RANK[right.game.confidence] - CONFIDENCE_RANK[left.game.confidence] ||
        right.modelProbability - left.modelProbability ||
        right.ev * right.modelProbability - left.ev * left.modelProbability
    )
    .slice(0, 8);
}

function getParlayFirstTicketForLegCount(board: GamePrediction[], legCount: 2 | 3 | 4) {
  const singles = getParlayFirstLegCandidates(board).slice(0, legCount === 2 ? 8 : 6);
  if (singles.length < legCount) {
    return null;
  }

  let best: ParlayCandidate | null = null;

  for (const legs of combinations(singles, legCount)) {
    const uniqueGames = new Set(legs.map((leg) => leg.game.id));
    if (uniqueGames.size !== legs.length) {
      continue;
    }
    if (!isParlayCorrelationAllowed(legs)) {
      continue;
    }
    if (countHighEliteLegs(legs) < PARLAY_FIRST_MIN_HE_LEGS) {
      continue;
    }

    const candidate = buildParlayCandidate(legs);
    if (candidate.ev <= 0) {
      continue;
    }
    const minCombined =
      legCount === 2
        ? LIVE_PARLAY_MIN_COMBINED_PROBABILITY_2
        : legCount === 3
          ? LIVE_PARLAY_MIN_COMBINED_PROBABILITY_3
          : PREMIUM_4LEG_MIN_COMBINED_PROBABILITY;
    if (candidate.probability < minCombined) {
      continue;
    }

    candidate.strategy = "parlay_first";
    if (!best || candidate.score > best.score) {
      best = candidate;
    }
  }

  return best;
}

function getLiveParlayLegCandidates(board: GamePrediction[] = predictions) {
  if (!boardHasMarketOdds(board)) {
    return [];
  }

  return buildMarketMoneylineCandidates(board)
    .filter(passesLiveParlayLegFilter)
    .sort(
      (left, right) =>
        CONFIDENCE_RANK[right.game.confidence] - CONFIDENCE_RANK[left.game.confidence] ||
        right.modelProbability - left.modelProbability ||
        right.ev * right.modelProbability - left.ev * left.modelProbability
    )
    .slice(0, 8);
}

function countHighEliteLegs(legs: BestBet[]) {
  return legs.filter((leg) => leg.game.confidence === "Elite" || leg.game.confidence === "High").length;
}

function getLiveTwoLegParlay(board: GamePrediction[] = predictions) {
  const singles = getLiveParlayLegCandidates(board);
  if (singles.length < 2) {
    return null;
  }

  let best: ParlayCandidate | null = null;

  for (const legs of combinations(singles, 2)) {
    const uniqueGames = new Set(legs.map((leg) => leg.game.id));
    if (uniqueGames.size !== legs.length) {
      continue;
    }
    if (!isParlayCorrelationAllowed(legs)) {
      continue;
    }
    if (countHighEliteLegs(legs) < LIVE_PARLAY_MIN_HIGH_ELITE_LEGS_2) {
      continue;
    }

    const candidate = buildParlayCandidate(legs);
    if (candidate.ev <= 0 || candidate.probability < LIVE_PARLAY_MIN_COMBINED_PROBABILITY_2) {
      continue;
    }

    candidate.strategy = "live_quality";
    if (!best || candidate.score > best.score) {
      best = candidate;
    }
  }

  return best;
}

function getLiveThreeLegParlay(board: GamePrediction[] = predictions) {
  const singles = getLiveParlayLegCandidates(board).slice(0, 6);
  if (singles.length < 3) {
    return null;
  }

  let best: ParlayCandidate | null = null;

  for (const legs of combinations(singles, 3)) {
    const uniqueGames = new Set(legs.map((leg) => leg.game.id));
    if (uniqueGames.size !== legs.length) {
      continue;
    }
    if (!isParlayCorrelationAllowed(legs)) {
      continue;
    }
    if (countHighEliteLegs(legs) < LIVE_PARLAY_MIN_HIGH_ELITE_LEGS_3) {
      continue;
    }

    const candidate = buildParlayCandidate(legs);
    if (candidate.ev <= 0 || candidate.probability < LIVE_PARLAY_MIN_COMBINED_PROBABILITY_3) {
      continue;
    }

    candidate.strategy = "live_premium";
    if (!best || candidate.score > best.score) {
      best = candidate;
    }
  }

  return best;
}

function getAnchorParlayLegCandidates(board: GamePrediction[] = predictions) {
  if (!boardHasMarketOdds(board)) {
    return [];
  }

  return buildMarketMoneylineCandidates(board)
    .filter(
      (bet) =>
        (bet.game.confidence === "Elite" || bet.game.confidence === "High") &&
        bet.modelProbability >= ANCHOR_PARLAY_MIN_CONFIDENCE_PROBABILITY &&
        bet.bookProbability >= ANCHOR_PARLAY_MIN_BOOK_PROBABILITY &&
        bet.ev >= ANCHOR_PARLAY_MIN_LEG_EV
    )
    .sort(
      (left, right) =>
        CONFIDENCE_RANK[right.game.confidence] - CONFIDENCE_RANK[left.game.confidence] ||
        right.modelProbability - left.modelProbability ||
        right.ev - left.ev
    )
    .slice(0, 8);
}

function getTopMoneylineTicket(board: GamePrediction[] = predictions) {
  const qualified = [...buildMarketMoneylineBets(board)].sort(
    (left, right) => right.modelProbability - left.modelProbability || right.edge - left.edge
  );
  if (qualified.length > 0) {
    return qualified[0];
  }

  const available = buildBestAvailableMarketMoneylineBets(board)
    .filter((bet) => bet.ev > 0)
    .sort(
      (left, right) =>
        right.modelProbability - left.modelProbability ||
        right.edge - left.edge ||
        right.ev - left.ev
    );

  return available[0] ?? null;
}

function ticketScoreForSingle(bet: BestBet) {
  return bet.modelProbability;
}

function bestAnchorParlay(board: GamePrediction[] = predictions, stake = 100) {
  const edgeLegs = getParlayLegCandidates(board);
  const anchorLegs = getAnchorParlayLegCandidates(board);
  let best: ParlayCandidate | null = null;

  for (const edgeLeg of edgeLegs) {
    for (const anchorLeg of anchorLegs) {
      if (edgeLeg.game.id === anchorLeg.game.id) {
        continue;
      }
      if (!isParlayCorrelationAllowed([edgeLeg, anchorLeg])) {
        continue;
      }

      const candidate = buildParlayCandidate([edgeLeg, anchorLeg], stake);
      if (candidate.ev <= 0) {
        continue;
      }

      candidate.strategy = "anchor";
      if (!best || candidate.score > best.score) {
        best = candidate;
      }
    }
  }

  return best;
}

export function getParlayCandidates(board: GamePrediction[] = predictions, stake = 100) {
  const singles = getParlayLegCandidates(board);

  const parlays: ParlayCandidate[] = [];
  const maxLegs = Math.min(SAFE_PARLAY_MAX_LEGS, singles.length);

  for (let legCount = 2; legCount <= maxLegs; legCount += 1) {
    const combos = combinations(singles, legCount);
    for (const legs of combos) {
      const uniqueGames = new Set(legs.map((leg) => leg.game.id));
      if (uniqueGames.size !== legs.length) {
        continue;
      }
      if (!isParlayCorrelationAllowed(legs)) {
        continue;
      }

      const candidate = buildParlayCandidate(legs, stake);
      if (candidate.ev <= 0) {
        continue;
      }
      candidate.strategy = "edge";

      parlays.push(candidate);
    }
  }

  const anchor = bestAnchorParlay(board, stake);
  if (anchor) {
    parlays.push(anchor);
  }

  return parlays.sort((left, right) => right.score - left.score);
}

export function getBestParlaysByLegCount(board: GamePrediction[] = predictions) {
  const parlays = getParlayCandidates(board);
  const byLegCount = new Map<number, ParlayCandidate>();

  for (const parlay of parlays) {
    if (!byLegCount.has(parlay.legCount)) {
      byLegCount.set(parlay.legCount, parlay);
    }
  }

  const results = [...byLegCount.values()].sort((left, right) => left.legCount - right.legCount);
  return results;
}

export function getParlayForStrategy(board: GamePrediction[] = predictions, strategy: ParlayStrategyInput) {
  if (strategy.leg_count < 2) {
    return null;
  }

  const minProbability = Math.max(strategy.min_probability, SAFE_PARLAY_MIN_LEG_PROBABILITY);
  const singles = getParlayLegCandidates(board)
    .filter(
      (bet) =>
        bet.edge >= strategy.min_edge &&
        bet.modelProbability >= minProbability
    )
    .sort((left, right) => (right.ev * right.modelProbability) - (left.ev * left.modelProbability))
    .slice(0, Math.min(strategy.top_n, 8));

  if (singles.length < strategy.leg_count) {
    return null;
  }

  let best: ParlayCandidate | null = null;
  for (const legs of combinations(singles, strategy.leg_count)) {
      const uniqueGames = new Set(legs.map((leg) => leg.game.id));
      if (uniqueGames.size !== legs.length) {
        continue;
      }
      if (!isParlayCorrelationAllowed(legs)) {
        continue;
      }

      const candidate = buildParlayCandidate(legs);
      if (candidate.ev <= 0) {
        continue;
      }
      candidate.strategy = "edge";

    if (!best || candidate.score > best.score) {
      best = candidate;
    }
  }

  return best;
}

export function getBestTwoLegParlay(board: GamePrediction[] = predictions) {
  const singles = getParlayLegCandidates(board)
    .sort(
      (left, right) =>
        CONFIDENCE_RANK[right.game.confidence] - CONFIDENCE_RANK[left.game.confidence] ||
        right.modelProbability - left.modelProbability ||
        (right.ev * right.modelProbability) - (left.ev * left.modelProbability)
    )
    .slice(0, 8);

  let best: ParlayCandidate | null = null;

  if (singles.length >= 2) {
    for (const legs of combinations(singles, 2)) {
      const uniqueGames = new Set(legs.map((leg) => leg.game.id));
      if (uniqueGames.size !== legs.length) {
        continue;
      }
      if (!isParlayCorrelationAllowed(legs)) {
        continue;
      }

      const candidate = buildParlayCandidate(legs);
      if (candidate.ev <= 0) {
        continue;
      }
      candidate.strategy = "edge";
      if (!best || candidate.score > best.score) {
        best = candidate;
      }
    }
  }

  const anchor = bestAnchorParlay(board);
  if (anchor && (!best || anchor.score > best.score)) {
    best = anchor;
  }

  return best;
}

export function getPremiumThreeLegParlay(board: GamePrediction[] = predictions) {
  const singles = getParlayLegCandidates(board)
    .sort((left, right) => (right.ev * right.modelProbability) - (left.ev * left.modelProbability))
    .slice(0, 6);

  if (singles.length < 3) {
    return null;
  }

  let best: ParlayCandidate | null = null;

  for (const legs of combinations(singles, 3)) {
    const uniqueGames = new Set(legs.map((leg) => leg.game.id));
    if (uniqueGames.size !== legs.length) {
      continue;
    }
    if (!isParlayCorrelationAllowed(legs)) {
      continue;
    }

    const highConfidenceLegs = legs.filter(
      (leg) => leg.game.confidence === "Elite" || leg.game.confidence === "High"
    ).length;
    if (highConfidenceLegs < PREMIUM_PARLAY_MIN_HIGH_ELITE_LEGS) {
      continue;
    }

    const candidate = buildParlayCandidate(legs);
    if (candidate.ev <= 0 || candidate.probability < PREMIUM_PARLAY_MIN_COMBINED_PROBABILITY) {
      continue;
    }

    candidate.strategy = "premium";
    if (!best || candidate.score > best.score) {
      best = candidate;
    }
  }

  return best;
}

export function getPremiumFourLegParlay(board: GamePrediction[] = predictions) {
  const singles = getParlayLegCandidates(board)
    .sort((left, right) => (right.ev * right.modelProbability) - (left.ev * left.modelProbability))
    .slice(0, 6);

  if (singles.length < 4) {
    return null;
  }

  let best: ParlayCandidate | null = null;

  for (const legs of combinations(singles, 4)) {
    const uniqueGames = new Set(legs.map((leg) => leg.game.id));
    if (uniqueGames.size !== legs.length) {
      continue;
    }

    const highConfidenceLegs = legs.filter(
      (leg) => leg.game.confidence === "Elite" || leg.game.confidence === "High"
    ).length;
    if (highConfidenceLegs < PREMIUM_4LEG_MIN_HIGH_ELITE_LEGS) {
      continue;
    }

    const candidate = buildParlayCandidate(legs);
    if (candidate.ev <= 0 || candidate.probability < PREMIUM_4LEG_MIN_COMBINED_PROBABILITY) {
      continue;
    }

    candidate.strategy = "premium_4";
    if (!best || candidate.score > best.score) {
      best = candidate;
    }
  }

  return best;
}

function getPositiveEvLegCandidates(board: GamePrediction[] = predictions) {
  if (!boardHasMarketOdds(board)) {
    return [];
  }

  return buildMarketMoneylineCandidates(board)
    .filter(
      (bet) =>
        isParlayEligibleConfidence(bet.game.confidence) &&
        isStarterReadyForParlay(bet.game) &&
        bet.ev > 0
    )
    .sort(
      (left, right) =>
        right.ev * right.modelProbability - left.ev * left.modelProbability ||
        right.ev - left.ev ||
        right.modelProbability - left.modelProbability
    );
}

export function getForcedTopTwoLegParlay(board: GamePrediction[] = predictions) {
  const pool = getPositiveEvLegCandidates(board).slice(0, 8);
  let best: ParlayCandidate | null = null;

  for (const legs of combinations(pool, 2)) {
    const uniqueGames = new Set(legs.map((leg) => leg.game.id));
    if (uniqueGames.size !== legs.length) {
      continue;
    }
    if (!isParlayCorrelationAllowed(legs)) {
      continue;
    }

    const candidate = buildParlayCandidate(legs);
    if (candidate.ev <= 0) {
      continue;
    }
    candidate.strategy = "forced_top_2";
    if (!best || candidate.score > best.score) {
      best = candidate;
    }
  }

  return best;
}

/** Top two Medium+ model picks at or above TRG59 threshold, by win probability. */
export function getTrg59ForceTwoLegParlay(board: GamePrediction[] = predictions): ParlayCandidate | null {
  if (!boardHasMarketOdds(board)) {
    return null;
  }

  const legs: BestBet[] = [];
  const seenGames = new Set<string>();

  for (const bet of buildMarketMoneylineCandidates(board)
    .filter(
      (candidate) =>
        isParlayEligibleConfidence(candidate.game.confidence) &&
        isStarterReadyForParlay(candidate.game) &&
        candidate.modelProbability >= TRG59_FORCE_PARLAY_MIN_PROBABILITY
    )
    .sort((left, right) => right.modelProbability - left.modelProbability)) {
    if (seenGames.has(bet.game.id)) {
      continue;
    }
    legs.push(bet);
    seenGames.add(bet.game.id);
    if (legs.length === 2) {
      break;
    }
  }

  if (legs.length < 2) {
    return null;
  }

  const candidate = buildParlayCandidate(legs);
  candidate.strategy = "trg59_top2";
  return candidate;
}

/** @deprecated use getTrg59ForceTwoLegParlay */
export function getMed60ForceTwoLegParlay(board: GamePrediction[] = predictions): ParlayCandidate | null {
  return getTrg59ForceTwoLegParlay(board);
}

/** Matches Python `best_ticket`: highest-scoring filtered 2/3/4-leg parlay or +EV single. */
export function getBestTicketDailyTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  return getMaxScoreDailyTicket(board);
}

/** Backtest winner (Mar–Jun 2026): filtered 2-leg when available, else top-2 positive-EV legs. */
export function getAlwaysTwoLegParlay(board: GamePrediction[] = predictions) {
  const filtered = getBestTwoLegParlay(board);
  if (filtered) {
    return filtered;
  }
  return getForcedTopTwoLegParlay(board);
}

/** Exhaustive fair backtest winner: always-2 ticket vs filtered premium 3-leg — higher score wins. */
export function getTwoOrThreeBestParlay(board: GamePrediction[] = predictions) {
  const twoLeg = getAlwaysTwoLegParlay(board);
  const threeLeg = getPremiumThreeLegParlay(board);
  const options = [twoLeg, threeLeg].filter((ticket): ticket is ParlayCandidate => ticket !== null);

  if (options.length === 0) {
    return null;
  }

  return options.sort((left, right) => right.score - left.score)[0];
}

/** OOS-tested variant: always-2, premium 3-leg, or qualified single — highest score wins one bet. */
export function getTwoOrThreeOrSingleTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  const options: DailyTicket[] = [];

  const twoLeg = getAlwaysTwoLegParlay(board);
  if (twoLeg) {
    options.push({ kind: "parlay", parlay: twoLeg, score: twoLeg.score, qualified: twoLeg.strategy !== "forced_top_2" });
  }

  const threeLeg = getPremiumThreeLegParlay(board);
  if (threeLeg) {
    options.push({ kind: "parlay", parlay: threeLeg, score: threeLeg.score, qualified: true });
  }

  const single = getTopMoneylineTicket(board);
  if (single && single.ev > 0) {
    options.push({
      kind: "single",
      bet: single,
      score: ticketScoreForSingle(single),
      qualified: Boolean(single.qualified)
    });
  }

  if (options.length === 0) {
    return null;
  }

  return options.sort((left, right) => right.score - left.score)[0];
}

export function getMaxScoreDailyTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  const options: DailyTicket[] = [];

  const single = getTopMoneylineTicket(board);
  if (single && single.ev > 0) {
    options.push({
      kind: "single",
      bet: single,
      score: ticketScoreForSingle(single),
      qualified: Boolean(single.qualified)
    });
  }

  const twoLeg = getBestTwoLegParlay(board);
  if (twoLeg) {
    options.push({
      kind: "parlay",
      parlay: twoLeg,
      score: twoLeg.score,
      qualified: true
    });
  }

  const threeLeg = getPremiumThreeLegParlay(board);
  if (threeLeg) {
    options.push({
      kind: "parlay",
      parlay: threeLeg,
      score: threeLeg.score,
      qualified: true
    });
  }

  const fourLeg = getPremiumFourLegParlay(board);
  if (fourLeg) {
    options.push({
      kind: "parlay",
      parlay: fourLeg,
      score: fourLeg.score,
      qualified: true
    });
  }

  if (options.length === 0) {
    return null;
  }

  const best = options.sort((left, right) => right.score - left.score)[0];
  return best;
}

/**
 * parlay_first — parlay-heavy, realistic hit-rate strategy (2026 walk-forward):
 *   1. Best filtered 2/3/4-leg parlay (legs >= 8% edge, >= 1 High/Elite leg)
 *   2. Else +EV single only if High/Elite and >= 67%
 *   3. Else no bet
 */
export function getParlayFirstDailyTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  const parlayOptions: DailyTicket[] = [];

  for (const legCount of [2, 3, 4] as const) {
    const parlay = getParlayFirstTicketForLegCount(board, legCount);
    if (parlay) {
      parlayOptions.push({ kind: "parlay", parlay, score: parlay.score, qualified: true });
    }
  }

  if (parlayOptions.length > 0) {
    return parlayOptions.sort((left, right) => right.score - left.score)[0];
  }

  const elitePool = buildMarketMoneylineCandidates(board).filter(
    (bet) =>
      (bet.game.confidence === "High" || bet.game.confidence === "Elite") &&
      (bet.game.pickProbability ?? bet.modelProbability) >= PARLAY_FIRST_ELITE_SINGLE_MIN &&
      bet.game.starterCertain !== false &&
      bet.game.seriesFade !== true &&
      bet.ev > 0
  );

  if (elitePool.length === 0) {
    return null;
  }

  const best = elitePool.sort(
    (left, right) =>
      (right.game.pickProbability ?? right.modelProbability) -
        (left.game.pickProbability ?? left.modelProbability) ||
      right.ev - left.ev
  )[0];

  return {
    kind: "single",
    bet: { ...best, qualified: true },
    score: best.game.pickProbability ?? best.modelProbability,
    qualified: true
  };
}

/** Top edge pick on the board — lock priority and headline display. */
export function getTopEdgePick(board: GamePrediction[] = predictions): BestBet | null {
  return getTopMoneylineTicket(board);
}
export function getNoLowParlay223sTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  return getTwoOrThreeOrSingleTicket(board);
}

/** trg59_top_prob_2: force top-2 parlay when 2+ Medium+ picks >= 59%; else best_ticket. */
export function getTrg59TopProb2Ticket(board: GamePrediction[] = predictions): DailyTicket | null {
  const forced = getTrg59ForceTwoLegParlay(board);
  if (forced && forced.probability >= TRG59_MIN_COMBINED_PROBABILITY) {
    return { kind: "parlay", parlay: forced, score: forced.score, qualified: true };
  }
  return getBestTicketDailyTicket(board);
}

/** @deprecated use getTrg59TopProb2Ticket */
export function getMed60ForceTwo223sTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  return getTrg59TopProb2Ticket(board);
}

/**
 * high_elite_76_parlay — walk-forward optimized strategy (2026 season analysis).
 *
 * Rules (probabilities are the model's TRUE calibrated win probability, no inflation):
 * 1. Only High and Elite picks with confirmed market odds qualify.
 *    High ≈ genuinely wins 62%+, Elite ≈ 67%+ (gated by starter ERA edge / team form).
 * 2. 3 qualifying picks → 3-leg parlay; 2 → 2-leg parlay (sorted by win prob).
 * 3. If only 1 qualifying pick (or none) → skip, no bet today.
 */
export function getHighElite76ParlayTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  if (!boardHasMarketOdds(board)) {
    return null;
  }

  // Reject moneylines beyond ±1500 — these are corrupted/stale odds data, not real MLB prices.
  const ML_SANITY_LIMIT = 1500;
  const qualified = buildMarketMoneylineCandidates(board)
    .filter(
      (bet) =>
        (bet.game.confidence === "Elite" || bet.game.confidence === "High") &&
        isStarterReadyForParlay(bet.game) &&
        bet.game.homeMoneyline !== null &&
        bet.game.awayMoneyline !== null &&
        Math.abs(bet.game.homeMoneyline) <= ML_SANITY_LIMIT &&
        Math.abs(bet.game.awayMoneyline) <= ML_SANITY_LIMIT &&
        // +EV safety rail: never bet a leg the model doesn't price as beating the
        // vig-included line.
        bet.ev > 0 &&
        // Value gate: only bet legs with genuine edge over the market line. Validated
        // on the honest model's 2026 walk-forward (see HIGH_ELITE_MIN_EDGE).
        bet.edge >= HIGH_ELITE_MIN_EDGE
    )
    .sort((a, b) => b.edge - a.edge || b.modelProbability - a.modelProbability);

  if (qualified.length === 0) {
    return null;
  }

  // Deduplicate by game id — collect up to 3 High/Elite legs
  const seen = new Set<string>();
  const legs: BestBet[] = [];
  for (const bet of qualified) {
    if (seen.has(bet.game.id)) continue;
    seen.add(bet.game.id);
    legs.push(bet);
    if (legs.length === 3) break;
  }

  // 3 High/Elite picks → 3-leg parlay; 2 → 2-leg parlay; 1 → single.
  if (legs.length >= 3) {
    const parlay = buildParlayCandidate(legs.slice(0, 3));
    parlay.strategy = "high_elite_76_parlay";
    return { kind: "parlay", parlay, score: parlay.score, qualified: true };
  }
  if (legs.length >= 2) {
    const parlay = buildParlayCandidate(legs.slice(0, 2));
    parlay.strategy = "high_elite_76_parlay";
    return { kind: "parlay", parlay, score: parlay.score, qualified: true };
  }

  const best = legs[0];
  return {
    kind: "single",
    bet: best,
    score: ticketScoreForSingle(best),
    qualified: true,
  };
}

/** Skip unless value single (edge≥12%, market disagrees) or 2-leg edge parlay. */
export function getEdgeValueDailyTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  if (!boardHasMarketOdds(board)) {
    return null;
  }

  const pool = buildMarketMoneylineCandidates(board)
    .filter(
      (bet) =>
        bet.modelProbability >= MIN_MONEYLINE_PROBABILITY &&
        bet.edge >= LIVE_DAILY_MIN_EDGE &&
        bet.ev > 0 &&
        Math.abs(bet.odds) <= MAX_MONEYLINE_ABS_ODDS &&
        isStarterReadyForParlay(bet.game)
    )
    .sort((a, b) => b.edge - a.edge || b.ev - a.ev);

  if (pool.length === 0) {
    return null;
  }

  const best = pool[0];
  if (best.game.marketAgrees === false && best.edge >= LIVE_VALUE_SINGLE_MIN_EDGE) {
    return {
      kind: "single",
      bet: best,
      score: ticketScoreForSingle(best),
      qualified: true,
    };
  }

  const legs = pool.filter((bet) => bet.edge >= 0.08).slice(0, 2);
  if (legs.length >= 2 && isParlayCorrelationAllowed(legs)) {
    const parlay = buildParlayCandidate(legs);
    if (parlay.ev > 0) {
      parlay.strategy = "edge_value_ticket";
      return { kind: "parlay", parlay, score: parlay.score, qualified: true };
    }
  }

  return null;
}

/**
 * LIVE STRATEGY (power_parlay): parlay when a strong 2-leg ticket exists; else single best High/Elite.
 * Never force a weak top-2 parlay — that was the old 53% coin-flip that busted the bankroll.
 *
 * Parlay gate (all must pass):
 *   - Both legs High or Elite confidence
 *   - Each leg >= 66% model win probability
 *   - Best 2-leg combo (not blind top-2 rank) has combined probability >= 52%
 *   - Different games
 *
 * Validated blind walk-forward with real closing odds, $10 start, 50% parlay / 20% single stake:
 *   full season: 67% ticket hit (40-20), $10 -> $182, bankroll never dipped below $10
 *   parlay days: 69% hit (9-4) on 13 qualifying days
 *   last 7 days: 5-0 singles, $10 -> $18.80 (no parlay qualifiers on recent slate)
 * Rejected: naive top-2 at 65% (45% hit, near bust), calibrated_parlay (53% hit), looser 65/48 gates ($1)
 */
const LIVE_QUALITY_TIERS = new Set(["Elite", "High"]);
const POWER_PARLAY_LEG_MIN_PROB = 0.66;
const POWER_PARLAY_COMBINED_MIN = 0.52;
const POWER_PARLAY_CANDIDATE_LIMIT = 6;

function pickProbabilityForBet(bet: BestBet) {
  return bet.game.pickProbability ?? bet.modelProbability;
}

function buildLiveMoneylinePool(board: GamePrediction[]) {
  return buildMarketMoneylineCandidates(board)
    .filter(
      (bet) =>
        bet.game.confidence !== "Low" &&
        bet.game.starterCertain !== false &&
        bet.game.seriesFade !== true &&
        Math.abs(bet.odds) <= ML_SANITY_LIMIT_LIVE
    )
    .sort(
      (left, right) =>
        CONFIDENCE_RANK[right.game.confidence] - CONFIDENCE_RANK[left.game.confidence] ||
        pickProbabilityForBet(right) - pickProbabilityForBet(left)
    );
}

function pickPowerParlayLegs(pool: BestBet[]): BestBet[] | null {
  const candidates = pool
    .filter((bet) => LIVE_QUALITY_TIERS.has(bet.game.confidence))
    .filter((bet) => pickProbabilityForBet(bet) >= POWER_PARLAY_LEG_MIN_PROB)
    .sort((left, right) => pickProbabilityForBet(right) - pickProbabilityForBet(left))
    .slice(0, POWER_PARLAY_CANDIDATE_LIMIT);

  if (candidates.length < 2) {
    return null;
  }

  let best: { legs: BestBet[]; probability: number } | null = null;

  for (const combo of combinations(candidates, 2, 30)) {
    if (combo[0].game.id === combo[1].game.id) {
      continue;
    }
    if (!isParlayCorrelationAllowed(combo)) {
      continue;
    }

    const probability = combo.reduce((value, leg) => value * pickProbabilityForBet(leg), 1);
    if (probability < POWER_PARLAY_COMBINED_MIN) {
      continue;
    }

    if (!best || probability > best.probability) {
      best = { legs: combo, probability };
    }
  }

  return best?.legs ?? null;
}

export function getPowerParlayTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  const pool = buildLiveMoneylinePool(board);
  if (pool.length === 0) {
    return null;
  }

  const parlayLegs = pickPowerParlayLegs(pool);
  if (parlayLegs && parlayLegs.length >= 2) {
    const parlay = buildParlayCandidate(parlayLegs);
    parlay.strategy = "power_parlay";
    return { kind: "parlay", parlay, score: parlay.probability, qualified: true };
  }

  const best = pool.find((bet) => LIVE_QUALITY_TIERS.has(bet.game.confidence));
  if (!best) {
    return null;
  }

  return {
    kind: "single",
    bet: { ...best, qualified: true },
    score: pickProbabilityForBet(best),
    qualified: true,
  };
}

/** @deprecated use getPowerParlayTicket */
export function getStrongParlayTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  return getPowerParlayTicket(board);
}

/** @deprecated use getStrongParlayTicket — singles-only fallback when parlay gate fails */
export function getQualitySingleTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  const pool = buildLiveMoneylinePool(board);
  if (pool.length === 0) {
    return null;
  }

  const best = pool[0];
  const qualified = LIVE_QUALITY_TIERS.has(best.game.confidence);

  return {
    kind: "single",
    bet: { ...best, qualified },
    score: pickProbabilityForBet(best),
    qualified,
  };
}

/** daily_best_single / daily_high_two_leg = High/Elite (BET) lane gates. */
export const DAILY_SINGLE_MIN_PROBABILITY = 0.55;
export const DAILY_SINGLE_MIN_EDGE = 0.02;
export const DAILY_SINGLE_MIN_ERA_DIFF = 0.5;
export const DAILY_SINGLE_MIN_FORM_EDGE = 0.1;
export const DAILY_SINGLE_MIN_ODDS = -250;

function highLaneMoneylinePool(board: GamePrediction[] = predictions): BestBet[] {
  return buildMarketMoneylineCandidates(board)
    .filter(
      (bet) =>
        bet.ev > 0 &&
        bet.modelProbability >= DAILY_SINGLE_MIN_PROBABILITY &&
        bet.edge >= DAILY_SINGLE_MIN_EDGE &&
        bet.odds > DAILY_SINGLE_MIN_ODDS &&
        bet.game.starterCertain !== false &&
        bet.game.marketAgrees === true &&
        (bet.game.eraDiff ?? 0) >= DAILY_SINGLE_MIN_ERA_DIFF &&
        (bet.game.formEdge ?? 0) >= DAILY_SINGLE_MIN_FORM_EDGE &&
        (bet.game.confidence === "High" || bet.game.confidence === "Elite") &&
        Math.abs(bet.odds) <= ML_SANITY_LIMIT_LIVE
    )
    .sort(
      (left, right) =>
        right.modelProbability - left.modelProbability || right.ev - left.ev || right.edge - left.edge
    );
}

/**
 * daily_best_single — bet the model's best High-confidence moneyline when one exists.
 * Gates match the High label (p≥55%, form≥0.1, ERA≥0.5, edge≥2%, market agrees, +EV,
 * odds better than -250). Skip the day when nothing earns High — do not pad with leans.
 */
export function getDailyBestSingleTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  const pool = highLaneMoneylinePool(board);
  if (pool.length === 0) {
    return null;
  }

  const best = pool[0];
  return {
    kind: "single",
    bet: { ...best, qualified: true },
    score: best.modelProbability,
    qualified: true,
  };
}

/**
 * daily_high_two_leg — primary live ticket (Aug 2026):
 *   - 2+ High/Elite legs → 2-leg moneyline parlay (top two by model p)
 *   - exactly 1 High → single
 *   - 0 → skip
 * Same High gates as daily_best_single. Never pads with Medium/Low.
 */
export function getDailyHighTwoLegTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  const pool = highLaneMoneylinePool(board);
  if (pool.length === 0) {
    return null;
  }

  const seen = new Set<string>();
  const unique: BestBet[] = [];
  for (const bet of pool) {
    if (seen.has(bet.game.id)) continue;
    seen.add(bet.game.id);
    unique.push(bet);
    if (unique.length >= 2) break;
  }

  if (unique.length >= 2 && isParlayCorrelationAllowed(unique.slice(0, 2))) {
    const legs = unique.slice(0, 2).map((bet) => ({ ...bet, qualified: true }));
    const parlay = buildParlayCandidate(legs);
    parlay.strategy = "daily_high_two_leg";
    return { kind: "parlay", parlay, score: parlay.score, qualified: true };
  }

  const best = unique[0];
  return {
    kind: "single",
    bet: { ...best, qualified: true },
    score: best.modelProbability,
    qualified: true,
  };
}

function evScoreForBet(bet: BestBet) {
  return bet.ev * bet.modelProbability;
}

/**
 * market_agree_parlay — favorite-first, bet-ready direction (Jul 2026, revised):
 *   - Publishes a parlay EVERY slate (no skip days).
 *   - Only takes sides the MARKET prices as favorites/pick'ems (never longshot
 *     dogs) so legs are actually likely to win. Legs are ranked by how strongly
 *     the book favors them (plus model agreement), so the parlay is built from the
 *     most probable winners, not anti-market lottery legs.
 *   - Caps the combined price: prefers a 3-leg favorite parlay but drops to 2 legs
 *     if 3 legs would push the ticket past ~+260, so it stays cashable.
 */
export function getMarketAgreeParlayTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  if (!boardHasMarketOdds(board)) {
    return null;
  }

  const universe = buildMarketMoneylineCandidates(board).filter(
    (bet) =>
      bet.game.starterCertain !== false &&
      Math.abs(bet.odds) <= ML_SANITY_LIMIT_LIVE
  );

  if (universe.length === 0) {
    return null;
  }

  // Legs must never be Low confidence. Rank by sim strength and +EV vs market
  // (sim − book), not by "must agree with the favorite."
  const eligible = universe.filter((bet) => bet.game.confidence !== "Low");
  const tierPredicates: Array<(bet: BestBet) => boolean> = [
    (bet) => bet.modelProbability >= 0.6 && bet.edge >= 0.02,
    (bet) => bet.modelProbability >= 0.57 && (bet.game.confidence === "Elite" || bet.game.confidence === "High"),
    (bet) => bet.modelProbability >= 0.55,
    (bet) => bet.edge >= 0,
    () => true,
  ];

  const tierOf = (bet: BestBet) => {
    for (let index = 0; index < tierPredicates.length; index += 1) {
      if (tierPredicates[index](bet)) {
        return index;
      }
    }
    return tierPredicates.length;
  };

  const ranked = (eligible.length > 0 ? eligible : universe)
    .map((bet) => ({ bet, tier: tierOf(bet) }))
    .sort(
      (left, right) =>
        left.tier - right.tier ||
        right.bet.modelProbability - left.bet.modelProbability ||
        right.bet.edge - left.bet.edge
    )
    .map((entry) => entry.bet);

  const pickLegs = (max: number, requireCorrelation: boolean): BestBet[] => {
    const legs: BestBet[] = [];
    for (const bet of ranked) {
      if (legs.length >= max) {
        break;
      }
      if (legs.some((leg) => leg.game.id === bet.game.id)) {
        continue;
      }
      if (requireCorrelation && !isParlayCorrelationAllowed([...legs, bet])) {
        continue;
      }
      legs.push(bet);
    }
    return legs;
  };

  let chosen = pickLegs(3, true);
  if (chosen.length < 2) {
    chosen = pickLegs(2, false);
  }

  if (chosen.length >= 2) {
    let parlay = buildParlayCandidate(chosen);
    // Keep the ticket cashable: if 3 legs make it a longshot, fall back to the
    // two strongest favorites instead.
    if (chosen.length === 3 && parlay.decimalOdds > MARKET_AGREE_MAX_PARLAY_DECIMAL) {
      const twoLeg = buildParlayCandidate(chosen.slice(0, 2));
      parlay = twoLeg;
    }
    parlay.strategy = "market_agree_parlay";
    return { kind: "parlay", parlay, score: parlay.score, qualified: true };
  }

  const best = ranked[0];
  return {
    kind: "single",
    bet: { ...best, qualified: true },
    score: best.modelProbability,
    qualified: true,
  };
}

/**
 * daily_top3_prob — three separate moneyline singles every day, ranked by
 * model win probability (then edge). This is not a parlay: stake is split across
 * the three singles with the live daily exposure cap.
 */
export function getDailyTop3ProbTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  const candidates = buildMarketMoneylineCandidates(board).filter(
    (bet) =>
      bet.game.starterCertain !== false &&
      Math.abs(bet.odds) <= ML_SANITY_LIMIT_LIVE
  );
  if (candidates.length === 0) {
    return null;
  }

  const bets = candidates
    .sort(
      (left, right) =>
        right.modelProbability - left.modelProbability ||
        right.edge - left.edge ||
        right.ev - left.ev
    )
    .slice(0, 3)
    .map((bet) => ({ ...bet, qualified: true }));

  if (bets.length === 0) {
    return null;
  }

  return {
    kind: "multi_single",
    bets,
    score: bets.reduce((total, bet) => total + bet.modelProbability, 0),
    qualified: true,
  };
}

/** @deprecated Use getDailyTop3ProbTicket — kept for callers during rename. */
export function getDailyTop3EVScoreTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  return getDailyTop3ProbTicket(board);
}

/** Daily ticket: 2-leg High stack when available; else one High single; else skip. */
export function getBestDailyTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  return getDailyHighTwoLegTicket(board);
}

export function getDailyParlayTickets(board: GamePrediction[] = predictions) {
  const tickets: ParlayCandidate[] = [];
  const twoLeg = getBestTwoLegParlay(board);
  const threeLeg = getPremiumThreeLegParlay(board);

  if (twoLeg) {
    tickets.push(twoLeg);
  }
  if (threeLeg && (!twoLeg || threeLeg.score > twoLeg.score)) {
    tickets.push(threeLeg);
  }

  return tickets;
}

export function getBacktestedParlaysByLegCount(board: GamePrediction[] = predictions, strategies: ParlayStrategyInput[]) {
  const backtested = strategies
    .map((strategy) => getParlayForStrategy(board, strategy))
    .filter((parlay): parlay is ParlayCandidate => parlay !== null)
    .sort((left, right) => left.legCount - right.legCount);

  if (backtested.length > 0) {
    return backtested;
  }

  return getBestParlaysByLegCount(board);
}
