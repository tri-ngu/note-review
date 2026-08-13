# Upload/Checkpoint/Generating Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the three missing v1 frontend stages — Upload, Analyzer Checkpoint, Generating — wired to the real backend, reusing the visual language of `design-mockups/selected-design.html` (the "Botanical Field Guide" journal theme already used by the existing flashcard view), and route the app through them before landing on the existing flashcard/Review view.

**Architecture:** Three new presentational stage components (`UploadStage`, `CheckpointStage`, `GeneratingStage`) live under `frontend/src/pages/`, sharing a `JournalShell` wrapper for the mockup's cover/tab/page chrome. All network orchestration (fetch calls, SSE stream reading, stage transitions) stays in `App.tsx`'s existing top-level component (renamed `SessionFlow`), which already owns this responsibility for the ready-state (browse/review) today. Pure logic (weight rebalancing on delete, checkpoint total/validity math, SSE buffer parsing, generation progress reduction) is extracted into small tested `lib/` modules, matching this repo's existing pattern (`shuffle.ts`, `scoring.ts`, `validateEdit.ts`) of keeping components thin and logic unit-tested.

**Tech Stack:** React 19 + TypeScript + Vite, CSS Modules, Vitest, react-router-dom v7 (routing unchanged — no new routes; these stages are `SessionFlow`-internal states under `/`, exactly like the existing browse/review toggle).

**Spec:** `DESIGN.md` (API contract, generation pipeline, SSE event shapes), `requirements.md` (Analyzer checkpoint acceptance criteria, error handling), `CONTEXT.md` (terminology), `design-mockups/selected-design.html` (visual/interaction reference — demo-only elements excluded, see Global Constraints).

## Global Constraints

