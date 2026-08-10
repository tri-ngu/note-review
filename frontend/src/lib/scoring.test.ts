import { describe, expect, it } from 'vitest';
import { isQuestionCorrect } from './scoring';

describe('isQuestionCorrect', () => {
  it('is correct when selection exactly matches (MC, single answer)', () => {
    expect(isQuestionCorrect([1], [1])).toBe(true);
  });

  it('is incorrect when MC selection is wrong', () => {
    expect(isQuestionCorrect([2], [1])).toBe(false);
  });

  it('is correct regardless of order (SA, multiple answers)', () => {
    expect(isQuestionCorrect([4, 1, 2], [1, 2, 4])).toBe(true);
  });

  it('is incorrect when selection is a partial subset', () => {
    expect(isQuestionCorrect([1, 2], [1, 2, 4])).toBe(false);
  });

  it('is incorrect when selection has an extra wrong option', () => {
    expect(isQuestionCorrect([1, 2, 4, 3], [1, 2, 4])).toBe(false);
  });

  it('is incorrect when nothing is selected', () => {
    expect(isQuestionCorrect([], [1])).toBe(false);
  });

  it('is correct for a Select-All question with only 1 correct option, selected', () => {
    expect(isQuestionCorrect([1], [1])).toBe(true);
  });

  it('is correct for a Select-All question with all 4 correct, all selected', () => {
    expect(isQuestionCorrect([1, 2, 3, 4], [4, 3, 2, 1])).toBe(true);
  });
});
