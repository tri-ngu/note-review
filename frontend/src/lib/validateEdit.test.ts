import { describe, expect, it } from 'vitest';
import { validateEdit, hasEditErrors, type EditDraft } from './validateEdit';

function baseDraft(overrides: Partial<EditDraft> = {}): EditDraft {
  return {
    options: ['A', 'B', 'C', 'D'],
    correct_answers: [1],
    is_select_all: false,
    page_number: 1,
    ...overrides,
  };
}

describe('validateEdit', () => {
  it('passes a valid Multiple-Choice draft', () => {
    expect(validateEdit(baseDraft())).toEqual({});
  });

  it('passes a valid Select-All draft', () => {
    expect(validateEdit(baseDraft({ is_select_all: true, correct_answers: [1, 3] }))).toEqual({});
  });

  it('flags a blank option', () => {
    const errors = validateEdit(baseDraft({ options: ['A', '', 'C', 'D'] }));
    expect(errors.options).toBeDefined();
  });

  it('flags a whitespace-only option', () => {
    const errors = validateEdit(baseDraft({ options: ['A', '   ', 'C', 'D'] }));
    expect(errors.options).toBeDefined();
  });

  it('flags Multiple-Choice with zero correct answers', () => {
    const errors = validateEdit(baseDraft({ correct_answers: [] }));
    expect(errors.correct_answers).toBeDefined();
  });

  it('flags Multiple-Choice with more than one correct answer', () => {
    const errors = validateEdit(baseDraft({ correct_answers: [1, 2] }));
    expect(errors.correct_answers).toBeDefined();
  });

  it('flags Select-All with zero correct answers', () => {
    const errors = validateEdit(baseDraft({ is_select_all: true, correct_answers: [] }));
    expect(errors.correct_answers).toBeDefined();
  });

  it('allows Select-All with all 4 correct', () => {
    const errors = validateEdit(baseDraft({ is_select_all: true, correct_answers: [1, 2, 3, 4] }));
    expect(errors.correct_answers).toBeUndefined();
  });

  it('flags a zero page number', () => {
    const errors = validateEdit(baseDraft({ page_number: 0 }));
    expect(errors.page_number).toBeDefined();
  });

  it('flags a negative page number', () => {
    const errors = validateEdit(baseDraft({ page_number: -3 }));
    expect(errors.page_number).toBeDefined();
  });

  it('flags a non-integer page number', () => {
    const errors = validateEdit(baseDraft({ page_number: 1.5 }));
    expect(errors.page_number).toBeDefined();
  });

  it('reports multiple errors at once', () => {
    const errors = validateEdit(baseDraft({ options: ['', 'B', 'C', 'D'], correct_answers: [], page_number: 0 }));
    expect(errors.options).toBeDefined();
    expect(errors.correct_answers).toBeDefined();
    expect(errors.page_number).toBeDefined();
  });
});

describe('hasEditErrors', () => {
  it('is false for an empty error object', () => {
    expect(hasEditErrors({})).toBe(false);
  });

  it('is true when any error is present', () => {
    expect(hasEditErrors({ page_number: 'bad' })).toBe(true);
  });
});
