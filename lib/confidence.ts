// Accountable confidence — must match trained_edge_model.public_confidence_for.

import type { GamePrediction } from "./data";

export const CONFIDENCE_MEDIUM_MIN = 0.55;
export const CONFIDENCE_HIGH_MIN = 0.62;
export const CONFIDENCE_ELITE_MIN = 0.65;
export const CONFIDENCE_HIGH_EDGE_MIN = 0.10;
export const CONFIDENCE_ELITE_EDGE_MIN = 0.12;

export type ConfidenceContext = {
  modelEdge?: number;
  starterCertain?: boolean;
};

export function confidenceFromPickProbability(
  probability: number,
  context: ConfidenceContext = {}
): GamePrediction["confidence"] {
  const modelEdge = context.modelEdge ?? 0;
  const starterCertain = context.starterCertain ?? true;

  if (!starterCertain) {
    return probability >= CONFIDENCE_MEDIUM_MIN ? "Medium" : "Low";
  }

  if (probability >= CONFIDENCE_ELITE_MIN && modelEdge >= CONFIDENCE_ELITE_EDGE_MIN) {
    return "Elite";
  }
  if (probability >= CONFIDENCE_HIGH_MIN && modelEdge >= CONFIDENCE_HIGH_EDGE_MIN) {
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
  });
  if (game.confidence !== expected) {
    throw new Error(
      `Prediction integrity: ${game.id} confidence ${game.confidence} != ${expected} for pick ${pick.toFixed(4)}`
    );
  }
}
