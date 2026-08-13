import { describe, expect, it } from 'vitest';
import { INITIAL_PROGRESS, nextGenerationProgress, type GenerationEvent } from './generationProgress';

describe('nextGenerationProgress', () => {
  it('starts at 0%, not done', () => {
    expect(INITIAL_PROGRESS).toEqual({ label: 'Not started yet.', percent: 0, done: false, errorMessage: null });
  });

  it('advances percent and sets a labeled message on generator_initial', () => {
    const evt: GenerationEvent = { stage: 'generator_initial', concept: 'Photosynthesis' };
    const result = nextGenerationProgress(INITIAL_PROGRESS, evt);
    expect(result.percent).toBe(8);
    expect(result.label).toContain('Photosynthesis');
    expect(result.done).toBe(false);
  });

  it('caps percent at 95 before a done event arrives', () => {
    let progress = INITIAL_PROGRESS;
    for (let i = 0; i < 20; i++) {
      progress = nextGenerationProgress(progress, { stage: 'verify_round', round: 1, concept: 'X' });
    }
    expect(progress.percent).toBe(95);
    expect(progress.done).toBe(false);
  });

  it('jumps to 100% and done on the done event', () => {
    const result = nextGenerationProgress(INITIAL_PROGRESS, { stage: 'done', question_set: { questions: [] } });
    expect(result.percent).toBe(100);
    expect(result.done).toBe(true);
    expect(result.errorMessage).toBeNull();
  });

  it('marks done with the error message on the error event', () => {
    const result = nextGenerationProgress(INITIAL_PROGRESS, { stage: 'error', message: 'Generation failed. Please try again.' });
    expect(result.done).toBe(true);
    expect(result.errorMessage).toBe('Generation failed. Please try again.');
  });
});
