import { describe, expect, it, vi } from 'vitest';
import { shuffleQuestions } from './shuffle';

describe('shuffleQuestions', () => {
  it('preserves length and every original element', () => {
    const items = [1, 2, 3, 4, 5, 6, 7, 8];
    const result = shuffleQuestions(items);
    expect(result).toHaveLength(items.length);
    expect([...result].sort()).toEqual([...items].sort());
  });

  it('does not mutate the input array', () => {
    const items = [1, 2, 3];
    const original = [...items];
    shuffleQuestions(items);
    expect(items).toEqual(original);
  });

  it('produces the expected permutation for a mocked Math.random sequence', () => {
    const items = ['a', 'b', 'c', 'd'];
    // Fisher-Yates from i=3 down to i=1, one Math.random() call per step.
    const sequence = [0, 0, 0]; // always swap with index 0
    let call = 0;
    vi.spyOn(Math, 'random').mockImplementation(() => sequence[call++] as number);

    const result = shuffleQuestions(items);

    // i=3: j=floor(0*4)=0 -> swap(3,0): [d,b,c,a]
    // i=2: j=floor(0*3)=0 -> swap(2,0): [c,b,d,a]
    // i=1: j=floor(0*2)=0 -> swap(1,0): [b,c,d,a]
    expect(result).toEqual(['b', 'c', 'd', 'a']);

    vi.restoreAllMocks();
  });
});
