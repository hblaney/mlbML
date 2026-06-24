// Prediction-first confidence — pure probability tiers on the market-blended pick
// probability (matches probability_calibration.py). No market-edge requirement:
// a more reliable pick simply has a higher win probability.

import type { GamePrediction } from "./data";

export const CONFIDENCE_MEDIUM_MIN = 0.58;
export const CONFIDENCE_HIGH_MIN = 0.64;
export const CONFIDENCE_ELITE_MIN = 0.7;
export const CONFIDENCE_UNCERTAIN_MEDIUM_MIN = 0.6;

export type ConfidenceContext = {
  modelEdge?: number;
  starterCertain?: boolean;
  marketAvailable?: boolean;
  marketAgrees?: boolean | null;
  rawPick?: number;
  eraDiff?: number;
  formEdge?: number;
};

export function confidenceFromPickProbability(
  probability: number,
  context: ConfidenceContext = {}
): GamePrediction["confidence"] {
  const starterCertain = context.starterCertain ?? true;
  const marketAvailable = context.marketAvailable ?? true;

  // Unconfirmed starter or no market price makes the probability less trustworthy.
  if (!starterCertain || !marketAvailable) {
    return probability >= CONFIDENCE_UNCERTAIN_MEDIUM_MIN ? "Medium" : "Low";
  }

  if (probability >= CONFIDENCE_ELITE_MIN) {
    return "Elite";
  }
  if (probability >= CONFIDENCE_HIGH_MIN) {
    return "High";
  }
  if (probability >= CONFIDENCE_MEDIUM_MIN) {
    return "Medium";
  }
  return "Low";
}

export function assertConfidenceMatchesPick(
  game: Pick<
    GamePrediction,
    | "id"
    | "pickProbability"
    | "rawPickProbability"
    | "confidence"
    | "modelEdge"
    | "marketAgrees"
    | "starterCertain"
    | "homeMoneyline"
    | "awayMoneyline"
    | "eraDiff"
    | "formEdge"
  >
): void {
  const pick = game.pickProbability ?? 0;
  const expected = confidenceFromPickProbability(pick, {
    modelEdge: game.modelEdge,
    starterCertain: game.starterCertain,
    marketAvailable: game.homeMoneyline != null && game.awayMoneyline != null,
    marketAgrees: game.marketAgrees,
    rawPick: game.rawPickProbability ?? pick,
    eraDiff: game.eraDiff ?? 0,
    formEdge: game.formEdge ?? 0,
  });
  if (game.confidence !== expected) {
    throw new Error(
      `Prediction integrity: ${game.id} confidence ${game.confidence} != ${expected} for pick ${pick.toFixed(4)}`
    );
  }
}
