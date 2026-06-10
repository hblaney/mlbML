import { execFile } from "child_process";
import { readFile } from "fs/promises";
import path from "path";
import { promisify } from "util";
import { GamePrediction, normalizeTeamId } from "./data";

const execFileAsync = promisify(execFile);
const canRunLocalGenerators = process.env.VERCEL !== "1";
const autoRegenerateBoard = process.env.AUTO_REGENERATE_BOARD === "1";

export type AccuracyOutput = {
  generated_at: string;
  evaluated_games: number;
  overall_accuracy: number;
  brier_score: number;
  days_at_or_above_60pct: number;
  weeks_at_or_above_60pct: number;
  daily_accuracy: Record<string, number>;
  weekly_accuracy: Record<string, number>;
  recent_predictions: PredictionHistoryRow[];
  prediction_history?: PredictionHistoryRow[];
};

export type PredictionHistoryRow = {
  date: string;
  startsAt?: string;
  gamePk?: number;
  home: string;
  away: string;
  probability: number;
  pickProbability?: number;
  confidence?: "Low" | "Medium" | "High" | "Elite";
  predicted?: string;
  actual?: string;
  correct: number;
};

export type ParlayBacktestStrategy = {
  leg_count: number;
  min_edge: number;
  min_probability: number;
  top_n: number;
  bets: number;
  wins: number;
  losses: number;
  hit_rate: number;
  profit: number;
  roi: number;
  avg_model_probability: number;
  avg_ev: number;
};

export type SingleBacktestStrategy = {
  min_edge: number;
  min_probability: number;
  max_abs_odds: number;
  bets: number;
  wins: number;
  losses: number;
  hit_rate: number;
  profit: number;
  roi: number;
  avg_ev: number;
};

export type ParlayBacktestOutput = {
  generated_at: string;
  date_range: { start: string; end: string };
  odds_metadata?: {
    odds_data_start: string | null;
    odds_data_end: string | null;
    odds_data_stale: boolean;
    limited_by: string;
  };
  stake: number;
  historical_games: number;
  model_prediction_rows: number;
  days_with_candidates: number;
  best_single_strategies?: SingleBacktestStrategy[];
  recommended_single_strategy?: SingleBacktestStrategy;
  best_by_leg_count: ParlayBacktestStrategy[];
  recommended_by_leg_count?: ParlayBacktestStrategy[];
};

