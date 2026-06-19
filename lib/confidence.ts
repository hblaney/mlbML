// Single source of truth for confidence labels — must match trained_edge_model.public_confidence_for.

import type { GamePrediction } from "./data";

export const CONFIDENCE_HIGH_MIN = 0.7;
export const CONFIDENCE_MEDIUM_MIN = 0.55;

export function confidenceFromPickProbability(probability: number): GamePrediction["confidence"] {
  if (probability >= CONFIDENCE_HIGH_MIN) {
    return "High";
  }
  if (probability >= CONFIDENCE_MEDIUM_MIN) {
    return "Medium";
  }
  return "Low";
}

export function assertConfidenceMatchesPick(game: Pick<GamePrediction, "id" | "pickProbability" | "confidence">): void {
  const pick = game.pickProbability ?? 0;
  const expected = confidenceFromPickProbability(pick);
  if (game.confidence !== expected) {
    throw new Error(
      `Prediction integrity: ${game.id} confidence ${game.confidence} != ${expected} for pick ${pick.toFixed(4)}`
    );
  }
}
