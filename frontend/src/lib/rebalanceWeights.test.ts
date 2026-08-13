import { describe, expect, it } from 'vitest';
import { rebalanceWeightsAfterDelete } from './rebalanceWeights';

describe('rebalanceWeightsAfterDelete', () => {
  it('redistributes the removed weight proportionally among remaining entries', () => {
    const remaining = [{ weight_percentage: 30 }, { weight_percentage: 30 }, { weight_percentage: 20 }];
    const result = rebalanceWeightsAfterDelete(remaining, 20);
    expect(result.map((r) => r.weight_percentage)).toEqual([37.5, 37.5, 25]);
  });

  it('splits evenly when every remaining weight is zero', () => {
    const remaining = [{ weight_percentage: 0 }, { weight_percentage: 0 }];
    const result = rebalanceWeightsAfterDelete(remaining, 100);
    expect(result.map((r) => r.weight_percentage)).toEqual([50, 50]);
  });

  it('returns an empty array unchanged', () => {
    expect(rebalanceWeightsAfterDelete([], 100)).toEqual([]);
  });

  it('preserves other fields on each entry', () => {
    const remaining = [{ weight_percentage: 50, concept: 'A' }, { weight_percentage: 50, concept: 'B' }];
    const result = rebalanceWeightsAfterDelete(remaining, 10);
    expect(result.map((r) => r.concept)).toEqual(['A', 'B']);
  });
});
