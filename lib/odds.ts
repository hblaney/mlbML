export function impliedProbability(americanOdds: number) {
  if (americanOdds < 0) {
    return Math.abs(americanOdds) / (Math.abs(americanOdds) + 100);
  }

  return 100 / (americanOdds + 100);
}

export function expectedValue(probability: number, americanOdds: number, stake = 100) {
  const profit = americanOdds > 0 ? (americanOdds / 100) * stake : (100 / Math.abs(americanOdds)) * stake;
  const lossProbability = 1 - probability;

  return probability * profit - lossProbability * stake;
}

export function decimalOdds(americanOdds: number) {
  return americanOdds > 0 ? 1 + americanOdds / 100 : 1 + 100 / Math.abs(americanOdds);
}

export function americanFromDecimal(decimal: number) {
  if (decimal >= 2) {
    return Math.round((decimal - 1) * 100);
  }

  return Math.round(-100 / (decimal - 1));
}

export function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatOdds(value: number) {
  return value > 0 ? `+${value}` : `${value}`;
}
