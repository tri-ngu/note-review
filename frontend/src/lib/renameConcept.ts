import type { Question } from '../types/question';

export function distinctConcepts(questions: Question[], excludeConcept: string): string[] {
  const seen = new Set<string>();
  for (const q of questions) {
    if (q.concept !== excludeConcept) seen.add(q.concept);
  }
  return [...seen];
}

export function conceptCollides(otherConcepts: string[], candidate: string): boolean {
  return otherConcepts.includes(candidate);
}

export function renameConceptEverywhere(questions: Question[], oldName: string, newName: string): Question[] {
  return questions.map((q) => (q.concept === oldName ? { ...q, concept: newName } : q));
}
