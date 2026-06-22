// Accountable confidence on 60–90% display scale — must match probability_calibration.py.

import type { GamePrediction } from "./data";

export const DISPLAY_PROBABILITY_FLOOR = 0.6;
export const DISPLAY_PROBABILITY_CEILING = 0.9;
export const CONFIDENCE_MEDIUM_MIN = 0.68;
export const CONFIDENCE_HIGH_MIN = 0.76;
export const CONFIDENCE_ELITE_MIN = 0.85;
export const CONFIDENCE_HIGH_EDGE_MIN = 0.08;
export const CONFIDENCE_ELITE_EDGE_MIN = 0.1;

export type ConfidenceContext = {
  modelEdge?: number;
  starterCertain?: boolean;
  marketAvailable?: boolean;
  rawPick?: number;
};

export function confidenceFromPickProbability(
  probability: number,
  context: ConfidenceContext = {}
): GamePrediction["confidence"] {
  const modelEdge = context.modelEdge ?? 0;
  const starterCertain = context.starterCertain ?? true;
  const marketAvailable = context.marketAvailable ?? true;
  const rawPick = context.rawPick ?? probability;

  if (!starterCertain) {
    return probability >= CONFIDENCE_MEDIUM_MIN ? "Medium" : "Low";
  }

  if (!marketAvailable) {
    return probability >= CONFIDENCE_MEDIUM_MIN ? "Medium" : "Low";
  }

  if (probability >= CONFIDENCE_ELITE_MIN && modelEdge >= CONFIDENCE_ELITE_EDGE_MIN && rawPick >= 0.67) {
    return "Elite";
  }
  if (probability >= CONFIDENCE_HIGH_MIN && modelEdge >= CONFIDENCE_HIGH_EDGE_MIN && rawPick >= 0.62) {
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
    "id" | "pickProbability" | "confidence" | "modelEdge" | "starterCertain"
  >
): void {
  const pick = game.pickProbability ?? 0;
  const expected = confidenceFromPickProbability(pick, {
    modelEdge: game.modelEdge,
    starterCertain: game.starterCertain,
    marketAvailable: game.homeMoneyline != null && game.awayMoneyline != null,
    rawPick: game.rawPickProbability ?? pick,
  });
  if (game.confidence !== expected) {
    throw new Error(
      `Prediction integrity: ${game.id} confidence ${game.confidence} != ${expected} for pick ${pick.toFixed(4)}`
    );
  }
}
