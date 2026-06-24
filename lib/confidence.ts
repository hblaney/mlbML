// Honest confidence on the TRUE probability scale — must match probability_calibration.py.
// The displayed % IS the model's calibrated win probability (no inflation), so these
// thresholds are the real win-rate floors for each tier.

import type { GamePrediction } from "./data";

export const CONFIDENCE_MEDIUM_MIN = 0.57;
export const CONFIDENCE_HIGH_MIN = 0.64;
export const CONFIDENCE_ELITE_MIN = 0.67;
// Unconfirmed starter or no market price can't earn above Medium.
export const CONFIDENCE_UNCERTAIN_MEDIUM_MIN = 0.6;
export const CONFIDENCE_HIGH_EDGE_MIN = 0.08;
export const CONFIDENCE_ELITE_EDGE_MIN = 0.1;
export const HIGH_VALUE_EDGE_MIN = 0.12;
export const HIGH_VALUE_PROB_MIN = 0.57;

// ERA diff / form edge thresholds — must match probability_calibration.py
export const HIGH_ERA_DIFF_MIN = 1.5;
export const HIGH_FORM_EDGE_MIN = 0.10;
export const ELITE_ERA_DIFF_MIN = 2.5;
export const ELITE_FORM_EDGE_MIN = 0.08;
export const HIGH_MIN_RAW_PICK = 0.64;
export const ELITE_MIN_RAW_PICK = 0.67;

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
  const modelEdge = context.modelEdge ?? 0;
  const starterCertain = context.starterCertain ?? true;
  const marketAvailable = context.marketAvailable ?? true;
  const marketAgrees = context.marketAgrees;
  const rawPick = context.rawPick ?? probability;
  const eraDiff = context.eraDiff ?? 0;
  const formEdge = context.formEdge ?? 0;

  if (!starterCertain) {
    return probability >= CONFIDENCE_UNCERTAIN_MEDIUM_MIN ? "Medium" : "Low";
  }

  if (!marketAvailable) {
    return probability >= CONFIDENCE_UNCERTAIN_MEDIUM_MIN ? "Medium" : "Low";
  }

  const eliteEraOk = eraDiff >= ELITE_ERA_DIFF_MIN;
  const eliteFormOk = formEdge >= ELITE_FORM_EDGE_MIN;
  if (
    probability >= CONFIDENCE_ELITE_MIN &&
    modelEdge >= CONFIDENCE_ELITE_EDGE_MIN &&
    rawPick >= ELITE_MIN_RAW_PICK &&
    eliteEraOk &&
    eliteFormOk
  ) {
    return "Elite";
  }

  const highEraOk = eraDiff >= HIGH_ERA_DIFF_MIN;
  const highFormOk = formEdge >= HIGH_FORM_EDGE_MIN;

  if (
    modelEdge >= HIGH_VALUE_EDGE_MIN &&
    probability >= HIGH_VALUE_PROB_MIN &&
    marketAgrees === false
  ) {
    return "High";
  }

  if (
    probability >= CONFIDENCE_HIGH_MIN &&
    modelEdge >= CONFIDENCE_HIGH_EDGE_MIN &&
    rawPick >= HIGH_MIN_RAW_PICK &&
    (highEraOk || highFormOk)
  ) {
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
