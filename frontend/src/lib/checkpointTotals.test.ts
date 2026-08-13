import { describe, expect, it } from 'vitest';
import { computeCheckpointTotals } from './checkpointTotals';

describe('computeCheckpointTotals', () => {
  it('is balanced when weights sum to exactly 100', () => {
    const result = computeCheckpointTotals([
      { weight_percentage: 60, question_count: 4 },
      { weight_percentage: 40, question_count: 3 },
    ]);
    expect(result).toEqual({ totalWeight: 100, totalQuestions: 7, isBalanced: true });
  });

  it('is balanced within the 0.05 tolerance', () => {
    const result = computeCheckpointTotals([{ weight_percentage: 99.97, question_count: 1 }]);
    expect(result.isBalanced).toBe(true);
  });

  it('is not balanced outside tolerance', () => {
    const result = computeCheckpointTotals([{ weight_percentage: 90, question_count: 1 }]);
    expect(result.isBalanced).toBe(false);
  });

  it('handles an empty list as unbalanced with zero totals', () => {
    expect(computeCheckpointTotals([])).toEqual({ totalWeight: 0, totalQuestions: 0, isBalanced: false });
  });
});
