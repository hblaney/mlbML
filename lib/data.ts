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
  startsAt: string;
  awayTeam: string;
  homeTeam: string;
  awayPitcher: string;
  homePitcher: string;
  predictedTeam?: string;
  pickProbability?: number;
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
  modelVersion: string;
  explanation: string[];
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

export type AccuracySnapshot = {
  range: string;
  record: string;
  accuracy: number;
  units: number;
  brierScore: number;
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

export const accuracySnapshots: AccuracySnapshot[] = [
  { range: "Yesterday", record: "8-5", accuracy: 0.615, units: 1.7, brierScore: 0.218 },
  { range: "Last 7 Days", record: "51-34", accuracy: 0.6, units: 5.2, brierScore: 0.226 },
  { range: "Season", record: "412-304", accuracy: 0.575, units: 18.4, brierScore: 0.234 }
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

const MIN_MONEYLINE_PROBABILITY = 0.55;
const MIN_MONEYLINE_EDGE = 0.04;
const MAX_MONEYLINE_ABS_ODDS = 180;
const BEST_AVAILABLE_MONEYLINE_COUNT = 5;
const BEST_AVAILABLE_MIN_EDGE = 0.01;
const BEST_AVAILABLE_MAX_ABS_ODDS = 220;
const MODEL_ONLY_MIN_PROBABILITY = 0.55;
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

function buildMarketMoneylineCandidates(board: GamePrediction[]) {
  return board
    .filter((game) => game.homeMoneyline !== null && game.awayMoneyline !== null)
    .flatMap((game) => {
      const away = getTeam(game.awayTeam);
      const home = getTeam(game.homeTeam);
      const matchup = `${away.abbreviation} @ ${home.abbreviation}`;
      const homeMarket = impliedProbability(game.homeMoneyline as number);
      const awayMarket = impliedProbability(game.awayMoneyline as number);
      const marketTotal = homeMarket + awayMarket;
      const homeNoVig = homeMarket / marketTotal;
      const awayNoVig = awayMarket / marketTotal;

      return [
        {
          id: `${game.id}-home`,
          game,
          team: home,
          opponent: away,
          matchup,
          side: "Moneyline",
          odds: game.homeMoneyline as number,
          modelProbability: game.modelHomeWinProbability,
          bookProbability: homeNoVig,
          ev: expectedValue(game.modelHomeWinProbability, game.homeMoneyline as number)
        },
        {
          id: `${game.id}-away`,
          game,
          team: away,
          opponent: home,
          matchup,
          side: "Moneyline",
          odds: game.awayMoneyline as number,
          modelProbability: game.modelAwayWinProbability,
          bookProbability: awayNoVig,
          ev: expectedValue(game.modelAwayWinProbability, game.awayMoneyline as number)
        }
      ];
    })
    .map((bet) => ({ ...bet, edge: bet.modelProbability - bet.bookProbability }));
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
    .sort((a, b) => b.edge - a.edge);
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
  if (boardHasMarketOdds(board)) {
    const marketBets = buildMarketMoneylineBets(board);
    const excludedIds = new Set(marketBets.map((bet) => bet.id));
    const fallbackBets = buildBestAvailableMarketMoneylineBets(board, excludedIds);
    const combined = [...marketBets, ...fallbackBets].slice(0, BEST_AVAILABLE_MONEYLINE_COUNT);
    if (combined.length > 0) {
      return combined;
    }
  }

  const modelBets = buildModelOnlyMoneylineBets(board);
  if (modelBets.length > 0) {
    return modelBets;
  }

  const fallback = topModelOnlyMoneylineBet(board);
  return fallback ? [fallback] : [];
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

const SAFE_PARLAY_MIN_LEG_PROBABILITY = 0.58;
const SAFE_PARLAY_MIN_BOOK_PROBABILITY = 0.48;
const SAFE_PARLAY_MAX_LEGS = 4;
const DAILY_PARLAY_LEG_COUNTS = [3, 4] as const;

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

export function getParlayCandidates(board: GamePrediction[] = predictions, stake = 100) {
  const singles = getBestBets(board)
    .filter(
      (bet) =>
        bet.modelProbability >= SAFE_PARLAY_MIN_LEG_PROBABILITY &&
        (bet.modelOnly || bet.bookProbability >= SAFE_PARLAY_MIN_BOOK_PROBABILITY)
    )
    .sort((left, right) => (right.ev * right.modelProbability) - (left.ev * left.modelProbability))
    .slice(0, 8);

  const parlays: ParlayCandidate[] = [];
  const maxLegs = Math.min(SAFE_PARLAY_MAX_LEGS, singles.length);

  for (let legCount = 2; legCount <= maxLegs; legCount += 1) {
    const combos = combinations(singles, legCount);
    for (const legs of combos) {
      const uniqueGames = new Set(legs.map((leg) => leg.game.id));
      if (uniqueGames.size !== legs.length) {
        continue;
      }

      const candidate = buildParlayCandidate(legs, stake);
      const allModelOnly = legs.every((leg) => leg.modelOnly);

      if (candidate.ev <= 0 && !allModelOnly) {
        continue;
      }

      if (allModelOnly && candidate.probability < 0.32) {
        continue;
      }

      parlays.push(candidate);
    }
  }

  if (parlays.length === 0) {
    const fallback = buildFallbackParlay(singles, stake);
    if (fallback) {
      parlays.push(fallback);
    }
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
  if (results.length > 0) {
    return results;
  }

  const singles = getBestBets(board).slice(0, 8);
  const fallback = buildFallbackParlay(singles);
  return fallback ? [fallback] : [];
}

export function getParlayForStrategy(board: GamePrediction[] = predictions, strategy: ParlayStrategyInput) {
  if (strategy.leg_count < 2) {
    return null;
  }

  const minProbability = Math.max(strategy.min_probability, SAFE_PARLAY_MIN_LEG_PROBABILITY);
  const singles = getBestBets(board)
    .filter(
      (bet) =>
        bet.edge >= strategy.min_edge &&
        bet.modelProbability >= minProbability &&
        (bet.modelOnly || bet.bookProbability >= SAFE_PARLAY_MIN_BOOK_PROBABILITY)
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

    const candidate = buildParlayCandidate(legs);
    const allModelOnly = legs.every((leg) => leg.modelOnly);

    if (candidate.ev <= 0 && !allModelOnly) {
      continue;
    }

    if (allModelOnly && candidate.probability < 0.32) {
      continue;
    }

    if (!best || candidate.score > best.score) {
      best = candidate;
    }
  }

  return best;
}

export function getDailyParlayTickets(board: GamePrediction[] = predictions) {
  const singles = getBestBets(board)
    .filter(
      (bet) =>
        bet.modelProbability >= SAFE_PARLAY_MIN_LEG_PROBABILITY &&
        (bet.modelOnly || bet.bookProbability >= SAFE_PARLAY_MIN_BOOK_PROBABILITY)
    )
    .sort((left, right) => (right.ev * right.modelProbability) - (left.ev * left.modelProbability))
    .slice(0, 8);

  const tickets: ParlayCandidate[] = [];

  for (const legCount of DAILY_PARLAY_LEG_COUNTS) {
    if (singles.length < legCount) {
      continue;
    }

    let best: ParlayCandidate | null = null;
    for (const legs of combinations(singles, legCount)) {
      const uniqueGames = new Set(legs.map((leg) => leg.game.id));
      if (uniqueGames.size !== legs.length) {
        continue;
      }

      const candidate = buildParlayCandidate(legs);
      if (candidate.ev <= 0 && !legs.every((leg) => leg.modelOnly)) {
        continue;
      }
      if (!best || candidate.score > best.score) {
        best = candidate;
      }
    }

    if (best) {
      tickets.push(best);
    }
  }

  if (tickets.length > 0) {
    return tickets;
  }

  return getBestParlaysByLegCount(board).filter((parlay) => parlay.legCount === 3 || parlay.legCount === 4);
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
