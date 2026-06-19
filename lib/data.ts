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
  /** False when a probable starter is TBD or changed since the last board refresh. */
  starterCertain?: boolean;
  pitcherChanged?: boolean;
  /** True when the model pick lost its last 2 games vs this opponent — parlay leg blocked. */
  seriesFade?: boolean;
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

const MIN_MONEYLINE_PROBABILITY = 0.62;
const MIN_MONEYLINE_EDGE = 0.08;
const MAX_MONEYLINE_ABS_ODDS = 180;
const BEST_AVAILABLE_MONEYLINE_COUNT = 5;
const BEST_AVAILABLE_MIN_EDGE = 0.04;
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
    if (marketBets.length > 0) {
      return marketBets.slice(0, BEST_AVAILABLE_MONEYLINE_COUNT);
    }
  }

  const modelBets = buildModelOnlyMoneylineBets(board).filter((bet) => bet.qualified);
  if (modelBets.length > 0) {
    return modelBets;
  }

  return [];
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

const SAFE_PARLAY_MIN_LEG_PROBABILITY = 0.65;
const SAFE_PARLAY_MIN_LEG_EDGE = 0.05;
const SAFE_PARLAY_MIN_BOOK_PROBABILITY = 0.50;
/** Live site parlays: stricter legs than backtest pool — no forced pairings. */
const LIVE_PARLAY_MIN_LEG_EDGE = 0.06;
const LIVE_PARLAY_MIN_BOOK_PROBABILITY = 0.50;
const LIVE_PARLAY_HIGH_ELITE_MIN_PROBABILITY = 0.62;
const LIVE_PARLAY_MEDIUM_MIN_PROBABILITY = 0.68;
const LIVE_PARLAY_MIN_COMBINED_PROBABILITY_2 = 0.38;
const LIVE_PARLAY_MIN_COMBINED_PROBABILITY_3 = 0.28;
const LIVE_PARLAY_MIN_HIGH_ELITE_LEGS_2 = 1;
const LIVE_PARLAY_MIN_HIGH_ELITE_LEGS_3 = 2;
const ANCHOR_PARLAY_MIN_CONFIDENCE_PROBABILITY = 0.645;
const ANCHOR_PARLAY_MIN_BOOK_PROBABILITY = 0.50;
const ANCHOR_PARLAY_MIN_LEG_EV = -2;
const PREMIUM_PARLAY_MIN_COMBINED_PROBABILITY = 0.30;
const PREMIUM_PARLAY_MIN_HIGH_ELITE_LEGS = 2;
const PREMIUM_4LEG_MIN_COMBINED_PROBABILITY = 0.15;
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
  if (game.starterCertain === false || game.pitcherChanged === true) {
    return false;
  }
  if (USE_PARLAY_CORRELATION_FILTER && game.seriesFade === true) {
    return false;
  }
  return true;
}

/** When 2+ Medium+ picks reach this win%, force top-2 parlay (season walk-forward +$39 @ $5 flat vs prior). */
export const MED60_FORCE_PARLAY_MIN_PROBABILITY = 0.60;

/** Live plan: med60 force-2 overlay on no_low_parlay_223s fallback. */
export const LIVE_BETTING_STRATEGY = "med60_force2_223s";
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
  strategy?: "edge" | "anchor" | "premium" | "premium_4" | "forced_top_2" | "live_quality" | "live_premium" | "med60_top2";
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
  const legKey = ticket.kind === "single" ? "1" : String(ticket.parlay.legCount);
  const fromPlan = stakeByLeg?.[legKey];
  if (fromPlan != null) {
    return fromPlan;
  }
  if (ticket.kind === "single") {
    return OPTIMIZED_STAKE_BY_LEG_COUNT[1];
  }
  return OPTIMIZED_STAKE_BY_LEG_COUNT[ticket.parlay.legCount] ?? OPTIMIZED_GROWTH_STAKE_PCT;
}

export type DailyTicket =
  | {
      kind: "single";
      bet: BestBet;
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
  const qualified = buildMarketMoneylineBets(board).sort(
    (left, right) => (right.ev * right.modelProbability) - (left.ev * left.modelProbability)
  );
  if (qualified.length > 0) {
    return qualified[0];
  }

  const available = buildBestAvailableMarketMoneylineBets(board)
    .filter((bet) => bet.ev > 0)
    .sort((left, right) => (right.ev * right.modelProbability) - (left.ev * left.modelProbability));

  return available[0] ?? null;
}

function ticketScoreForSingle(bet: BestBet) {
  return bet.ev * bet.modelProbability;
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

/** Top two Medium+ model picks at or above MED60 threshold, by win probability. */
export function getMed60ForceTwoLegParlay(board: GamePrediction[] = predictions): ParlayCandidate | null {
  if (!boardHasMarketOdds(board)) {
    return null;
  }

  const legs: BestBet[] = [];
  const seenGames = new Set<string>();

  for (const bet of buildMarketMoneylineCandidates(board)
    .filter(
      (candidate) =>
        isParlayEligibleConfidence(candidate.game.confidence) &&
        candidate.modelProbability >= MED60_FORCE_PARLAY_MIN_PROBABILITY
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
  candidate.strategy = "med60_top2";
  return candidate;
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

  return options.sort((left, right) => right.score - left.score)[0];
}

/** no_low_parlay_223s: always-2, premium 3-leg, or single — highest score wins one bet. */
export function getNoLowParlay223sTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  return getTwoOrThreeOrSingleTicket(board);
}

/** med60_force2_223s: force top-2 parlay when 2+ Medium+ picks >= 60%; else no_low_parlay_223s. */
export function getMed60ForceTwo223sTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  const forced = getMed60ForceTwoLegParlay(board);
  if (forced) {
    return { kind: "parlay", parlay: forced, score: forced.score, qualified: true };
  }
  return getNoLowParlay223sTicket(board);
}

/** Daily ticket: one system bet per day. */
export function getBestDailyTicket(board: GamePrediction[] = predictions): DailyTicket | null {
  return getMed60ForceTwo223sTicket(board);
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
