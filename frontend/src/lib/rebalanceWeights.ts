export function rebalanceWeightsAfterDelete<T extends { weight_percentage: number }>(
  remaining: T[],
  removedWeight: number,
): T[] {
  if (remaining.length === 0) return remaining;

  const remainingTotal = remaining.reduce((sum, r) => sum + r.weight_percentage, 0);

  if (remainingTotal > 0) {
    return remaining.map((r) => ({
      ...r,
      weight_percentage: Math.round((r.weight_percentage + (r.weight_percentage / remainingTotal) * removedWeight) * 100) / 100,
    }));
  }

  const even = Math.round((100 / remaining.length) * 100) / 100;
  return remaining.map((r) => ({ ...r, weight_percentage: even }));
}