export async function loadAccuracyOutput(): Promise<AccuracyOutput | null> {
  try {
    const filePath = path.join(process.cwd(), "public", "accuracy.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as AccuracyOutput;
  } catch {
    return null;
  }
}

export async function loadParlayBacktest(): Promise<ParlayBacktestOutput | null> {
  try {
    const filePath = path.join(process.cwd(), "public", "parlay-backtest.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as ParlayBacktestOutput;
  } catch {
    return null;
  }
}

type PredictionOutputRow = Partial<GamePrediction> & {
  date?: string;
  awayTeam: string;
  homeTeam: string;
};

type PredictionBoardFile = {
  generated_at?: string;
  trained_through?: string;
  predictions?: PredictionOutputRow[];
};

function isFreshBoard(payload: PredictionBoardFile, rows: PredictionOutputRow[]) {
  const today = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  const boardIsToday = rows.length > 0 && rows.every((row) => (row.date ?? row.startsAt?.slice(0, 10)) === today);
  const generatedToday = payload.generated_at === today;
  const trainedThroughYesterday = payload.trained_through === yesterday;
  return boardIsToday && generatedToday && trainedThroughYesterday;
}

async function readPredictionBoard(): Promise<{ payload: PredictionBoardFile; rows: PredictionOutputRow[] }> {
  const filePath = path.join(process.cwd(), "public", "predictions.json");
  const raw = await readFile(filePath, "utf8");
  const parsed = JSON.parse(raw) as PredictionBoardFile | PredictionOutputRow[];

  if (Array.isArray(parsed)) {
    return { payload: {}, rows: parsed };
  }

  const rows = Array.isArray(parsed.predictions) ? parsed.predictions : [];
  return { payload: parsed, rows };
}

async function generateTodayBoard() {
  if (!canRunLocalGenerators) {
    return;
  }

  try {
    await execFileAsync("python3", ["scripts/model/generate_today_board.py"], {
      cwd: process.cwd(),
      timeout: 120_000
    });
  } catch {
    // Keep the page render resilient if Python or the MLB API is unavailable.
  }
}

function normalizePredictionRows(rows: PredictionOutputRow[]): GamePrediction[] {
  return rows.map((row) => {
    const awayTeam = normalizeTeamId(row.awayTeam);
    const homeTeam = normalizeTeamId(row.homeTeam);
    const homeProbability = row.modelHomeWinProbability ?? 0.5;
    const awayProbability = row.modelAwayWinProbability ?? 1 - homeProbability;
    const pickProbability = row.pickProbability ?? Math.max(homeProbability, awayProbability);
    const predictedTeam = row.predictedTeam ?? (homeProbability >= awayProbability ? homeTeam : awayTeam);

    return {
      id: row.id ?? `${awayTeam}-${homeTeam}-${row.startsAt ?? "today"}`,
      startsAt: row.startsAt ?? new Date().toISOString(),
      awayTeam,
      homeTeam,
      awayPitcher: row.awayPitcher ?? "TBD",
      homePitcher: row.homePitcher ?? "TBD",
      predictedTeam,
      pickProbability,
      modelHomeWinProbability: homeProbability,
      modelAwayWinProbability: awayProbability,
      homeMoneyline: row.homeMoneyline ?? null,
      awayMoneyline: row.awayMoneyline ?? null,
      homeRunline: row.homeRunline ?? null,
      awayRunline: row.awayRunline ?? null,
      homeRunlinePrice: row.homeRunlinePrice ?? null,
      awayRunlinePrice: row.awayRunlinePrice ?? null,
      marketTotal: row.marketTotal ?? null,
      overPrice: row.overPrice ?? null,
      underPrice: row.underPrice ?? null,
      projectedTotal: row.projectedTotal ?? null,
      oddsSource: row.oddsSource ?? null,
      confidence: row.confidence ?? "Low",
      modelVersion: row.modelVersion ?? "daily-model",
      explanation: row.explanation ?? [
        "Generated by the daily model output",
        "Odds default to neutral when live lines are unavailable",
        "Refresh the page to pick up newly generated board data"
      ]
    };
  }).sort((left, right) => (right.pickProbability ?? 0) - (left.pickProbability ?? 0));
}

export async function loadPredictionBoard(): Promise<GamePrediction[]> {
  try {
    let { payload, rows } = await readPredictionBoard();

    if (!isFreshBoard(payload, rows) && autoRegenerateBoard) {
      await generateTodayBoard();
      ({ payload, rows } = await readPredictionBoard());
    }

    return normalizePredictionRows(rows);
  } catch {
    if (autoRegenerateBoard) {
      await generateTodayBoard();
    }
    try {
      const { rows } = await readPredictionBoard();
      return normalizePredictionRows(rows);
    } catch {
      return [];
    }
  }
}

type PredictionHistoryOutput = {
  generated_at: string;
  trained_through?: string;
  predictions: PredictionHistoryRow[];
};

async function generatePredictionHistory() {
  if (!canRunLocalGenerators) {
    return;
  }

  try {
    await execFileAsync("python3", ["scripts/model/generate_prediction_history.py"], {
      cwd: process.cwd(),
      timeout: 120_000
    });
  } catch {
    // The History page can still fall back to accuracy.json if this fails.
  }
}

async function readPredictionHistory(): Promise<PredictionHistoryOutput | null> {
  try {
    const filePath = path.join(process.cwd(), "public", "prediction-history.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as PredictionHistoryOutput;
  } catch {
    return null;
  }
}

export async function loadFullPredictionHistory(): Promise<PredictionHistoryRow[]> {
  const today = new Date().toISOString().slice(0, 10);
  let output = await readPredictionHistory();

  const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  if (
    !output ||
    output.generated_at !== today ||
    output.trained_through !== yesterday ||
    !Array.isArray(output.predictions) ||
    output.predictions.some((row) => !row.actual || row.date >= today)
  ) {
    await generatePredictionHistory();
    output = await readPredictionHistory();
  }

  return output?.predictions ?? [];
}
