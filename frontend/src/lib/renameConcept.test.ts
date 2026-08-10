import { describe, expect, it } from 'vitest';
import { distinctConcepts, conceptCollides, renameConceptEverywhere } from './renameConcept';
import type { Question } from '../types/question';

function makeQuestion(concept: string): Question {
  return {
    concept,
    question_text: 'q',
    options: ['A', 'B', 'C', 'D'],
    correct_answers: [1],
    is_select_all: false,
    explanation: 'e',
    page_number: 1,
    source_quote: 's',
  };
}

describe('distinctConcepts', () => {
  it('returns unique concepts excluding the given one', () => {
    const questions = [makeQuestion('A'), makeQuestion('B'), makeQuestion('A'), makeQuestion('C')];
    expect(distinctConcepts(questions, 'A')).toEqual(['B', 'C']);
  });

  it('returns an empty list when no other concept exists', () => {
    const questions = [makeQuestion('A'), makeQuestion('A')];
    expect(distinctConcepts(questions, 'A')).toEqual([]);
  });
});

describe('conceptCollides', () => {
  it('is true when the candidate matches an existing other concept', () => {
    expect(conceptCollides(['B', 'C'], 'B')).toBe(true);
  });

  it('is false when the candidate matches none', () => {
    expect(conceptCollides(['B', 'C'], 'D')).toBe(false);
  });
});

describe('renameConceptEverywhere', () => {
  it('renames every Question tagged with the old concept', () => {
    const questions = [makeQuestion('A'), makeQuestion('B'), makeQuestion('A')];
    const result = renameConceptEverywhere(questions, 'A', 'A2');
    expect(result.map((q) => q.concept)).toEqual(['A2', 'B', 'A2']);
  });

  it('leaves unrelated concepts untouched', () => {
    const questions = [makeQuestion('B')];
    const result = renameConceptEverywhere(questions, 'A', 'A2');
    expect(result.map((q) => q.concept)).toEqual(['B']);
  });
});