- Do not modify `DESIGN.md`, `CONTEXT.md`, `requirements.md`, or `PROGRESS.md` — read-only per `PROGRESS.md`'s "Parts not to touch".
- Do not modify `.env`.
- Weights must re-sum to 100 (±0.05 client-side gate; backend's own `/generate` gate is ±1.0) before the Confirm button is enabled — `requirements.md` Analyzer checkpoint acceptance criteria.
- Question count total locks server-side the instant `/generate` is called — client never re-edits after that point.
- Backend error codes for `/upload` are exactly `not_a_pdf` / `file_too_large` / `no_extractable_text` (`backend/app/extraction.py`); `/generate` SSE `error` stage message is the generic `"Generation failed. Please try again."` (`backend/app/generation_http.py`'s `GENERIC_FAILURE_MESSAGE`) — never show pipeline internals, per `requirements.md` Error handling.
- Remove every demo-only element from the mockup: the "Preview state" button row (`#stateBtnRow`) and the "Show next stage" simulate button (`#simulateBtn`) — these exist only to let a reviewer preview all 3 sections' visual states in one static file; the real app drives state from actual backend responses instead.
- SSE event shapes are exactly what `backend/app/pipeline.py` emits: `{stage:"generator_initial", concept}`, `{stage:"verify_round", round, concept}`, `{stage:"patch", round, concept}`, `{stage:"done", question_set}`, `{stage:"error", message}` — confirmed by reading `pipeline.py`'s `on_event(...)` call sites, not assumed from `DESIGN.md` prose alone.

---

## File Structure

```
frontend/src/
  types/
    allocation.ts          NEW  — ConceptSnippet, ConceptAllocation (mirrors backend/app/models.py)
  lib/
    rebalanceWeights.ts     NEW  — pure: redistribute weight_percentage on concept delete
    rebalanceWeights.test.ts NEW
    checkpointTotals.ts     NEW  — pure: total weight/questions + balanced check
    checkpointTotals.test.ts NEW
    sseParse.ts              NEW  — pure: split a raw SSE text buffer into parsed events + remainder
    sseParse.test.ts         NEW
    generationProgress.ts    NEW  — pure: SSE event -> {label, percent, done, errorMessage}
    generationProgress.test.ts NEW
    runGeneration.ts         NEW  — async: POST + read SSE stream, calls onEvent per event (network-bound, untested — matches existing untested async handlers in App.tsx/useRoomSocket.ts)
  components/
    JournalShell.tsx         NEW  — shared cover/section-tab/page chrome (ported from mockup's .journal/.cover/.section-tab/.page)
    JournalShell.module.css  NEW
  pages/
    UploadStage.tsx           NEW
    UploadStage.module.css    NEW
    CheckpointStage.tsx       NEW
    CheckpointStage.module.css NEW
    GeneratingStage.tsx       NEW
    GeneratingStage.module.css NEW
  App.tsx                    MODIFY — SessionFlow orchestrates stage transitions; ready-stage logic (browse/review, updateQuestion, room buttons) unchanged, now gated behind stage.name === 'ready'
```

## Judgment call flagged for approval

The mockup's Checkpoint section includes a per-concept **Delete** button and an editable **concept name** field, neither of which is in `requirements.md`'s Analyzer-checkpoint acceptance criteria (that section only requires editing `weight_percentage`/`question_count`). This is compatible with the already-decided "Analyzer-checkpoint allocation edits are pure client-side, full edited allocation sent as the `/generate` request body" direction (`PROGRESS.md`'s Required Documents section) — deleting/renaming an entry before confirm just changes what's in that client-side array, no backend change needed. This plan **includes** Delete + Rename, matching the mockup, on that basis. Flagging in case Tri wants it cut to the literal requirements.md scope instead.

---

### Task 1: Shared allocation types

**Files:**
- Create: `frontend/src/types/allocation.ts`

**Interfaces:**
- Produces: `ConceptSnippet { quote: string; page_number: number }`, `ConceptAllocation { concept: string; weight_percentage: number; question_count: number; snippets: ConceptSnippet[] }` — used by every later task.

- [ ] **Step 1: Write the file**

```ts
export interface ConceptSnippet {
  quote: string;
  page_number: number;
}

export interface ConceptAllocation {
  concept: string;
  weight_percentage: number;
  question_count: number;
  snippets: ConceptSnippet[];
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors (new file has no consumers yet, but must parse cleanly).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/allocation.ts
git commit -m "feat: add ConceptAllocation frontend types"
```

---

### Task 2: `rebalanceWeights` — pure weight redistribution on delete

**Files:**
- Create: `frontend/src/lib/rebalanceWeights.ts`
- Test: `frontend/src/lib/rebalanceWeights.test.ts`

**Interfaces:**
- Consumes: any array of `{ weight_percentage: number }`-shaped objects.
- Produces: `rebalanceWeightsAfterDelete<T extends { weight_percentage: number }>(remaining: T[], removedWeight: number): T[]` — new array, same order, `weight_percentage` redistributed proportionally so the set still sums to 100 (rounded to 2 decimals). Consumed by Task 8 (`CheckpointStage`).

- [ ] **Step 1: Write the failing tests**

```ts
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/lib/rebalanceWeights.test.ts`
Expected: FAIL — `rebalanceWeights.ts` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```ts
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/rebalanceWeights.test.ts`
Expected: PASS (4/4)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/rebalanceWeights.ts frontend/src/lib/rebalanceWeights.test.ts
git commit -m "feat: add pure weight-rebalance logic for checkpoint concept deletion"
```

---

### Task 3: `checkpointTotals` — pure total/validity math

**Files:**
- Create: `frontend/src/lib/checkpointTotals.ts`
- Test: `frontend/src/lib/checkpointTotals.test.ts`

**Interfaces:**
- Consumes: array of `{ weight_percentage: number; question_count: number }`.
- Produces: `computeCheckpointTotals(allocations): { totalWeight: number; totalQuestions: number; isBalanced: boolean }`. Consumed by Task 8.

- [ ] **Step 1: Write the failing tests**

```ts
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/lib/checkpointTotals.test.ts`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Write the implementation**

```ts
export interface CheckpointTotals {
  totalWeight: number;
  totalQuestions: number;
  isBalanced: boolean;
}

const WEIGHT_TOLERANCE = 0.05;

export function computeCheckpointTotals(
  allocations: { weight_percentage: number; question_count: number }[],
): CheckpointTotals {
  const totalWeight = allocations.reduce((sum, a) => sum + a.weight_percentage, 0);
  const totalQuestions = allocations.reduce((sum, a) => sum + a.question_count, 0);
  const isBalanced = Math.abs(totalWeight - 100) <= WEIGHT_TOLERANCE;
  return { totalWeight, totalQuestions, isBalanced };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/checkpointTotals.test.ts`
Expected: PASS (4/4)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/checkpointTotals.ts frontend/src/lib/checkpointTotals.test.ts
git commit -m "feat: add pure checkpoint total/balance math"
```

---

### Task 4: `sseParse` — pure SSE buffer parsing

**Files:**
- Create: `frontend/src/lib/sseParse.ts`
- Test: `frontend/src/lib/sseParse.test.ts`

**Interfaces:**
- Produces: `parseSseBuffer<T>(buffer: string): { events: T[]; remainder: string }` — splits accumulated raw SSE text on blank lines, parses each complete `data: {...}` block as JSON, returns any trailing incomplete chunk as `remainder` for the caller to prepend to the next network read. Consumed by Task 10 (`runGeneration`).

- [ ] **Step 1: Write the failing tests**

```ts
import { describe, expect, it } from 'vitest';
import { parseSseBuffer } from './sseParse';

describe('parseSseBuffer', () => {
  it('parses a single complete event with no remainder', () => {
    const result = parseSseBuffer<{ stage: string }>('data: {"stage":"done"}\n\n');
    expect(result).toEqual({ events: [{ stage: 'done' }], remainder: '' });
  });

  it('parses multiple complete events in one buffer', () => {
    const buffer = 'data: {"stage":"a"}\n\ndata: {"stage":"b"}\n\n';
    const result = parseSseBuffer<{ stage: string }>(buffer);
    expect(result.events).toEqual([{ stage: 'a' }, { stage: 'b' }]);
    expect(result.remainder).toBe('');
  });

  it('keeps a trailing incomplete event as remainder', () => {
    const buffer = 'data: {"stage":"a"}\n\ndata: {"stage":"b"';
    const result = parseSseBuffer<{ stage: string }>(buffer);
    expect(result.events).toEqual([{ stage: 'a' }]);
    expect(result.remainder).toBe('data: {"stage":"b"');
  });

  it('returns no events for an empty buffer', () => {
    expect(parseSseBuffer('')).toEqual({ events: [], remainder: '' });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/lib/sseParse.test.ts`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Write the implementation**

```ts
export interface ParsedSseChunk<T> {
  events: T[];
  remainder: string;
}

export function parseSseBuffer<T>(buffer: string): ParsedSseChunk<T> {
  const parts = buffer.split('\n\n');
  const remainder = parts.pop() ?? '';
  const events: T[] = [];

  for (const part of parts) {
    const dataLine = part.split('\n').find((line) => line.startsWith('data: '));
    if (!dataLine) continue;
    events.push(JSON.parse(dataLine.slice('data: '.length)) as T);
  }

  return { events, remainder };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/sseParse.test.ts`
Expected: PASS (4/4)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/sseParse.ts frontend/src/lib/sseParse.test.ts
git commit -m "feat: add pure SSE buffer parser"
```

---

### Task 5: `generationProgress` — pure event-to-progress reducer

**Files:**
- Create: `frontend/src/lib/generationProgress.ts`
- Test: `frontend/src/lib/generationProgress.test.ts`

**Interfaces:**
- Consumes: nothing external.
- Produces: `GenerationEvent` (union matching `pipeline.py`'s `on_event` payloads plus the terminal `done`/`error` stages), `GenerationProgress { label: string; percent: number; done: boolean; errorMessage: string | null }`, `INITIAL_PROGRESS`, `nextGenerationProgress(prev, evt): GenerationProgress`. Consumed by Task 9 (`GeneratingStage`) and Task 11 (`App.tsx`).

- [ ] **Step 1: Write the failing tests**

```ts
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/lib/generationProgress.test.ts`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Write the implementation**

```ts
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/generationProgress.test.ts`
Expected: PASS (5/5)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/generationProgress.ts frontend/src/lib/generationProgress.test.ts
git commit -m "feat: add pure generation-progress reducer for SSE events"
```

---

### Task 6: `JournalShell` — shared cover/tab/page chrome

**Files:**
- Create: `frontend/src/components/JournalShell.tsx`
- Create: `frontend/src/components/JournalShell.module.css`

**Interfaces:**
- Produces: `JournalShell({ title, subtitle, stepEyebrow, stepTitle, stepDescription, children }): JSX.Element`. Consumed by Tasks 7, 8, 9.

- [ ] **Step 1: Write `JournalShell.module.css`** (ported from `design-mockups/selected-design.html` lines 34–105, palette scoped to `.journal` so descendant modules can reference the same custom properties via normal CSS cascade)

```css
.journal {
  --cream: #f4f2e6;
  --sage: #8fa684;
  --forest: #4b6043;
  --olive: #34402c;
  --gold: #a3742a;
  --line: #c8cdb5;

  min-height: 100vh;
  max-width: 900px;
  margin: 0 auto;
  padding: 2rem 1.25rem 5rem 1.25rem;
  background: var(--cream);
  color: var(--olive);
  font-family: Constantia, Georgia, serif;
  font-size: 16px;
  line-height: 1.55;
  box-sizing: border-box;
}
.journal * {
  box-sizing: border-box;
}
.journal h1,
.journal h2,
.journal label,
.journal button {
  font-family: Rockwell, Georgia, serif;
}

.cover {
  text-align: center;
  padding-bottom: 1.75rem;
}
.cover .leaf {
  font-size: 1.7rem;
  color: var(--forest);
  display: block;
}
.cover h1 {
  margin: 0.25rem 0 0 0;
  font-size: 1.9rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}
.cover p {
  margin: 0.35rem 0 0 0;
  font-style: italic;
  color: var(--forest);
  font-size: 0.95rem;
}

.sectionTab {
  background: var(--sage);
  color: #fff;
  padding: 1rem 1.75rem 2.1rem 1.75rem;
  margin-top: 1.5rem;
  clip-path: polygon(
    0 0,
    100% 0,
    100% 82%,
    87.5% 100%,
    75% 82%,
    62.5% 100%,
    50% 82%,
    37.5% 100%,
    25% 82%,
    12.5% 100%,
    0 82%
  );
}
.tabEyebrow {
  font-size: 0.7rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--cream);
  opacity: 0.85;
  margin: 0 0 0.2rem 0;
}
.sectionTab h2 {
  margin: 0;
  font-size: 1.3rem;
  letter-spacing: 0.03em;
}
.sectionTab p {
  margin: 0.4rem 0 0 0;
  font-size: 0.88rem;
  font-style: italic;
  color: #f2f5ee;
  max-width: 60ch;
}

.page {
  background: var(--cream);
  background-image: linear-gradient(var(--line) 1px, transparent 1px),
    linear-gradient(90deg, var(--line) 1px, transparent 1px);
  background-size: 100% 32px, 32px 100%;
  border: 1px solid var(--line);
  border-top: none;
  padding: 2rem 1.75rem 2.25rem 1.75rem;
}
```

- [ ] **Step 2: Write `JournalShell.tsx`**

```tsx
import type { ReactNode } from 'react';
import styles from './JournalShell.module.css';

interface JournalShellProps {
  title: string;
  subtitle: string;
  stepEyebrow: string;
  stepTitle: string;
  stepDescription: string;
  children: ReactNode;
}

export function JournalShell({ title, subtitle, stepEyebrow, stepTitle, stepDescription, children }: JournalShellProps) {
  return (
    <div className={styles.journal}>
      <div className={styles.cover}>
        <span className={styles.leaf}>❧</span>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <section aria-labelledby="stage-heading">
        <div className={styles.sectionTab}>
          <p className={styles.tabEyebrow}>{stepEyebrow}</p>
          <h2 id="stage-heading">{stepTitle}</h2>
          <p>{stepDescription}</p>
        </div>
        <div className={styles.page}>{children}</div>
      </section>
    </div>
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/JournalShell.tsx frontend/src/components/JournalShell.module.css
git commit -m "feat: add shared JournalShell chrome for the pre-generation stages"
```

---

### Task 7: `UploadStage`

**Files:**
- Create: `frontend/src/pages/UploadStage.tsx`
- Create: `frontend/src/pages/UploadStage.module.css`

**Interfaces:**
- Consumes: `JournalShell` (Task 6).
- Produces: `UploadStage({ onUploaded: (concepts: ConceptAllocation[]) => void }): JSX.Element`. Consumed by Task 11.

- [ ] **Step 1: Write `UploadStage.module.css`** (ported from mockup lines 108–161, 163–185; drops `.tab-btn-row`/`.tab-btn`/`.caption` — demo-only preview-state controls)

```css
.dropzone {
  border: 2px dashed var(--sage);
  background: #fff;
  padding: 2.25rem 1.5rem;
  text-align: center;
  position: relative;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}
.dropzone:hover {
  border-color: var(--forest);
  background: #f7f6ec;
}
.dragover {
  border-color: var(--forest);
  background: #eef1e6;
  border-style: solid;
}
.isError {
  border-color: var(--gold);
}
.leaf {
  font-size: 1.5rem;
  color: var(--forest);
  display: block;
  margin-bottom: 0.4rem;
}
.dzFace p {
  margin: 0.25rem 0;
}
.browseBtn {
  margin-top: 0.75rem;
  background: none;
  border: 1px solid var(--olive);
  color: var(--olive);
  padding: 0.5rem 1.1rem;
  font-size: 0.82rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  cursor: pointer;
}
.browseBtn:hover {
  background: var(--olive);
  color: var(--cream);
}
.hidden {
  display: none !important;
}
.spinner {
  width: 26px;
  height: 26px;
  margin: 0 auto 0.8rem auto;
  border: 3px solid var(--line);
  border-top-color: var(--forest);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.dzError {
  margin-top: 0.85rem;
  border-left: 3px solid var(--gold);
  background: #f8f0df;
  padding: 0.7rem 0.9rem;
  font-size: 0.9rem;
}
.fieldRow {
  margin-top: 1.5rem;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}
.fieldRow label {
  font-size: 0.76rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--forest);
}
.qcountInput {
  font-family: Constantia, Georgia, serif;
  font-size: 1rem;
  padding: 0.5rem 0.6rem;
  border: 1px solid var(--olive);
  background: #fff;
  color: var(--olive);
  width: 230px;
  max-width: 100%;
}
```

- [ ] **Step 2: Write `UploadStage.tsx`**

```tsx
import { useRef, useState } from 'react';
import type { DragEvent } from 'react';
import type { ConceptAllocation } from '../types/allocation';
import { JournalShell } from '../components/JournalShell';
import styles from './UploadStage.module.css';

interface UploadStageProps {
  onUploaded: (concepts: ConceptAllocation[]) => void;
}

type UploadStatus = 'idle' | 'analyzing';

const ERROR_MESSAGES: Record<string, string> = {
  not_a_pdf: "That file isn't a PDF. Upload a PDF and try again.",
  file_too_large: 'This file is over the 20MB limit.',
  no_extractable_text: "This PDF has no selectable text (likely a scan) — we can't read it.",
  generation_failed: 'Something went wrong analyzing your Note. Please try again.',
  network: 'Could not reach the backend. Check your connection and try again.',
};

export function UploadStage({ onUploaded }: UploadStageProps) {
  const [status, setStatus] = useState<UploadStatus>('idle');
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [targetCount, setTargetCount] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setErrorCode(null);
    setStatus('analyzing');

    const formData = new FormData();
    formData.append('file', file);
    const trimmedCount = targetCount.trim();
    if (trimmedCount !== '') {
      formData.append('target_question_count', trimmedCount);
    }

    try {
      const res = await fetch('/upload', { method: 'POST', body: formData });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        setErrorCode(body.detail && ERROR_MESSAGES[body.detail] ? body.detail : 'generation_failed');
        setStatus('idle');
        return;
      }
      const data = (await res.json()) as { concepts: ConceptAllocation[] };
      onUploaded(data.concepts);
    } catch {
      setErrorCode('network');
      setStatus('idle');
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) void handleFile(file);
  }

  return (
    <JournalShell
      title="Note Review"
      subtitle="Upload a Note to generate a Question Set"
      stepEyebrow="Step 1"
      stepTitle="Upload"
      stepDescription="Upload a Note (PDF). It's read and broken into concepts before anything else happens."
    >
      <div
        className={`${styles.dropzone} ${dragOver ? styles.dragover : ''} ${errorCode ? styles.isError : ''}`}
        role="button"
        tabIndex={0}
        aria-label="Drop a PDF here or browse to select one"
        onClick={() => status === 'idle' && fileInputRef.current?.click()}
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && status === 'idle') {
            e.preventDefault();
            fileInputRef.current?.click();
          }
        }}
        onDragEnter={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={(e) => {
          e.preventDefault();
          setDragOver(false);
        }}
        onDrop={onDrop}
      >
        {status === 'idle' ? (
          <div className={styles.dzFace}>
            <span className={styles.leaf}>❧</span>
            <p>Drop the Note here</p>
            <p style={{ fontSize: '.85rem', opacity: 0.75 }}>— or —</p>
            <button
              type="button"
              className={styles.browseBtn}
              onClick={(e) => {
                e.stopPropagation();
                fileInputRef.current?.click();
              }}
            >
              Browse files
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              className={styles.hidden}
              aria-hidden="true"
              tabIndex={-1}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleFile(file);
                e.target.value = '';
              }}
            />
          </div>
        ) : (
          <div className={styles.dzFace}>
            <div className={styles.spinner} role="status" aria-live="polite" />
            <p>Analyzing your Note…</p>
          </div>
        )}
      </div>
      {errorCode && (
        <div className={styles.dzError} role="alert">
          {ERROR_MESSAGES[errorCode]}
        </div>
      )}

      <div className={styles.fieldRow}>
        <label htmlFor="qCount">Target question count</label>
        <input
          type="number"
          id="qCount"
          className={styles.qcountInput}
          min={1}
          placeholder="Auto — let AI decide"
          value={targetCount}
          disabled={status === 'analyzing'}
          onChange={(e) => setTargetCount(e.target.value)}
        />
      </div>
    </JournalShell>
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/UploadStage.tsx frontend/src/pages/UploadStage.module.css
git commit -m "feat: add UploadStage wired to POST /upload"
```

---

### Task 8: `CheckpointStage`

**Files:**
- Create: `frontend/src/pages/CheckpointStage.tsx`
- Create: `frontend/src/pages/CheckpointStage.module.css`

**Interfaces:**
- Consumes: `JournalShell` (Task 6), `rebalanceWeightsAfterDelete` (Task 2), `computeCheckpointTotals` (Task 3), `ConceptAllocation` (Task 1).
- Produces: `CheckpointStage({ allocations: ConceptAllocation[]; onConfirm: (allocations: ConceptAllocation[]) => void }): JSX.Element`. Consumed by Task 11.

- [ ] **Step 1: Write `CheckpointStage.module.css`** (ported from mockup lines 219–417, dropping nothing — every element here is real functionality, not demo)

```css
.totalBar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem;
  background: #fff;
  border: 1px solid var(--olive);
  padding: 0.85rem 1.1rem;
  margin-bottom: 0.5rem;
}
.totalFigure {
  font-size: 1.1rem;
  font-weight: bold;
}
.totalFigureValue {
  color: var(--forest);
}
.totalFigure.warn .totalFigureValue {
  color: var(--gold);
}
.qTotal {
  font-size: 0.78rem;
  opacity: 0.75;
}
.totalMsg {
  font-size: 0.85rem;
  font-style: italic;
  color: var(--forest);
  margin: 0 0 1.5rem 0;
}
.totalMsg.warn {
  color: var(--gold);
  font-style: normal;
}

.entries {
  display: flex;
  flex-direction: column;
}
.entry {
  padding: 1.2rem 0;
  border-bottom: 1px dashed var(--line);
}
.entry:first-child {
  padding-top: 0;
}
.entryHead {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.entryIndex {
  font-size: 0.75rem;
  letter-spacing: 0.06em;
  color: var(--gold);
  text-transform: uppercase;
  margin-top: 0.2rem;
}
.entryNameInput {
  flex: 1 1 240px;
  font-family: Rockwell, Georgia, serif;
  font-size: 1.05rem;
  font-weight: bold;
  color: var(--olive);
  background: transparent;
  border: 1px solid transparent;
  padding: 0.15rem 0.3rem;
  margin: 0;
}
.entryNameInput:hover {
  border-color: var(--line);
  background: #fff;
}
.entryNameInput:focus {
  border-color: var(--olive);
  background: #fff;
  outline: none;
}

.strikeBtn {
  background: #fff;
  border: 1px solid var(--gold);
  color: var(--gold);
  font-size: 0.72rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  padding: 0.45rem 1rem 0.45rem 0.7rem;
  cursor: pointer;
  clip-path: polygon(0 0, 88% 0, 100% 14%, 88% 28%, 100% 42%, 88% 56%, 100% 70%, 88% 84%, 100% 100%, 0 100%);
}
.strikeBtn:hover {
  background: var(--gold);
  color: #fff;
}

.entryFields {
  display: flex;
  align-items: flex-end;
  gap: 1.75rem;
  flex-wrap: wrap;
  margin-top: 0.85rem;
}
.fieldBlock label {
  display: block;
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--forest);
  margin-bottom: 0.3rem;
}
.fieldBlock input {
  font-family: Constantia, Georgia, serif;
  font-size: 0.95rem;
  padding: 0.4rem 0.5rem;
  border: 1px solid var(--olive);
  background: #fdfcf6;
  color: var(--olive);
  width: 105px;
}

.toggleQuote {
  margin-top: 0.9rem;
  background: none;
  border: none;
  border-bottom: 1px dotted var(--forest);
  color: var(--forest);
  font-family: Constantia, Georgia, serif;
  font-size: 0.85rem;
  font-style: italic;
  padding: 0.15rem 0;
  cursor: pointer;
}
.toggleQuote:hover {
  color: var(--olive);
}

.quotePanel {
  margin-top: 0.7rem;
  border-left: 3px solid var(--sage);
  background: #f6f5ec;
  padding: 0.7rem 1rem;
}
.quotePanel p {
  margin: 0 0 0.3rem 0;
  font-style: italic;
  font-size: 0.92rem;
}
.quotePage {
  margin: 0;
  font-size: 0.74rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--gold);
}

.confirmRow {
  position: sticky;
  bottom: 0;
  margin-top: 1.75rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  background: var(--cream);
  border-top: 1px solid var(--olive);
  padding: 1rem 0;
  box-shadow: 0 -8px 12px -10px rgba(40, 50, 30, 0.4);
}
.confirmBtn {
  font-family: Rockwell, Georgia, serif;
  font-size: 0.88rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  background: var(--forest);
  color: #fff;
  border: 1px solid var(--forest);
  padding: 0.75rem 1.5rem;
  cursor: pointer;
}
.confirmBtn:disabled {
  background: #cfd3c3;
  border-color: #cfd3c3;
  color: #7a806f;
  cursor: not-allowed;
}
.confirmBtn:not(:disabled):hover {
  background: var(--olive);
  border-color: var(--olive);
}
.confirmNote {
  font-size: 0.85rem;
  font-style: italic;
  color: var(--forest);
}
```

- [ ] **Step 2: Write `CheckpointStage.tsx`**

```tsx
import { useState } from 'react';
import type { ConceptAllocation } from '../types/allocation';
import { rebalanceWeightsAfterDelete } from '../lib/rebalanceWeights';
import { computeCheckpointTotals } from '../lib/checkpointTotals';
import { JournalShell } from '../components/JournalShell';
import styles from './CheckpointStage.module.css';

interface CheckpointStageProps {
  allocations: ConceptAllocation[];
  onConfirm: (allocations: ConceptAllocation[]) => void;
}

interface Entry extends ConceptAllocation {
  id: string;
}

function toId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : Math.random().toString(36).slice(2);
}

export function CheckpointStage({ allocations, onConfirm }: CheckpointStageProps) {
  const [entries, setEntries] = useState<Entry[]>(() => allocations.map((a) => ({ ...a, id: toId() })));
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [confirmed, setConfirmed] = useState(false);

  const totals = computeCheckpointTotals(entries);

  function updateEntry(id: string, patch: Partial<Pick<Entry, 'concept' | 'weight_percentage' | 'question_count'>>) {
    setConfirmed(false);
    setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, ...patch } : e)));
  }

  function deleteEntry(id: string) {
    setConfirmed(false);
    setEntries((prev) => {
      const removed = prev.find((e) => e.id === id);
      const rest = prev.filter((e) => e.id !== id);
      if (!removed) return rest;
      return rebalanceWeightsAfterDelete(rest, removed.weight_percentage);
    });
  }

  function toggleQuote(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleConfirm() {
    if (!totals.isBalanced) return;
    setConfirmed(true);
    onConfirm(entries.map(({ id, ...rest }) => rest));
  }

  return (
    <JournalShell
      title="Note Review"
      subtitle="Concepts found in your Note"
      stepEyebrow="Step 2"
      stepTitle="Checkpoint"
      stepDescription="Concepts found in your Note, each with a weight and question count. Adjust or remove any before continuing."
    >
      <div className={styles.totalBar}>
        <div className={`${styles.totalFigure} ${!totals.isBalanced ? styles.warn : ''}`}>
          Total weight: <span className={styles.totalFigureValue}>{totals.totalWeight.toFixed(1)}</span>%
        </div>
        <div className={styles.qTotal}>Total questions: {totals.totalQuestions}</div>
      </div>
      <p className={`${styles.totalMsg} ${!totals.isBalanced ? styles.warn : ''}`}>
        {totals.isBalanced
          ? 'Ready to continue.'
          : `Weights must add up to 100% before you can continue — currently ${totals.totalWeight.toFixed(1)}%.`}
      </p>

      <div className={styles.entries}>
        {entries.map((entry, i) => {
          const expanded = expandedIds.has(entry.id);
          const snippet = entry.snippets[0];
          return (
            <div key={entry.id} className={styles.entry}>
              <div className={styles.entryHead}>
                <span className={styles.entryIndex}>{String(i + 1).padStart(2, '0')}</span>
                <input
                  type="text"
                  className={styles.entryNameInput}
                  aria-label="Concept name"
                  value={entry.concept}
                  onChange={(e) => updateEntry(entry.id, { concept: e.target.value })}
                />
                <button type="button" className={styles.strikeBtn} onClick={() => deleteEntry(entry.id)}>
                  Delete
                </button>
              </div>
              <div className={styles.entryFields}>
                <div className={styles.fieldBlock}>
                  <label htmlFor={`weight-${entry.id}`}>Weight %</label>
                  <input
                    id={`weight-${entry.id}`}
                    type="number"
                    min={0}
                    step={0.01}
                    value={entry.weight_percentage}
                    onChange={(e) => updateEntry(entry.id, { weight_percentage: parseFloat(e.target.value) || 0 })}
                  />
                </div>
                <div className={styles.fieldBlock}>
                  <label htmlFor={`count-${entry.id}`}>Question count</label>
                  <input
                    id={`count-${entry.id}`}
                    type="number"
                    min={0}
                    step={1}
                    value={entry.question_count}
                    onChange={(e) => updateEntry(entry.id, { question_count: parseInt(e.target.value, 10) || 0 })}
                  />
                </div>
              </div>
              {snippet && (
                <>
                  <button type="button" className={styles.toggleQuote} onClick={() => toggleQuote(entry.id)}>
                    {expanded ? '❧ Hide source quote' : '❧ View source quote'}
                  </button>
                  {expanded && (
                    <div className={styles.quotePanel}>
                      <p>&ldquo;{snippet.quote}&rdquo;</p>
                      <p className={styles.quotePage}>Page {snippet.page_number}</p>
                    </div>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>

      <div className={styles.confirmRow}>
        <button className={styles.confirmBtn} disabled={!totals.isBalanced} onClick={handleConfirm}>
          Confirm and Continue
        </button>
        {confirmed && <span className={styles.confirmNote}>Confirmed.</span>}
      </div>
    </JournalShell>
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/CheckpointStage.tsx frontend/src/pages/CheckpointStage.module.css
git commit -m "feat: add CheckpointStage with editable weight/count/name and delete"
```

---

### Task 9: `GeneratingStage`

**Files:**
- Create: `frontend/src/pages/GeneratingStage.tsx`
- Create: `frontend/src/pages/GeneratingStage.module.css`

**Interfaces:**
- Consumes: `JournalShell` (Task 6), `GenerationProgress` (Task 5).
- Produces: `GeneratingStage({ progress: GenerationProgress; resumed?: boolean }): JSX.Element` — purely presentational, no network calls (owner of the network call is `App.tsx`, Task 11). Consumed by Task 11.

- [ ] **Step 1: Write `GeneratingStage.module.css`** (ported from mockup lines 419–476, dropping `.log-btn` — that class only ever backed the removed "Show next stage" demo button)

```css
.trailWrap {
  background: #fff;
  border: 1px solid var(--olive);
  padding: 2rem 1.5rem;
  text-align: center;
}

.growDial {
  width: 150px;
  height: 150px;
  border-radius: 50%;
  margin: 0 auto 1.25rem auto;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--line);
  transition: background 0.4s ease;
}
.growDialInner {
  width: 112px;
  height: 112px;
  border-radius: 50%;
  background: var(--cream);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.pctNum {
  font-family: Rockwell, Georgia, serif;
  font-size: 1.6rem;
  color: var(--olive);
}
.pctCap {
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--forest);
}
.stageLabel {
  margin: 0;
  font-size: 1.05rem;
  min-height: 1.4em;
}
```

- [ ] **Step 2: Write `GeneratingStage.tsx`**

```tsx
import type { GenerationProgress } from '../lib/generationProgress';
import { JournalShell } from '../components/JournalShell';
import styles from './GeneratingStage.module.css';

interface GeneratingStageProps {
  progress: GenerationProgress;
  resumed?: boolean;
}

function dialGradient(pct: number): string {
  const clamped = Math.max(0, Math.min(100, pct));
  return `conic-gradient(var(--forest) 0% ${clamped}%, var(--sage) ${clamped}% 100%)`;
}

export function GeneratingStage({ progress, resumed }: GeneratingStageProps) {
  return (
    <JournalShell
      title="Note Review"
      subtitle="Writing your Question Set"
      stepEyebrow="Step 3"
      stepTitle="Generating Questions"
      stepDescription="Questions are written from the confirmed concepts, then checked and revised over several rounds."
    >
      <div className={styles.trailWrap}>
        <div className={styles.growDial} style={{ background: dialGradient(progress.percent) }}>
          <div className={styles.growDialInner}>
            <span className={styles.pctNum}>{progress.percent}%</span>
            <span className={styles.pctCap}>Complete</span>
          </div>
        </div>
        <p className={styles.stageLabel}>
          {resumed ? 'A generation run for this session is already in progress — checking back for results…' : progress.label}
        </p>
      </div>
    </JournalShell>
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/GeneratingStage.tsx frontend/src/pages/GeneratingStage.module.css
git commit -m "feat: add presentational GeneratingStage progress dial"
```

---

### Task 10: `runGeneration` — SSE stream consumer

**Files:**
- Create: `frontend/src/lib/runGeneration.ts`

**Interfaces:**
- Consumes: `parseSseBuffer` (Task 4), `GenerationEvent` (Task 5).
- Produces: `runGeneration({ endpoint, body?, onEvent }): Promise<void>`. Consumed by Task 11.
- Not unit tested: network/stream-bound, matching this repo's existing convention of leaving async network glue (`App.tsx`'s `handleCreateRoom`, `useRoomSocket.ts`) untested while the pure logic it calls (here: `sseParse`, `generationProgress`) is tested — see Tasks 4–5.

- [ ] **Step 1: Write the implementation**

```ts
import { parseSseBuffer } from './sseParse';
import type { GenerationEvent } from './generationProgress';

interface RunGenerationArgs {
  endpoint: '/generate' | '/generate/retry';
  body?: unknown;
  onEvent: (evt: GenerationEvent) => void;
}

export async function runGeneration({ endpoint, body, onEvent }: RunGenerationArgs): Promise<void> {
  let res: Response;
  try {
    res = await fetch(endpoint, {
      method: 'POST',
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    onEvent({ stage: 'error', message: 'Could not reach the backend. Please try again.' });
    return;
  }

  if (!res.ok || !res.body) {
    onEvent({ stage: 'error', message: 'Could not start generation. Please try again.' });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { events, remainder } = parseSseBuffer<GenerationEvent>(buffer);
    buffer = remainder;
    for (const evt of events) onEvent(evt);
  }
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/runGeneration.ts
git commit -m "feat: add SSE-stream generation runner"
```

---

### Task 11: Wire `App.tsx` — SessionFlow orchestration

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `UploadStage` (7), `CheckpointStage` (8), `GeneratingStage` (9), `runGeneration` (10), `INITIAL_PROGRESS`/`nextGenerationProgress` (5), `ConceptAllocation` (1).
- Produces: same public behavior as today at `/` (browse/review/room-creation unchanged) plus the new pre-generation stages. No new routes.

- [ ] **Step 1: Replace `frontend/src/App.tsx`'s session-loading logic**

Full new file content:

```tsx
import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import type { Question, QuestionSet } from './types/question';
import type { ConceptAllocation } from './types/allocation';
import { renameConceptEverywhere } from './lib/renameConcept';
import { INITIAL_PROGRESS, nextGenerationProgress, type GenerationEvent, type GenerationProgress } from './lib/generationProgress';
import { runGeneration } from './lib/runGeneration';
import { FlashcardView } from './components/FlashcardView';
import { ReviewSession } from './components/ReviewSession';
import { UploadStage } from './pages/UploadStage';
import { CheckpointStage } from './pages/CheckpointStage';
import { GeneratingStage } from './pages/GeneratingStage';
import { HostPage } from './room/HostPage';
import { JoinPage } from './room/JoinPage';
import { PlayerPage } from './room/PlayerPage';

type SessionResponse = {
  status: 'empty' | 'checkpoint_pending' | 'generating' | 'ready' | 'failed';
  allocations?: ConceptAllocation[];
  questions?: Question[];
};

type Stage =
  | { name: 'loading' }
  | { name: 'session_error'; message: string }
  | { name: 'upload' }
  | { name: 'checkpoint'; allocations: ConceptAllocation[] }
  | { name: 'generating'; mode: 'live' | 'resumed'; progress: GenerationProgress }
  | { name: 'failed' }
  | { name: 'ready'; view: 'browse' | 'review'; questionSet: QuestionSet };

const SESSION_POLL_MS = 3000;

async function errorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string };
    return body.detail ?? `Request failed (${res.status})`;
  } catch {
    return `Request failed (${res.status})`;
  }
}

function SessionFlow() {
  const [stage, setStage] = useState<Stage>({ name: 'loading' });
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    fetch('/session')
      .then((res) => res.json() as Promise<SessionResponse>)
      .then((data) => {
        if (cancelled) return;
        if (data.status === 'ready' && data.questions) {
          setStage({ name: 'ready', view: 'browse', questionSet: { questions: data.questions } });
        } else if (data.status === 'checkpoint_pending' && data.allocations) {
          setStage({ name: 'checkpoint', allocations: data.allocations });
        } else if (data.status === 'generating') {
          setStage({ name: 'generating', mode: 'resumed', progress: INITIAL_PROGRESS });
        } else if (data.status === 'failed') {
          setStage({ name: 'failed' });
        } else {
          setStage({ name: 'upload' });
        }
      })
      .catch(() => {
        if (!cancelled) setStage({ name: 'session_error', message: 'Could not reach the backend.' });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Resumed mid-generation on reload: no live SSE stream to attach to, so poll
  // GET /session until the background pipeline task (which keeps running
  // server-side regardless of client connection) settles.
  useEffect(() => {
    if (stage.name !== 'generating' || stage.mode !== 'resumed') return;
    let cancelled = false;
    const interval = setInterval(() => {
      fetch('/session')
        .then((res) => res.json() as Promise<SessionResponse>)
        .then((data) => {
          if (cancelled) return;
          if (data.status === 'ready' && data.questions) {
            setStage({ name: 'ready', view: 'browse', questionSet: { questions: data.questions } });
          } else if (data.status === 'failed') {
            setStage({ name: 'failed' });
          }
        })
        .catch(() => {
          /* transient network hiccup — keep polling */
        });
    }, SESSION_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [stage]);

  function handleUploaded(concepts: ConceptAllocation[]) {
    setStage({ name: 'checkpoint', allocations: concepts });
  }

  function runLiveGeneration(endpoint: '/generate' | '/generate/retry', body?: unknown) {
    setStage({ name: 'generating', mode: 'live', progress: INITIAL_PROGRESS });
    void runGeneration({
      endpoint,
      body,
      onEvent: (evt: GenerationEvent) => {
        setStage((prev) => {
          if (prev.name !== 'generating') return prev;
          return { ...prev, progress: nextGenerationProgress(prev.progress, evt) };
        });
        if (evt.stage === 'done') {
          setStage({ name: 'ready', view: 'browse', questionSet: evt.question_set });
        } else if (evt.stage === 'error') {
          setStage({ name: 'failed' });
        }
      },
    });
  }

  function handleConfirm(allocations: ConceptAllocation[]) {
    runLiveGeneration('/generate', { allocations });
  }

  function handleRetry() {
    runLiveGeneration('/generate/retry');
  }

  const updateQuestion = async (index: number, updated: Question, renameFrom?: string): Promise<string | null> => {
    if (renameFrom) {
      const renameRes = await fetch(`/concepts/${encodeURIComponent(renameFrom)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_name: updated.concept }),
      });
      if (!renameRes.ok) {
        return `Could not rename concept: ${await errorDetail(renameRes)}`;
      }
    }

    const patchRes = await fetch(`/questions/${index + 1}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        concept: updated.concept,
        question_text: updated.question_text,
        options: updated.options,
        correct_answers: updated.correct_answers,
        is_select_all: updated.is_select_all,
        explanation: updated.explanation,
        page_number: updated.page_number,
      }),
    });
    if (!patchRes.ok) {
      return `Could not save question: ${await errorDetail(patchRes)}`;
    }
    const savedQuestion = (await patchRes.json()) as Question;

    setStage((prev) => {
      if (prev.name !== 'ready') return prev;
      let questions = prev.questionSet.questions.map((q, i) => (i === index ? savedQuestion : q));
      if (renameFrom) {
        questions = renameConceptEverywhere(questions, renameFrom, updated.concept);
      }
      return { ...prev, questionSet: { questions } };
    });
    return null;
  };

  const handleCreateRoom = async () => {
    const response = await fetch('/rooms', { method: 'POST' });
    if (!response.ok) return;
    const data = (await response.json()) as { pin: string };
    navigate(`/host/${data.pin}`);
  };

  const handleJoinRoom = () => {
    navigate('/join');
  };

  switch (stage.name) {
    case 'loading':
      return <p>Loading…</p>;
    case 'session_error':
      return <p>{stage.message}</p>;
    case 'upload':
      return <UploadStage onUploaded={handleUploaded} />;
    case 'checkpoint':
      return <CheckpointStage allocations={stage.allocations} onConfirm={handleConfirm} />;
    case 'generating':
      return <GeneratingStage progress={stage.progress} resumed={stage.mode === 'resumed'} />;
    case 'failed':
      return (
        <div>
          <p>Generation failed. Please try again.</p>
          <button onClick={handleRetry}>Retry</button>
        </div>
      );
    case 'ready':
      if (stage.view === 'review') {
        return (
          <ReviewSession
            questionSet={stage.questionSet}
            onExit={() => setStage((prev) => (prev.name === 'ready' ? { ...prev, view: 'browse' } : prev))}
          />
        );
      }
      return (
        <FlashcardView
          questionSet={stage.questionSet}
          onStartReview={() => setStage((prev) => (prev.name === 'ready' ? { ...prev, view: 'review' } : prev))}
          onUpdateQuestion={updateQuestion}
          onCreateRoom={handleCreateRoom}
          onJoinRoom={handleJoinRoom}
        />
      );
  }
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SessionFlow />} />
        <Route path="/host/:pin" element={<HostPage />} />
        <Route path="/join" element={<JoinPage />} />
        <Route path="/join/:pin" element={<JoinPage />} />
        <Route path="/play/:pin" element={<PlayerPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 3: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: all existing tests plus the new Task 2/3/4/5 tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: wire Upload/Checkpoint/Generating stages into the app's session flow"
```

---

### Task 12: Manual end-to-end verification

**Files:** none (verification only).

- [ ] **Step 1: Start the backend**

Run (background): `cd backend && uvicorn app.main:app --reload --port 8000`

- [ ] **Step 2: Start the frontend**

Run (background): `cd frontend && npm run dev`

- [ ] **Step 3: Walk the Upload stage in Chrome**

Navigate to the frontend dev URL. Confirm: dropzone renders, no "Preview state" buttons are present anywhere on the page, browsing/dropping a non-PDF shows the `not_a_pdf` message, and uploading a real text-based PDF shows the spinner then transitions to Checkpoint.

- [ ] **Step 4: Walk the Checkpoint stage**

Confirm: concept list matches the Analyzer's response, editing a weight updates the total live, Confirm stays disabled while weights ≠ 100 (±0.05), deleting a concept redistributes the remaining weights back to 100, and Confirm becomes enabled once balanced.

- [ ] **Step 5: Walk the Generating stage**

Click Confirm. Confirm: the dial and stage label update as SSE events arrive, and on completion the app lands on the existing flashcard browse view with the real generated `QuestionSet`. If the Groq free-tier daily cap (noted in `PROGRESS.md`'s Todo, still possibly active as of this session) blocks the run, confirm instead that the `failed` stage renders with a working Retry button, and note the block in the final report rather than treating it as a bug in this UI.

- [ ] **Step 6: Reload mid-generation (if a run is long enough to catch)**

Reload the page while `status` is `generating`. Confirm the app shows the resumed-mode message (not a duplicate `/generate` call — check the Network tab for exactly one POST to `/generate` across both loads) and eventually lands on `ready` or `failed` once the background pipeline task settles.

- [ ] **Step 7: Confirm existing flows are unaffected**

Run: `cd frontend && npx vitest run` and `cd backend && python -m pytest` (or the project's existing pytest invocation)
Expected: unchanged pass counts from before this change (no backend files were touched, so this is a regression check only).

No commit for this task — verification only, findings folded back into earlier tasks if anything breaks.
