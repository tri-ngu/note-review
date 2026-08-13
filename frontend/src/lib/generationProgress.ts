import type { QuestionSet } from '../types/question';

export type GenerationEvent =
  | { stage: 'generator_initial'; concept: string }
  | { stage: 'verify_round'; round: number; concept: string }
  | { stage: 'patch'; round: number; concept: string }
  | { stage: 'done'; question_set: QuestionSet }
  | { stage: 'error'; message: string };

export interface GenerationProgress {
  label: string;
  percent: number;
  done: boolean;
  errorMessage: string | null;
}

export const INITIAL_PROGRESS: GenerationProgress = {
  label: 'Not started yet.',
  percent: 0,
  done: false,
  errorMessage: null,
};

const PROGRESS_STEP = 8;
const MAX_PROGRESS_BEFORE_DONE = 95;

function stageLabel(evt: GenerationEvent): string {
  switch (evt.stage) {
    case 'generator_initial':
      return `Writing questions — ${evt.concept}…`;
    case 'verify_round':
      return `Checking quality (round ${evt.round}) — ${evt.concept}…`;
    case 'patch':
      return `Fixing flagged questions (round ${evt.round}) — ${evt.concept}…`;
    case 'done':
      return 'Done — questions ready.';
    case 'error':
      return evt.message;
  }
}

export function nextGenerationProgress(prev: GenerationProgress, evt: GenerationEvent): GenerationProgress {
  if (evt.stage === 'error') {
    return { label: stageLabel(evt), percent: prev.percent, done: true, errorMessage: evt.message };
  }
  if (evt.stage === 'done') {
    return { label: stageLabel(evt), percent: 100, done: true, errorMessage: null };
  }
  return {
    label: stageLabel(evt),
    percent: Math.min(MAX_PROGRESS_BEFORE_DONE, prev.percent + PROGRESS_STEP),
    done: false,
    errorMessage: null,
  };
}
