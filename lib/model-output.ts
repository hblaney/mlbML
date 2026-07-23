import { execFile } from "child_process";
import { readFile } from "fs/promises";
import path from "path";
import { promisify } from "util";
import { GamePrediction, normalizeTeamId } from "./data";
import { assertConfidenceMatchesPick, confidenceFromPickProbability } from "./confidence";

const execFileAsync = promisify(execFile);
const canRunLocalGenerators = process.env.VERCEL !== "1";
const autoRegenerateBoard = process.env.AUTO_REGENERATE_BOARD === "1";

type ConfidenceBand = {
  bets: number;
  wins: number;
  losses: number;
  hit_rate: number | null;
};

export type AccuracyOutput = {
  generated_at: string;
  trained_through?: string;
  season?: string;
  evaluated_games: number;
  overall_accuracy: number;
  current_season?: {
    season: string;
    market_backed_games: number;
    market_backed_accuracy: number;
    high_confidence_games: number;
    high_confidence_accuracy: number;
    daily_accuracy: Record<string, number>;
  };
  by_confidence?: {
    Elite: ConfidenceBand;
    High: ConfidenceBand;
    Medium: ConfidenceBand;
    Low: ConfidenceBand;
  };
  last_7_days?: ConfidenceBand;
  yesterday?: ConfidenceBand;
  archive?: {
    evaluated_games: number;
    overall_accuracy: number;
  };
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
  marketBacked?: boolean;
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

export type RecommendationBetLeg = {
  team: string;
  matchup: string;
  odds: number;
  model_probability: number;
  book_probability: number;
  edge: number;
  won: boolean;
};

export type RecommendedBetRow = {
  category: "moneyline" | "advanced" | "parlay_2" | "parlay_3" | "parlay_4";
  date: string;
  gamePk?: number;
  matchup: string;
  team: string;
  side: string;
  label: string;
  odds: number;
  model_probability: number;
  book_probability: number | null;
  edge: number | null;
  ev: number;
  stake: number;
  qualified: boolean;
  won: boolean;
  profit: number;
  legs?: RecommendationBetLeg[];
};

export type RecommendationSummary = {
  bets: number;
  wins: number;
  losses: number;
  staked: number;
  profit: number;
  roi: number;
  hit_rate: number;
};

export type DailyRecommendationSnapshot = {
  date: string;
  bets: RecommendedBetRow[];
  summary: RecommendationSummary;
};

export type RecommendationPerformanceOutput = {
  generated_at: string;
  stake: number;
  starting_bankroll: number;
  date_range: { start: string; end: string };
  odds_metadata?: {
    odds_data_start: string | null;
    odds_data_end: string | null;
    odds_data_stale: boolean;
    limited_by: string;
  };
  strategy: {
    moneyline: {
      qualified_min_edge: number;
      qualified_min_probability: number;
      qualified_max_abs_odds: number;
      fallback_min_edge: number;
    };
    advanced: { market: string; min_edge: number };
    parlay: {
      leg_counts: number[];
      qualified_min_edge: number;
      qualified_min_probability: number;
      qualified_min_book_probability: number;
      top_n: number;
    };
  };
  by_category: Record<string, RecommendationSummary>;
  weekly: Record<string, RecommendationSummary>;
  monthly: Record<string, RecommendationSummary>;
  cumulative: {
    bets: number;
    profit: number;
    roi: number;
    balance: number;
    return_pct: number;
  };
  checkpoints: Array<{
    date: string;
    profit: number;
    balance: number;
    return_pct: number;
  }>;
  daily: DailyRecommendationSnapshot[];
};

export type Parlay2CompoundBet = RecommendedBetRow & {
  strategy?: "edge" | "anchor";
  legs: RecommendationBetLeg[];
};

export type Parlay2CompoundBacktestOutput = {
  generated_at: string;
  method: string;
  strategy: string;
  recommended_stake_pct: number;
  date_range: { start: string; end: string };
  odds_metadata?: RecommendationPerformanceOutput["odds_metadata"];
  criteria: {
    edge_leg_min_edge: number;
    edge_leg_min_model_probability: number;
    edge_leg_min_book_probability: number;
    edge_leg_positive_ev: boolean;
    anchor_leg_confidence: string[];
    anchor_leg_min_model_probability: number;
    anchor_leg_min_book_probability: number;
    anchor_leg_min_ev: number;
    ticket_must_have_positive_ev: boolean;
    legs_must_be_different_games: boolean;
    selection_score: string;
  };
  coverage: {
    game_days_with_candidates: number;
    qualifying_parlay_days: number;
    qualifying_rate: number;
    estimated_season_games_played: number;
    estimated_season_progress_pct: number;
  };
  flat_stake: number;
  flat_summary: RecommendationSummary;
  by_strategy: Record<
    string,
    {
      bets: number;
      wins: number;
      losses: number;
      flat_profit: number;
    }
  >;
  compound_scenarios: Array<{
    stake_pct: number;
    starting_bankroll: number;
    to_date: {
      bets: number;
      end: number;
      profit: number;
      return_pct: number;
      min_bankroll: number;
    };
    full_season_projection: {
      estimated_total_bets: number;
      estimated_season_progress_pct: number;
      end: number;
      profit: number;
      return_pct: number;
      note: string;
    };
  }>;
  bets: Parlay2CompoundBet[];
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

export type LiveModelPerformanceOutput = {
  generated_at: string;
  trained_through?: string;
  model_version?: string | null;
  season: string;
  method: string;
  stake: number;
  starting_bankroll: number;
  baseline_odds: number;
  date_range: { start: string | null; end: string | null };
  overall: RecommendationSummary;
  high_confidence: RecommendationSummary;
  by_confidence?: {
    Elite: { bets: number; wins: number; losses: number; hit_rate: number | null };
    High: { bets: number; wins: number; losses: number; hit_rate: number | null };
    Medium: { bets: number; wins: number; losses: number; hit_rate: number | null };
    Low: { bets: number; wins: number; losses: number; hit_rate: number | null };
  };
  last_7_days?: { bets: number; wins: number; losses: number; hit_rate: number | null };
  yesterday?: { bets: number; wins: number; losses: number; hit_rate: number | null };
  cumulative: RecommendationPerformanceOutput["cumulative"];
  checkpoints: RecommendationPerformanceOutput["checkpoints"];
  daily: Array<{
    date: string;
    games: number;
    accuracy: number;
    high_confidence: RecommendationSummary;
  }>;
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

export type ClvSummary = {
  n: number;
  beat_close_rate?: number;
  avg_clv?: number;
  avg_clv_pct_points?: number;
  win_rate?: number | null;
  win_rate_when_beat_close?: number | null;
  win_rate_when_missed_close?: number | null;
};

export type ClvOutput = {
  generated_from: string;
  note: string;
  overall: ClvSummary;
  by_confidence: Record<"Elite" | "High" | "Medium" | "Low", ClvSummary>;
  recent: Array<{
    date: string;
    pick: string;
    confidence: string | null;
    correct: number | null;
    entry_ml: number;
    close_ml: number;
    clv: number;
    beat_close: boolean;
  }>;
};

export async function loadClvOutput(): Promise<ClvOutput | null> {
  try {
    const filePath = path.join(process.cwd(), "public", "clv.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as ClvOutput;
  } catch {
    return null;
  }
}

export type HealthWindow = {
  n: number;
  accuracy: number;
  brier: number;
  log_loss: number;
  auc: number;
  ece: number;
  status: "healthy" | "watch" | "degraded";
};

export type ModelHealth = {
  generated_at: string;
  live_probability_key: string;
  overall_status: "healthy" | "watch" | "degraded" | "unknown";
  primary_universe?: string;
  primary_window?: string;
  recent_status?: "healthy" | "watch" | "degraded" | null;
  recent_trend: {
    last30_accuracy: number | null;
    last30_high_elite_accuracy: number | null;
    last30_high_elite_n: number;
    season_accuracy: number | null;
    season_high_elite_accuracy: number | null;
    season_high_elite_n: number;
    note: string;
  };
  windows: Record<string, HealthWindow>;
  windows_all_picks?: Record<string, HealthWindow>;
  recalibration: {
    verdict: string;
    holdout_n?: number;
    raw_log_loss?: number;
    recal_log_loss?: number;
    raw_ece?: number;
    recal_ece?: number;
  };
  note: string;
};

export async function loadModelHealth(): Promise<ModelHealth | null> {
  try {
    const filePath = path.join(process.cwd(), "public", "model-health.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as ModelHealth;
  } catch {
    return null;
  }
}

export async function loadRecommendationPerformance(): Promise<RecommendationPerformanceOutput | null> {
  try {
    const filePath = path.join(process.cwd(), "public", "recommendation-performance.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as RecommendationPerformanceOutput;
  } catch {
    return null;
  }
}

export async function loadStrategyBacktestResults() {
  try {
    const filePath = path.join(process.cwd(), "public", "strategy-backtest-results.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as StrategyBacktestResults;
  } catch {
    return null;
  }
}

export type StrategyBacktestResults = {
  generated_at: string;
  method: string;
  note: string;
  date_range: { start: string; end: string };
  odds_metadata?: RecommendationPerformanceOutput["odds_metadata"];
  game_days_with_odds: number;
  flat_by_mode: Record<
    string,
    {
      bets: number;
      wins: number;
      losses: number;
      flat_profit: number;
      flat_roi: number;
      hit_rate: number;
    }
  >;
  winners_by_bankroll: Record<
    string,
    Array<{
      mode: string;
      optimal_stake_pct: number;
      end_bankroll: number;
      profit: number;
      min_bankroll: number;
      bets: number;
      record: string;
    }>
  >;
  recommended_mode: string;
  recommended_stake_pct: number;
  recommended_summary: {
    mode: string;
    optimal_stake_pct: number;
    end_bankroll: number;
    profit: number;
    min_bankroll: number;
    bets: number;
    record: string;
  };
};

export type ExhaustiveStrategyRow = {
  strategy_id: string;
  rule: string;
  bankroll: number;
  days: number;
  multi_bet_days: number;
  mode: string;
  stake_pct: number;
  end: number;
  profit: number;
  min_bankroll: number;
  bets: number;
  wins: number;
  losses: number;
  flat_profit?: number;
  flat_roi?: number;
  hit_rate?: number;
};

export type ExhaustiveStrategySearch = {
  generated_at: string;
  method: string;
  date_range: { start: string; end: string };
  odds_metadata?: RecommendationPerformanceOutput["odds_metadata"];
  strategies_tested: number;
  fair_daily_exposure_cap: number;
  note_raw: string;
  note_fair: string;
  top_fair_10k: ExhaustiveStrategyRow[];
  top_raw_10k: ExhaustiveStrategyRow[];
  top_fair_10: ExhaustiveStrategyRow[];
  weird_result_analysis: {
    strategy: string;
    raw_10k: ExhaustiveStrategyRow;
    fair_10k: ExhaustiveStrategyRow;
    always_2_fair_10k: ExhaustiveStrategyRow;
    verdict: string;
  };
  recommendation: {
    one_bet_per_day_fair: ExhaustiveStrategyRow | null;
    multi_bet_fair: ExhaustiveStrategyRow | null;
  };
};

export async function loadExhaustiveStrategySearch() {
  try {
    const filePath = path.join(process.cwd(), "public", "exhaustive-strategy-search.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as ExhaustiveStrategySearch;
  } catch {
    return null;
  }
}

export type OosStrategyValidation = {
  generated_at: string;
  method: string;
  fair_daily_exposure_cap: number;
  stake_pct: number;
  note: string;
  period_2025: {
    label: string;
    date_range: { start: string; end: string };
    winner_one_bet_fair: ExhaustiveStrategyRow | null;
    top_fair_10k: ExhaustiveStrategyRow[];
    focus_strategies_fair_10k: Record<string, ExhaustiveStrategyRow | undefined>;
  };
  period_2026: {
    label: string;
    date_range: { start: string; end: string };
    winner_one_bet_fair: ExhaustiveStrategyRow | null;
    top_fair_10k: ExhaustiveStrategyRow[];
    focus_strategies_fair_10k: Record<string, ExhaustiveStrategyRow | undefined>;
  };
  overfitting_analysis: {
    verdict: string;
    two_or_three_best: {
      "2025": ExhaustiveStrategyRow | null;
      "2026": ExhaustiveStrategyRow | null;
      "2025_rank": number | null;
      "2026_rank": number | null;
    };
  };
};

export async function loadOosStrategyValidation() {
  try {
    const filePath = path.join(process.cwd(), "public", "oos-strategy-validation.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as OosStrategyValidation;
  } catch {
    return null;
  }
}

export type RatchetTier = {
  min_balance: number;
  max_balance: number | null;
  parlay_pct: number;
  single_pct: number;
};

export type BettingPlan = {
  generated_at: string;
  strategy: string;
  strategy_rules: string[];
  stake_by_leg_count: Record<string, number>;
  stake_optimizer_suggestion?: Record<string, number>;
  ratchet_tiers?: RatchetTier[];
  flat_stake_fallback: number;
  daily_exposure_cap: number;
  backtest_period: { start: string; end: string };
  retuned_from: string;
};

export type StrategyGuard = {
  generated_at: string;
  live_strategy: string;
  period: { season_start: string; end: string; rolling_14d_start: string };
  stakes: Record<string, number>;
  comparisons: Record<
    string,
    {
      season_to_date: {
        days: number;
        flat_roi: number;
        flat_profit: number;
        end: number;
        record: string;
      };
      rolling_14d: {
        days: number;
        flat_roi: number;
        flat_profit: number;
        end: number;
        record: string;
      };
    }
  >;
  ranked_by_season_compound?: string[];
  ranked_by_rolling_14d_compound?: string[];
  guard: {
    season_leader: string;
    leader_14d: string;
    leader_streak_days: number;
    switch_signal_days_required: number;
    switch_recommended: boolean;
    message: string;
  };
  live_compound?: {
    strategy: string;
    stakes: Record<string, number>;
    daily_exposure_cap: number;
    from_10: StrategyCompoundCurve;
    from_100: StrategyCompoundCurve;
  };
  execution_rules: string[];
};

export type StrategyCompoundCheckpoint = {
  date: string;
  profit: number;
  balance: number;
  return_pct: number;
  won: boolean;
  leg_count: number;
};

export type StrategyCompoundCurve = {
  starting_bankroll: number;
  end: number;
  profit: number;
  min_bankroll: number;
  record: string;
  days: number;
  flat_roi: number;
  flat_profit: number;
  checkpoints: StrategyCompoundCheckpoint[];
};

export async function loadStrategyGuard() {
  try {
    const filePath = path.join(process.cwd(), "public", "strategy-guard.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as StrategyGuard;
  } catch {
    return null;
  }
}

export type LiveBankrollTicket = {
  date: string;
  label: string;
  legs: string[];
  leg_count: number;
  stake_pct: number;
  stake_amount: number;
  profit?: number;
  balance_after?: number;
  won?: boolean;
  odds?: number;
  model_probability?: number;
  status?: string;
};

export type LiveBankroll = {
  generated_at: string;
  tracking_mode?: string;
  disclaimer?: string;
  strategy: string;
  staking?: string;
  stakes: Record<string, number>;
  ratchet_tiers?: RatchetTier[];
  prove_out?: {
    flat_stake_usd: number;
    target_tickets: number;
    completed_tickets: number;
    active: boolean;
  };
  daily_exposure_cap: number;
  started_at: string;
  starting_balance: number;
  balance: number;
  wallet_balance?: number | null;
  profit: number;
  return_pct: number;
  record: string;
  hit_rate?: number | null;
  backtest_ticket_hit_rate?: number;
  last_settled_date: string | null;
  today_ticket: LiveBankrollTicket | null;
  checkpoints: StrategyCompoundCheckpoint[];
  tickets?: LiveBankrollTicket[];
  tracking_note?: string;
};

export async function loadLiveBankroll() {
  try {
    const filePath = path.join(process.cwd(), "public", "live-bankroll.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as LiveBankroll;
  } catch {
    return null;
  }
}

export async function loadLiveStrategyMetrics() {
  try {
    const filePath = path.join(process.cwd(), "public", "live-strategy-metrics.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as {
      generated_at: string;
      strategy: string;
      headline: {
        bet_days: number;
        parlay_days: number;
        single_days: number;
        ticket_hit_rate: number;
        parlay_hit_rate: number | null;
        single_hit_rate: number | null;
        record: string;
      };
      flat_per_100_staked: { roi: number; profit_units: number; hit_rate: number };
    };
  } catch {
    return null;
  }
}

export async function loadBettingPlan() {
  try {
    const filePath = path.join(process.cwd(), "public", "betting-plan.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as BettingPlan;
  } catch {
    return null;
  }
}

export type LockedTicketLeg = {
  team: string;
  matchup: string;
  confidence: string;
  pickProbability: number;
  edge: number;
  odds: number;
  startsAt: string;
};

export type LockedDailyTicket = {
  kind: "single" | "multi_single" | "parlay" | "skip";
  label: string;
  legs: string[];
  leg_count: number;
  odds?: number | null;
  model_probability?: number | null;
  leg_details?: LockedTicketLeg[];
};

export type LockedTicketOutput = {
  date: string;
  locked_at: string;
  board_generated_at?: string;
  model_version?: string;
  pipeline_version?: string;
  source?: string;
  note?: string;
  ticket: LockedDailyTicket;
};

export async function loadLockedTicket(): Promise<LockedTicketOutput | null> {
  try {
    const filePath = path.join(process.cwd(), "public", "locked-ticket.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as LockedTicketOutput;
  } catch {
    return null;
  }
}

export type PropPrediction = {
  game_id: string | null;
  matchup: string;
  commence_time: string;
  player: string;
  player_id: number;
  team: string | null;
  opp: string | null;
  prop: string;
  prop_label: string;
  line: number;
  side: "Over" | "Under";
  pick: string;
  projection: number;
  model_prob: number;
  model_prob_raw?: number;
  market_prob: number | null;
  edge: number;
  price: number | null;
  ev: number | null;
  confidence: "Elite" | "High" | "Medium" | "Low";
  book_count: number;
  note: string;
  line_source?: string;
  market_is_pickem?: boolean;
  pp_odds_type?: "standard" | "goblin" | "demon" | string | null;
  coin_flip?: boolean;
  unplayable?: boolean;
};

export type PropParlay = {
  type?: string;
  n_legs: number;
  combined_prob?: number;
  flex_cash_rate_oos?: number | null;
  power_cash_rate_oos?: number | null;
  policy?: string;
  legs: PropPrediction[];
};

/** Same-game 3-leg parlay priced by the PA Monte Carlo joint probability. */
export type CorrelatedParlay = {
  game_id: string;
  matchup?: string | null;
  commence_time?: string | null;
  n_legs: number;
  type?: string;
  payout?: number;
  /** Correlation-aware cash probability (shrunk marginals × sim lift). */
  joint_prob: number;
  /** Raw sim fraction of games where all legs hit. */
  joint_prob_sim_raw?: number;
  /** Naive book assumption: product of the marginals. */
  independent_prob?: number;
  /** joint / independent — >1 means legs win together. */
  correlation_lift?: number;
  ev_per_dollar?: number;
  no_bet?: boolean;
  engine?: string;
  legs: PropPrediction[];
};

export type PropPredictionsOutput = {
  generated_at: string;
  board_generated_at?: string;
  source?: string;
  line_source?: string;
  count: number;
  min_edge?: number;
  top_bets?: PropPrediction[];
  /** Highest projected starter K Overs (includes model fill-ins when PP omits an ace). */
  ace_k_card?: PropPrediction[];
  parlay: PropParlay;
  /** Ranked same-game 3-leg parlays scored by the sim's joint probability. */
  correlated_parlays?: CorrelatedParlay[];
  predictions: PropPrediction[];
};

export async function loadPropPredictions(): Promise<PropPredictionsOutput | null> {
  try {
    const filePath = path.join(process.cwd(), "public", "prop-predictions.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as PropPredictionsOutput;
  } catch {
    return null;
  }
}

export type PropTrackRecord = {
  generated_at?: string;
  overall?: {
    graded: number;
    wins: number;
    losses: number;
    pushes: number;
    hit_rate: number;
    roi: number;
  };
  by_confidence?: Record<string, { graded: number; wins: number; hit_rate: number }>;
  by_prop?: Record<string, { graded: number; wins: number; hit_rate: number }>;
  parlay?: { graded: number; wins: number; hit_rate: number; roi: number };
  recent?: Array<Record<string, unknown>>;
};

export async function loadPropTrackRecord(): Promise<PropTrackRecord | null> {
  try {
    const filePath = path.join(process.cwd(), "public", "prop-track-record.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as PropTrackRecord;
  } catch {
    return null;
  }
}

export type BestTicketWalkforwardLeg = {
  team: string;
  matchup: string;
  odds?: number;
  model_probability: number;
  confidence: string;
  won: boolean;
};

export type BestTicketWalkforwardRow = {
  date: string;
  strategy: string;
  ticket_type: string;
  label: string;
  leg_count: number;
  legs: BestTicketWalkforwardLeg[];
  won: boolean;
  result: "HIT" | "MISS";
  flat_profit: number;
};

export type BestTicketWalkforwardOutput = {
  generated_at: string;
  method: string;
  model_version: string;
  feature_count: number;
  strategy: string;
  date_range: { start: string; end: string };
  game_prediction_accuracy: {
    games: number;
    correct: number;
    accuracy: number;
  };
  best_ticket_accuracy: {
    bet_days: number;
    wins: number;
    losses: number;
    hit_rate: number;
    record: string;
  };
  last_14_days: {
    start: string;
    end: string;
    bet_days: number;
    wins: number;
    losses: number;
    hit_rate: number;
    record: string;
    tickets: BestTicketWalkforwardRow[];
  };
  tickets: BestTicketWalkforwardRow[];
};

export async function loadBestTicketWalkforward() {
  try {
    const filePath = path.join(process.cwd(), "public", "best-ticket-walkforward.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as BestTicketWalkforwardOutput;
  } catch {
    return null;
  }
}

export async function loadBettingStrategyOptimizer() {
  try {
    const filePath = path.join(process.cwd(), "public", "betting-strategy-optimizer.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as BettingStrategyOptimizerOutput;
  } catch {
    return null;
  }
}

export type BettingStrategyOptimizerOutput = {
  generated_at: string;
  method: string;
  date_range: { start: string; end: string };
  season_progress_pct: number;
  stake_pct_grid: number[];
  starting_bankrolls: number[];
  strategies_tested: string[];
  flat_summaries: Record<
    string,
    {
      bets: number;
      wins: number;
      losses: number;
      flat_profit_per_100: number;
      flat_roi: number;
      mix: Record<string, number>;
    }
  >;
  optimal_by_bankroll: Record<
    string,
    {
      best_pure_strategy: {
        strategy: string;
        optimal_stake_pct: number;
        to_date_end: number;
        to_date_profit: number;
        min_bankroll: number;
        full_season_projection: number;
      } | null;
      all_strategies_ranked: Array<{
        strategy: string;
        optimal_stake_pct: number;
        to_date_end: number;
        to_date_profit: number;
        min_bankroll: number;
        full_season_projection: number;
      }>;
      best_tiered_max_score: {
        stake_map: Record<string, number>;
        end: number;
        profit: number;
        min_bankroll: number;
        return_pct: number;
        full_season_projection: number | null;
      } | null;
    }
  >;
  recommendation: {
    primary_strategy: string;
    description: string;
    tiered_staking: string;
    notes: string[];
    [key: string]: unknown;
  };
};

export async function loadParlay2CompoundBacktest(): Promise<Parlay2CompoundBacktestOutput | null> {
  try {
    const filePath = path.join(process.cwd(), "public", "parlay2-compound-backtest.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as Parlay2CompoundBacktestOutput;
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
  eraDiff?: number;
  formEdge?: number;
};

type PredictionBoardFile = {
  generated_at?: string;
  board_generated_at?: string;
  trained_through?: string;
  model_version?: string;
  pipeline_version?: string;
  retrained_this_run?: boolean;
  predictions?: PredictionOutputRow[];
};

const BOARD_MAX_AGE_MS = 20 * 60 * 60 * 1000; // 20 hours — board is valid all day after 5 AM retrain

function isFreshBoard(payload: PredictionBoardFile, rows: PredictionOutputRow[]) {
  const today = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  const boardIsToday = rows.length > 0 && rows.every((row) => (row.date ?? row.startsAt?.slice(0, 10)) === today);
  const generatedToday = payload.generated_at === today;
  const trainedThroughYesterday = payload.trained_through === yesterday;
  const boardGeneratedAt = payload.board_generated_at;
  const boardIsRecent =
    !boardGeneratedAt || Date.now() - new Date(boardGeneratedAt).getTime() <= BOARD_MAX_AGE_MS;
  return boardIsToday && generatedToday && trainedThroughYesterday && boardIsRecent;
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
    // The displayed % is the model's TRUE calibrated win probability (no inflation layer),
    // so pickProbability == rawPickProbability and the same number drives the label, the
    // ticket, and EV on every page. Fall back to raw / model max only if a field is missing.
    const pickProbability =
      row.pickProbability ?? row.rawPickProbability ?? Math.max(homeProbability, awayProbability);

    // Sanitise corrupted moneyline data before it reaches the UI or ticket logic.
    // Real MLB moneylines stay within ±1500; anything beyond that is a stale or bad API response.
    const ML_SANITY = 1500;
    const homeMoneylineRaw = row.homeMoneyline ?? null;
    const awayMoneylineRaw = row.awayMoneyline ?? null;
    const homeMoneyline = homeMoneylineRaw !== null && Math.abs(homeMoneylineRaw) <= ML_SANITY ? homeMoneylineRaw : null;
    const awayMoneyline = awayMoneylineRaw !== null && Math.abs(awayMoneylineRaw) <= ML_SANITY ? awayMoneylineRaw : null;

    const predictedTeam = row.predictedTeam ?? (homeProbability >= awayProbability ? homeTeam : awayTeam);
    const confidence =
      row.confidence ??
      confidenceFromPickProbability(pickProbability, {
        modelEdge: row.modelEdge,
        starterCertain: row.starterCertain,
        marketAvailable: homeMoneyline != null && awayMoneyline != null,
        rawPick: row.rawPickProbability ?? pickProbability,
      });

    const normalized: GamePrediction = {
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
      homeMoneyline,
      awayMoneyline,
      homeRunline: row.homeRunline ?? null,
      awayRunline: row.awayRunline ?? null,
      homeRunlinePrice: row.homeRunlinePrice ?? null,
      awayRunlinePrice: row.awayRunlinePrice ?? null,
      marketTotal: row.marketTotal ?? null,
      overPrice: row.overPrice ?? null,
      underPrice: row.underPrice ?? null,
      projectedTotal: row.projectedTotal ?? null,
      oddsSource: row.oddsSource ?? null,
      confidence,
      marketAgrees: row.marketAgrees,
      modelEdge: row.modelEdge,
      modelVersion: row.modelVersion ?? "daily-model",
      explanation: row.explanation ?? [
        "Generated by the daily model output",
        "Odds default to neutral when live lines are unavailable",
        "Refresh the page to pick up newly generated board data"
      ],
      starterCertain: row.starterCertain,
      pitcherChanged: row.pitcherChanged,
      eraDiff: row.eraDiff,
      formEdge: row.formEdge,
      predictionSource: row.predictionSource,
      lineupSource: row.lineupSource,
      nSims: row.nSims,
      simRawHomeWinProbability: row.simRawHomeWinProbability,
      gbmHomeWinProbability: row.gbmHomeWinProbability,
    };
    // Only re-validate when confidence was computed on-the-fly in TypeScript (row.confidence absent).
    // When the JSON row already carries a confidence label, Python's integrity check at generation
    // time is the ground truth. Re-checking here would use the raw pick probability for display
    // while Python used the calibrated display pick, causing false-positive mismatches.
    if (!row.confidence) {
      assertConfidenceMatchesPick(normalized);
    }
    return normalized;
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

export type ModelHealthWindow = {
  games: number;
  correct: number;
  accuracy: number | null;
  record: string;
};

export type ModelHealthSummary = {
  yesterday: ModelHealthWindow;
  last7Days: ModelHealthWindow;
  season: ModelHealthWindow;
};

function summarizePredictionWindow(rows: PredictionHistoryRow[]): ModelHealthWindow {
  const games = rows.length;
  const correct = rows.reduce((sum, row) => sum + Number(row.correct ?? 0), 0);
  return {
    games,
    correct,
    accuracy: games > 0 ? correct / games : null,
    record: `${correct}-${games - correct}`
  };
}

export async function loadModelHealthSummary(): Promise<ModelHealthSummary | null> {
  const predictions = await loadFullPredictionHistory();
  if (!predictions.length) {
    return null;
  }

  const today = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  const sevenDaysAgo = new Date(Date.now() - 7 * 86_400_000).toISOString().slice(0, 10);
  const currentSeason = today.slice(0, 4);
  const graded = predictions.filter((row) => row.actual && row.date < today);

  return {
    yesterday: summarizePredictionWindow(graded.filter((row) => row.date === yesterday)),
    last7Days: summarizePredictionWindow(
      graded.filter((row) => row.date >= sevenDaysAgo && row.date < today)
    ),
    season: summarizePredictionWindow(graded.filter((row) => row.date.startsWith(currentSeason)))
  };
}

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

export async function loadLiveModelPerformance(): Promise<LiveModelPerformanceOutput | null> {
  try {
    const filePath = path.join(process.cwd(), "public", "model-live-performance.json");
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as LiveModelPerformanceOutput;
  } catch {
    return null;
  }
}

export async function loadPredictionBoardMetadata(): Promise<PredictionBoardFile> {
  try {
    const { payload } = await readPredictionBoard();
    return payload;
  } catch {
    return {};
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
