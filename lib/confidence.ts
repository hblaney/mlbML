// Betting-label confidence — mirrors scripts/model/probability_calibration.py.

import type { GamePrediction } from "./data";

/** Lean floor (price-supported). */
export const CONFIDENCE_MEDIUM_MIN = 0.55;
/** High = BET lane. */
export const CONFIDENCE_HIGH_MIN = 0.55;
export const CONFIDENCE_ELITE_MIN = 0.65;
export const CONFIDENCE_UNCERTAIN_MEDIUM_MIN = 0.6;
export const CONFIDENCE_HIGH_MIN_ERA_DIFF = 0.5;
export const CONFIDENCE_ELITE_MIN_ERA_DIFF = 1.5;
export const CONFIDENCE_HIGH_MIN_FORM_EDGE = 0.1;
export const CONFIDENCE_ELITE_MIN_FORM_EDGE = 0.1;
export const CONFIDENCE_HIGH_MIN_MODEL_EDGE = 0.02;
export const CONFIDENCE_ELITE_MIN_MODEL_EDGE = 0.03;

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
  const eraDiff = Math.round((context.eraDiff ?? 0) * 1e6) / 1e6;
  const formEdge = Math.round((context.formEdge ?? 0) * 1e6) / 1e6;
  const edge = context.modelEdge ?? 0;

  if (!starterCertain || !marketAvailable) {
    return probability >= CONFIDENCE_UNCERTAIN_MEDIUM_MIN ? "Medium" : "Low";
  }

  if (
    probability >= CONFIDENCE_ELITE_MIN &&
    eraDiff >= CONFIDENCE_ELITE_MIN_ERA_DIFF &&
    formEdge >= CONFIDENCE_ELITE_MIN_FORM_EDGE &&
    edge >= CONFIDENCE_ELITE_MIN_MODEL_EDGE &&
    context.marketAgrees === true
  ) {
    return "Elite";
  }
  if (
    probability >= CONFIDENCE_HIGH_MIN &&
    eraDiff >= CONFIDENCE_HIGH_MIN_ERA_DIFF &&
    formEdge >= CONFIDENCE_HIGH_MIN_FORM_EDGE &&
    edge >= CONFIDENCE_HIGH_MIN_MODEL_EDGE &&
    context.marketAgrees === true
  ) {
    return "High";
  }
  if (context.marketAgrees === true && edge >= CONFIDENCE_HIGH_MIN_MODEL_EDGE && probability >= CONFIDENCE_MEDIUM_MIN) {
    return "Medium";
  }
  if (probability >= 0.58 && eraDiff >= CONFIDENCE_HIGH_MIN_ERA_DIFF && formEdge >= 0) {
    return "Medium";
  }
  return "Low";
}

export function betActionFromConfidence(confidence: GamePrediction["confidence"]): "bet" | "lean" | "pass" {
  if (confidence === "Elite" || confidence === "High") return "bet";
  if (confidence === "Medium") return "lean";
  return "pass";
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
