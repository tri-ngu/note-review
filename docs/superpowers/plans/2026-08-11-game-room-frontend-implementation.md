# Game Room Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Game Room (v2) frontend — Host flow, Player flow, and WebSocket wiring — on top of the already-built, already-tested FastAPI backend in `backend/`.

**Architecture:** Four `react-router` routes (`/`, `/host/:pin`, `/join/:pin`, `/play/:pin`); `/host/:pin` and `/play/:pin` are each a single route whose screen swaps panels based on `RoomState.status`, driven live by one WebSocket connection per page via a shared `useRoomSocket` hook (pure reducer over the server's `{type, ...payload}` messages). No client-side game logic is duplicated — the server is authoritative for timing, scoring, and phase transitions; the frontend only renders what it's told and forwards user actions (`advance`, `end_game`, `submit_answer`).

**Tech Stack:** React 19 + TypeScript + Vite (existing), CSS Modules (existing pattern), `react-router-dom` (new), `qrcode.react` (new), Vitest (existing, pure-function tests only).

## Global Constraints

- Spec of record: `docs/superpowers/specs/2026-08-11-game-room-frontend-design.md`, merged into `DESIGN.md`'s Room sections (see commit `5b4799a` on `main`/`game-room-build` in the docs repo).
- Only touch `frontend/` in this plan. Do not modify `backend/` — it's already built and tested (76 pytest cases), and the design explicitly accepted the reload/resume and WS-error gaps as known limitations rather than touching the backend.
- Do not modify `CONTEXT.md`/`DESIGN.md`/`requirements.md`/`PROGRESS.md` — already updated in a prior session.
- `tsconfig.app.json` has `verbatimModuleSyntax: true` — every type-only import must use `import type { ... }`.
- `tsconfig.app.json` has `noUnusedLocals`/`noUnusedParameters: true` and `noFallthroughCasesInSwitch: true` — every declared variable/param must be used, every switch case must return/break.
- Visual style matches the existing Botanical Field Guide palette (from `FlashcardView.module.css`): background `#e9e6df`, text `#1a1a1a`, accent green `#4b6043` / `#4b5440`, cream `#f4f2e6`; `Rockwell, Georgia, serif` for buttons/headings, `Constantia, Georgia, serif` for meta text, `'Segoe UI', system-ui, -apple-system, sans-serif` as the base font.
- Vite dev proxy forwards `/rooms`, `/health`, `/ws` to `http://localhost:8000` (FastAPI's default `uvicorn` port) — frontend code calls relative paths only (`fetch('/rooms')`, `new WebSocket(...window.location.host.../ws/room/...)`), never an absolute backend URL.
- No WS auto-reconnect, for either role, at any phase (approved known limitation).
- `error` WS message type is modeled in the type system and reducer, but the backend never currently emits it — don't build any UI flow that depends on it firing.
- Only pure functions (`roomSocketReducer`, `buildJoinUrl`) get Vitest unit tests, matching the existing repo convention (`src/lib/*.test.ts` — no component-level tests exist for `Flashcard.tsx`/`FlashcardView.tsx` either). Components are verified via a manual live smoke test as the final task.

---

### Task 1: Dependencies and dev proxy

**Files:**
- Modify: `frontend/package.json` (via `npm install`)
- Modify: `frontend/vite.config.ts`

**Interfaces:**
- Produces: dev-time proxy so all later `fetch('/rooms/...')` / `new WebSocket('.../ws/room/...')` calls resolve to the FastAPI backend without CORS.

- [ ] **Step 1: Install the two new dependencies**

Run from `frontend/`:
```bash
npm install react-router-dom qrcode.react
```

- [ ] **Step 2: Add the dev proxy to `vite.config.ts`**

Replace the file's contents with:
```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/rooms': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
```

- [ ] **Step 3: Verify the existing app still builds**

Run: `npx tsc --noEmit`
Expected: no errors (nothing functional changed yet).

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts
git commit -m "chore: add react-router-dom, qrcode.react, and backend dev proxy"
```

---

### Task 2: Room WebSocket protocol types

**Files:**
- Create: `frontend/src/types/room.ts`

**Interfaces:**
- Produces: `RoomPublicStatus`, `RoomPrecheck`, `RosterPlayer`, `LeaderboardStanding`, `AnswerResult`, `QuestionStartMessage`, `AnswerRevealMessage`, `LeaderboardMessage`, `GameOverMessage`, `ServerMessage`, `ClientMessage`, `ConnectionState`, `RoomPhase`, `RoomSocketAction`, `RoomSocketState` — used by every task from here on.

- [ ] **Step 1: Write the types file**

```ts
export type RoomPublicStatus = 'lobby' | 'in_progress' | 'finished';

export interface RoomPrecheck {
  status: RoomPublicStatus;
  player_count: number;
}

export interface RosterPlayer {
  player_id: string;
  nickname: string;
}

export interface LeaderboardStanding {
  player_id: string;
  nickname: string;
  score: number;
  rank: number;
}

export interface AnswerResult {
  correct: boolean;
  points: number;
}

export interface QuestionStartMessage {
  type: 'question_start';
  round: number;
  total_rounds: number;
  question_text: string;
  options: [string, string, string, string];
  is_select_all: boolean;
  page_number: number;
  concept: string;
  server_time: number;
}

export interface AnswerRevealMessage {
  type: 'answer_reveal';
  round: number;
  correct_answers: number[];
  explanation: string;
  results: Record<string, AnswerResult>;
}

export interface LeaderboardMessage {
  type: 'leaderboard';
  round: number;
  total_rounds: number;
  standings: LeaderboardStanding[];
  is_final: boolean;
}

export interface GameOverMessage {
  type: 'game_over';
  reason: 'natural_end' | 'host_ended' | 'host_disconnected';
  final_standings: LeaderboardStanding[];
}

export type ServerMessage =
  | { type: 'player_joined'; player_id: string; nickname: string }
  | { type: 'player_left'; player_id: string }
  | QuestionStartMessage
  | { type: 'answered_count'; answered: number; total_connected: number }
  | AnswerRevealMessage
  | LeaderboardMessage
  | GameOverMessage
  | { type: 'error'; code: string; message: string };

export type ClientMessage =
  | { type: 'advance' }
  | { type: 'end_game' }
  | { type: 'submit_answer'; round: number; selected: number[] };

export type ConnectionState = 'connecting' | 'open' | 'closed';

export type RoomSocketAction =
  | ServerMessage
  | { type: 'connection_open' }
  | { type: 'connection_closed' };

export type RoomPhase = 'lobby' | 'question_active' | 'reveal' | 'leaderboard' | 'finished';

export interface RoomSocketState {
  connection: ConnectionState;
  phase: RoomPhase;
  roster: RosterPlayer[];
  currentQuestion: QuestionStartMessage | null;
  answeredCount: { answered: number; total_connected: number } | null;
  lastReveal: AnswerRevealMessage | null;
  standings: LeaderboardStanding[];
  isFinalRound: boolean;
  gameOver: GameOverMessage | null;
  lastError: { code: string; message: string } | null;
}
```

- [ ] **Step 2: Verify it compiles**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/room.ts
git commit -m "feat: add Room WebSocket protocol types"
```

---

### Task 3: `roomSocketReducer` (pure, TDD)

**Files:**
- Create: `frontend/src/room/lib/roomSocketReducer.ts`
- Test: `frontend/src/room/lib/roomSocketReducer.test.ts`

**Interfaces:**
- Consumes: `RoomSocketAction`, `RoomSocketState` from `../../types/room` (Task 2).
- Produces: `initialRoomSocketState: RoomSocketState`, `roomSocketReducer(state: RoomSocketState, action: RoomSocketAction): RoomSocketState` — used by `useRoomSocket` (Task 5) and its own test.

- [ ] **Step 1: Write the failing tests**

```ts
import { describe, expect, it } from 'vitest';
import { initialRoomSocketState, roomSocketReducer } from './roomSocketReducer';

describe('roomSocketReducer', () => {
  it('adds a new player to the roster on player_joined', () => {
    const state = roomSocketReducer(initialRoomSocketState, {
      type: 'player_joined',
      player_id: 'p1',
      nickname: 'Alice',
    });
    expect(state.roster).toEqual([{ player_id: 'p1', nickname: 'Alice' }]);
  });

  it('updates nickname if player_joined fires again for the same player_id', () => {
    const joined = roomSocketReducer(initialRoomSocketState, {
      type: 'player_joined',
      player_id: 'p1',
      nickname: 'Alice',
    });
    const renamed = roomSocketReducer(joined, {
      type: 'player_joined',
      player_id: 'p1',
      nickname: 'Alice (1)',
    });
    expect(renamed.roster).toEqual([{ player_id: 'p1', nickname: 'Alice (1)' }]);
  });

  it('removes a player from the roster on player_left', () => {
    const joined = roomSocketReducer(initialRoomSocketState, {
      type: 'player_joined',
      player_id: 'p1',
      nickname: 'Alice',
    });
    const left = roomSocketReducer(joined, { type: 'player_left', player_id: 'p1' });
    expect(left.roster).toEqual([]);
  });

  it('enters question_active phase and clears prior round data on question_start', () => {
    const withPriorRound = {
      ...initialRoomSocketState,
      lastReveal: {
        type: 'answer_reveal' as const,
        round: 1,
        correct_answers: [1],
        explanation: 'because',
        results: {},
      },
      answeredCount: { answered: 2, total_connected: 3 },
    };
    const state = roomSocketReducer(withPriorRound, {
      type: 'question_start',
      round: 2,
      total_rounds: 8,
      question_text: 'What is water made of?',
      options: ['H2O', 'CO2', 'O2', 'N2'],
      is_select_all: false,
      page_number: 1,
      concept: 'Water cycle',
      server_time: 100,
    });
    expect(state.phase).toBe('question_active');
    expect(state.currentQuestion?.question_text).toBe('What is water made of?');
    expect(state.answeredCount).toBeNull();
    expect(state.lastReveal).toBeNull();
  });

  it('records answered_count', () => {
    const state = roomSocketReducer(initialRoomSocketState, {
      type: 'answered_count',
      answered: 1,
      total_connected: 4,
    });
    expect(state.answeredCount).toEqual({ answered: 1, total_connected: 4 });
  });

  it('enters reveal phase and stores the reveal payload on answer_reveal', () => {
    const state = roomSocketReducer(initialRoomSocketState, {
      type: 'answer_reveal',
      round: 1,
      correct_answers: [1, 3],
      explanation: 'because',
      results: { p1: { correct: true, points: 90 } },
    });
    expect(state.phase).toBe('reveal');
    expect(state.lastReveal?.correct_answers).toEqual([1, 3]);
  });

  it('enters leaderboard phase and stores standings on leaderboard', () => {
    const state = roomSocketReducer(initialRoomSocketState, {
      type: 'leaderboard',
      round: 1,
      total_rounds: 8,
      standings: [{ player_id: 'p1', nickname: 'Alice', score: 90, rank: 1 }],
      is_final: false,
    });
    expect(state.phase).toBe('leaderboard');
    expect(state.standings).toHaveLength(1);
    expect(state.isFinalRound).toBe(false);
  });

  it('enters finished phase and stores final standings on game_over', () => {
    const state = roomSocketReducer(initialRoomSocketState, {
      type: 'game_over',
      reason: 'natural_end',
      final_standings: [{ player_id: 'p1', nickname: 'Alice', score: 90, rank: 1 }],
    });
    expect(state.phase).toBe('finished');
    expect(state.gameOver?.reason).toBe('natural_end');
  });

  it('stores the last error on error without changing phase', () => {
    const state = roomSocketReducer(initialRoomSocketState, {
      type: 'error',
      code: 'late_answer',
      message: 'Answer rejected: too late.',
    });
    expect(state.phase).toBe('lobby');
    expect(state.lastError).toEqual({ code: 'late_answer', message: 'Answer rejected: too late.' });
  });

  it('tracks connection open/closed transitions', () => {
    const open = roomSocketReducer(initialRoomSocketState, { type: 'connection_open' });
    expect(open.connection).toBe('open');
    const closed = roomSocketReducer(open, { type: 'connection_closed' });
    expect(closed.connection).toBe('closed');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run src/room/lib/roomSocketReducer.test.ts`
Expected: FAIL — `roomSocketReducer.ts` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```ts
import type { RoomSocketAction, RoomSocketState } from '../../types/room';

export const initialRoomSocketState: RoomSocketState = {
  connection: 'connecting',
  phase: 'lobby',
  roster: [],
  currentQuestion: null,
  answeredCount: null,
  lastReveal: null,
  standings: [],
  isFinalRound: false,
  gameOver: null,
  lastError: null,
};

export function roomSocketReducer(state: RoomSocketState, action: RoomSocketAction): RoomSocketState {
  switch (action.type) {
    case 'connection_open':
      return { ...state, connection: 'open' };
    case 'connection_closed':
      return { ...state, connection: 'closed' };
    case 'player_joined': {
      const alreadyPresent = state.roster.some((p) => p.player_id === action.player_id);
      const roster = alreadyPresent
        ? state.roster.map((p) =>
            p.player_id === action.player_id ? { player_id: action.player_id, nickname: action.nickname } : p,
          )
        : [...state.roster, { player_id: action.player_id, nickname: action.nickname }];
      return { ...state, roster };
    }
    case 'player_left':
      return { ...state, roster: state.roster.filter((p) => p.player_id !== action.player_id) };
    case 'question_start':
      return {
        ...state,
        phase: 'question_active',
        currentQuestion: action,
        answeredCount: null,
        lastReveal: null,
      };
    case 'answered_count':
      return { ...state, answeredCount: { answered: action.answered, total_connected: action.total_connected } };
    case 'answer_reveal':
      return { ...state, phase: 'reveal', lastReveal: action };
    case 'leaderboard':
      return { ...state, phase: 'leaderboard', standings: action.standings, isFinalRound: action.is_final };
    case 'game_over':
      return { ...state, phase: 'finished', gameOver: action };
    case 'error':
      return { ...state, lastError: { code: action.code, message: action.message } };
    default:
      return state;
  }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run src/room/lib/roomSocketReducer.test.ts`
Expected: PASS (10/10)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/room/lib/roomSocketReducer.ts frontend/src/room/lib/roomSocketReducer.test.ts
git commit -m "feat: add pure roomSocketReducer for Room WS protocol"
```

---

### Task 4: `buildJoinUrl` (pure, TDD)

**Files:**
- Create: `frontend/src/room/lib/joinUrl.ts`
- Test: `frontend/src/room/lib/joinUrl.test.ts`

**Interfaces:**
- Produces: `buildJoinUrl(origin: string, pin: string): string` — used by `LobbyPanel` (Task 7).

- [ ] **Step 1: Write the failing tests**

```ts
import { describe, expect, it } from 'vitest';
import { buildJoinUrl } from './joinUrl';

describe('buildJoinUrl', () => {
  it('builds a join URL from an origin and PIN', () => {
    expect(buildJoinUrl('https://example.com', '0427')).toBe('https://example.com/join/0427');
  });

  it('works with a localhost dev origin', () => {
    expect(buildJoinUrl('http://localhost:5173', '9981')).toBe('http://localhost:5173/join/9981');
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run src/room/lib/joinUrl.test.ts`
Expected: FAIL — `joinUrl.ts` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```ts
export function buildJoinUrl(origin: string, pin: string): string {
  return `${origin}/join/${pin}`;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run src/room/lib/joinUrl.test.ts`
Expected: PASS (2/2)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/room/lib/joinUrl.ts frontend/src/room/lib/joinUrl.test.ts
git commit -m "feat: add buildJoinUrl helper"
```

---

### Task 5: `useRoomSocket` hook

**Files:**
- Create: `frontend/src/room/useRoomSocket.ts`

**Interfaces:**
- Consumes: `roomSocketReducer`, `initialRoomSocketState` from `./lib/roomSocketReducer` (Task 3); `ClientMessage`, `ServerMessage` from `../types/room` (Task 2).
- Produces: `useRoomSocket({ pin, role, playerId? }): { state: RoomSocketState; send: (message: ClientMessage) => void }` — used by `HostPage` (Task 14) and `PlayerPage` (Task 16).

- [ ] **Step 1: Write the hook**

```ts
import { useEffect, useReducer, useRef } from 'react';
import type { ClientMessage, ServerMessage } from '../types/room';
import { initialRoomSocketState, roomSocketReducer } from './lib/roomSocketReducer';

interface UseRoomSocketArgs {
  pin: string;
  role: 'host' | 'player';
  playerId?: string;
}

export function useRoomSocket({ pin, role, playerId }: UseRoomSocketArgs) {
  const [state, dispatch] = useReducer(roomSocketReducer, initialRoomSocketState);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!pin) return;
    const query = role === 'player' && playerId ? `?player_id=${encodeURIComponent(playerId)}` : '';
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/room/${pin}${query}`);
    socketRef.current = socket;

    socket.onopen = () => dispatch({ type: 'connection_open' });
    socket.onclose = () => dispatch({ type: 'connection_closed' });
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data as string) as ServerMessage;
      dispatch(message);
    };

    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [pin, role, playerId]);

  const send = (message: ClientMessage) => {
    socketRef.current?.send(JSON.stringify(message));
  };

  return { state, send };
}
```

- [ ] **Step 2: Verify it compiles**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/room/useRoomSocket.ts
git commit -m "feat: add useRoomSocket hook (no auto-reconnect, per design spec)"
```

---

### Task 6: `RoomErrorPanel` (shared)

**Files:**
- Create: `frontend/src/room/panels/RoomErrorPanel.tsx`
- Create: `frontend/src/room/panels/RoomErrorPanel.module.css`

**Interfaces:**
- Produces: `RoomErrorPanel({ title, message }: { title: string; message: string })` — used by `HostPage`, `JoinPage`, `PlayerPage` (Tasks 14-16).

- [ ] **Step 1: Write the component**

```tsx
import { Link } from 'react-router-dom';
import styles from './RoomErrorPanel.module.css';

interface RoomErrorPanelProps {
  title: string;
  message: string;
}

export function RoomErrorPanel({ title, message }: RoomErrorPanelProps) {
  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.message}>{message}</p>
        <Link className={styles.homeLink} to="/">
          Back to Home
        </Link>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Write the CSS module**

```css
.theme {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: #e9e6df;
  color: #1a1a1a;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  box-sizing: border-box;
}

.stage {
  max-width: 480px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

.title {
  font-family: Rockwell, Georgia, serif;
  color: #4b5440;
  margin: 0;
}

.message {
  font-family: Constantia, Georgia, serif;
  color: #4b5440;
  margin: 0;
}

.homeLink {
  font-size: 12.5px;
  border: 1px solid #4b6043;
  background: #4b6043;
  color: #f4f2e6;
  padding: 8px 20px;
  border-radius: 2px;
  font-family: Rockwell, Georgia, serif;
  text-decoration: none;
}
```

- [ ] **Step 3: Verify it compiles**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/room/panels/RoomErrorPanel.tsx frontend/src/room/panels/RoomErrorPanel.module.css
git commit -m "feat: add shared RoomErrorPanel"
```

---

### Task 7: `LobbyPanel` (Host)

**Files:**
- Create: `frontend/src/room/panels/LobbyPanel.tsx`
- Create: `frontend/src/room/panels/LobbyPanel.module.css`

**Interfaces:**
- Consumes: `buildJoinUrl` from `../lib/joinUrl` (Task 4); `RosterPlayer` from `../../types/room` (Task 2); `QRCodeSVG` from `qrcode.react` (Task 1).
- Produces: `LobbyPanel({ pin, roster, onStart }: { pin: string; roster: RosterPlayer[]; onStart: () => void })` — used by `HostPage` (Task 14).

- [ ] **Step 1: Write the component**

```tsx
import { QRCodeSVG } from 'qrcode.react';
import type { RosterPlayer } from '../../types/room';
import { buildJoinUrl } from '../lib/joinUrl';
import styles from './LobbyPanel.module.css';

interface LobbyPanelProps {
  pin: string;
  roster: RosterPlayer[];
  onStart: () => void;
}

export function LobbyPanel({ pin, roster, onStart }: LobbyPanelProps) {
  const joinUrl = buildJoinUrl(window.location.origin, pin);

  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <p className={styles.pinLabel}>Room PIN</p>
        <h1 className={styles.pin}>{pin}</h1>
        <QRCodeSVG value={joinUrl} size={180} />
        <p className={styles.joinUrl}>{joinUrl}</p>
        <h2 className={styles.rosterHeading}>Players ({roster.length}/10)</h2>
        <ul className={styles.roster}>
          {roster.map((player) => (
            <li key={player.player_id} className={styles.rosterItem}>
              {player.nickname}
            </li>
          ))}
        </ul>
        <button className={styles.startBtn} onClick={onStart}>
          Start Game
        </button>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Write the CSS module**

```css
.theme {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: #e9e6df;
  color: #1a1a1a;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  box-sizing: border-box;
}

.stage {
  max-width: 420px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}

.pinLabel {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-family: Constantia, Georgia, serif;
  color: #4b5440;
  margin: 0;
}

.pin {
  font-family: Rockwell, Georgia, serif;
  font-size: 48px;
  letter-spacing: 0.1em;
  color: #4b5440;
  margin: 0;
}

.joinUrl {
  font-family: Constantia, Georgia, serif;
  font-size: 13px;
  color: #4b5440;
  word-break: break-all;
  margin: 0;
}

.rosterHeading {
  font-family: Rockwell, Georgia, serif;
  font-size: 14px;
  color: #4b5440;
  margin: 8px 0 0;
}

.roster {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.rosterItem {
  font-family: Constantia, Georgia, serif;
  font-size: 13px;
  border: 1px solid #4b6043;
  border-radius: 2px;
  padding: 4px 10px;
  color: #4b5440;
}

.startBtn {
  font-size: 12.5px;
  border: 1px solid #4b6043;
  background: #4b6043;
  color: #f4f2e6;
  padding: 8px 20px;
  border-radius: 2px;
  font-family: Rockwell, Georgia, serif;
  cursor: pointer;
  margin-top: 8px;
}
```

- [ ] **Step 3: Verify it compiles**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/room/panels/LobbyPanel.tsx frontend/src/room/panels/LobbyPanel.module.css
git commit -m "feat: add Host LobbyPanel (PIN, QR, roster, Start Game)"
```

---

### Task 8: `QuestionActivePanel` (Host)

**Files:**
- Create: `frontend/src/room/panels/QuestionActivePanel.tsx`
- Create: `frontend/src/room/panels/QuestionActivePanel.module.css`

**Interfaces:**
- Produces: `QuestionActivePanel({ round, totalRounds, answeredCount }: { round: number; totalRounds: number; answeredCount: { answered: number; total_connected: number } | null })` — used by `HostPage` (Task 14) for both `question_active` and `reveal` phases (Host UI collapses reveal into this same panel, per the merged DESIGN.md note).

- [ ] **Step 1: Write the component**

```tsx
import styles from './QuestionActivePanel.module.css';

interface QuestionActivePanelProps {
  round: number;
  totalRounds: number;
  answeredCount: { answered: number; total_connected: number } | null;
}

export function QuestionActivePanel({ round, totalRounds, answeredCount }: QuestionActivePanelProps) {
  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <p className={styles.round}>
          Round {round} of {totalRounds}
        </p>
        <h1 className={styles.status}>Question in progress…</h1>
        <p className={styles.answeredCount}>
          {answeredCount ? `${answeredCount.answered} of ${answeredCount.total_connected} answered` : 'Waiting for answers…'}
        </p>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Write the CSS module**

```css
.theme {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: #e9e6df;
  color: #1a1a1a;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  box-sizing: border-box;
}

.stage {
  max-width: 420px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.round {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-family: Constantia, Georgia, serif;
  color: #4b5440;
  margin: 0;
}

.status {
  font-family: Rockwell, Georgia, serif;
  color: #4b5440;
  margin: 0;
}

.answeredCount {
  font-family: Constantia, Georgia, serif;
  font-size: 14px;
  color: #4b5440;
  margin: 0;
}
```

- [ ] **Step 3: Verify it compiles**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/room/panels/QuestionActivePanel.tsx frontend/src/room/panels/QuestionActivePanel.module.css
git commit -m "feat: add Host QuestionActivePanel"
```

---

### Task 9: `LeaderboardPanel` (shared Host/Player)

**Files:**
- Create: `frontend/src/room/panels/LeaderboardPanel.tsx`
- Create: `frontend/src/room/panels/LeaderboardPanel.module.css`

**Interfaces:**
- Consumes: `LeaderboardStanding` from `../../types/room` (Task 2).
- Produces: `LeaderboardPanel({ standings, round, totalRounds, isFinal, currentPlayerId?, hostControls? }: { standings: LeaderboardStanding[]; round: number; totalRounds: number; isFinal: boolean; currentPlayerId?: string; hostControls?: { onNext: () => void; onEndGame: () => void } })` — used by `HostPage` (Task 14, with `hostControls`) and `PlayerPage` (Task 16, with `currentPlayerId`, no `hostControls`).

- [ ] **Step 1: Write the component**

```tsx
import type { LeaderboardStanding } from '../../types/room';
import styles from './LeaderboardPanel.module.css';

interface LeaderboardPanelProps {
  standings: LeaderboardStanding[];
  round: number;
  totalRounds: number;
  isFinal: boolean;
  currentPlayerId?: string;
  hostControls?: { onNext: () => void; onEndGame: () => void };
}

export function LeaderboardPanel({
  standings,
  round,
  totalRounds,
  isFinal,
  currentPlayerId,
  hostControls,
}: LeaderboardPanelProps) {
  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <p className={styles.round}>
          Leaderboard — Round {round} of {totalRounds}
        </p>
        <ol className={styles.standings}>
          {standings.map((s) => (
            <li key={s.player_id} className={s.player_id === currentPlayerId ? styles.ownRow : styles.row}>
              <span className={styles.rank}>#{s.rank}</span>
              <span className={styles.nickname}>{s.nickname}</span>
              <span className={styles.score}>{s.score}</span>
            </li>
          ))}
        </ol>
        {hostControls && (
          <div className={styles.hostActions}>
            <button className={styles.primaryBtn} onClick={hostControls.onNext}>
              {isFinal ? 'Finish' : 'Next Question'}
            </button>
            <button className={styles.secondaryBtn} onClick={hostControls.onEndGame}>
              End Game
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Write the CSS module**

```css
.theme {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: #e9e6df;
  color: #1a1a1a;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  box-sizing: border-box;
}

.stage {
  max-width: 420px;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.round {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-family: Constantia, Georgia, serif;
  color: #4b5440;
  margin: 0;
  text-align: center;
}

.standings {
  list-style: none;
  padding: 0;
  margin: 0;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.row,
.ownRow {
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: Constantia, Georgia, serif;
  font-size: 14px;
  color: #4b5440;
  border: 1px solid #4b6043;
  border-radius: 2px;
  padding: 6px 12px;
}

.ownRow {
  background: #4b6043;
  color: #f4f2e6;
}

.rank {
  font-family: Rockwell, Georgia, serif;
  width: 32px;
}

.nickname {
  flex: 1;
}

.score {
  font-variant-numeric: tabular-nums;
}

.hostActions {
  display: flex;
  gap: 10px;
  margin-top: 8px;
}

.primaryBtn {
  font-size: 12.5px;
  border: 1px solid #4b6043;
  background: #4b6043;
  color: #f4f2e6;
  padding: 8px 20px;
  border-radius: 2px;
  font-family: Rockwell, Georgia, serif;
  cursor: pointer;
}

.secondaryBtn {
  font-size: 12.5px;
  border: 1px solid #4b6043;
  background: none;
  color: #4b6043;
  padding: 8px 20px;
  border-radius: 2px;
  font-family: Rockwell, Georgia, serif;
  cursor: pointer;
}
```

- [ ] **Step 3: Verify it compiles**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/room/panels/LeaderboardPanel.tsx frontend/src/room/panels/LeaderboardPanel.module.css
git commit -m "feat: add shared LeaderboardPanel (Host controls optional)"
```

---

### Task 10: `FinishedPanel` (shared Host/Player)

**Files:**
- Create: `frontend/src/room/panels/FinishedPanel.tsx`
- Create: `frontend/src/room/panels/FinishedPanel.module.css`

**Interfaces:**
- Consumes: `LeaderboardStanding` from `../../types/room` (Task 2).
- Produces: `FinishedPanel({ standings, reason, currentPlayerId? }: { standings: LeaderboardStanding[]; reason: 'natural_end' | 'host_ended' | 'host_disconnected'; currentPlayerId?: string })` — used by `HostPage` (Task 14) and `PlayerPage` (Task 16).

- [ ] **Step 1: Write the component**

```tsx
import { Link } from 'react-router-dom';
import type { LeaderboardStanding } from '../../types/room';
import styles from './FinishedPanel.module.css';

interface FinishedPanelProps {
  standings: LeaderboardStanding[];
  reason: 'natural_end' | 'host_ended' | 'host_disconnected';
  currentPlayerId?: string;
}

const REASON_LABEL: Record<FinishedPanelProps['reason'], string> = {
  natural_end: 'Game complete!',
  host_ended: 'Host ended the game.',
  host_disconnected: 'Host disconnected — game ended.',
};

export function FinishedPanel({ standings, reason, currentPlayerId }: FinishedPanelProps) {
  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <h1 className={styles.title}>{REASON_LABEL[reason]}</h1>
        <ol className={styles.standings}>
          {standings.map((s) => (
            <li key={s.player_id} className={s.player_id === currentPlayerId ? styles.ownRow : styles.row}>
              <span className={styles.rank}>#{s.rank}</span>
              <span className={styles.nickname}>{s.nickname}</span>
              <span className={styles.score}>{s.score}</span>
            </li>
          ))}
        </ol>
        <Link className={styles.homeLink} to="/">
          Back to Home
        </Link>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Write the CSS module**

```css
.theme {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: #e9e6df;
  color: #1a1a1a;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  box-sizing: border-box;
}

.stage {
  max-width: 420px;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.title {
  font-family: Rockwell, Georgia, serif;
  color: #4b5440;
  margin: 0;
  text-align: center;
}

.standings {
  list-style: none;
  padding: 0;
  margin: 0;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.row,
.ownRow {
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: Constantia, Georgia, serif;
  font-size: 14px;
  color: #4b5440;
  border: 1px solid #4b6043;
  border-radius: 2px;
  padding: 6px 12px;
}

.ownRow {
  background: #4b6043;
  color: #f4f2e6;
}

.rank {
  font-family: Rockwell, Georgia, serif;
  width: 32px;
}

.nickname {
  flex: 1;
}

.score {
  font-variant-numeric: tabular-nums;
}

.homeLink {
  font-size: 12.5px;
  border: 1px solid #4b6043;
  background: #4b6043;
  color: #f4f2e6;
  padding: 8px 20px;
  border-radius: 2px;
  font-family: Rockwell, Georgia, serif;
  text-decoration: none;
  margin-top: 8px;
}
```

- [ ] **Step 3: Verify it compiles**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/room/panels/FinishedPanel.tsx frontend/src/room/panels/FinishedPanel.module.css
git commit -m "feat: add shared FinishedPanel"
```

---

### Task 11: `WaitingPanel` (Player)

**Files:**
- Create: `frontend/src/room/panels/WaitingPanel.tsx`
- Create: `frontend/src/room/panels/WaitingPanel.module.css`

**Interfaces:**
- Produces: `WaitingPanel({ pin }: { pin: string })` — used by `PlayerPage` (Task 16) for the `lobby` phase.

- [ ] **Step 1: Write the component**

```tsx
import styles from './WaitingPanel.module.css';

interface WaitingPanelProps {
  pin: string;
}

export function WaitingPanel({ pin }: WaitingPanelProps) {
  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <p className={styles.pinLabel}>Room {pin}</p>
        <h1 className={styles.message}>Waiting for the host to start the game…</h1>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Write the CSS module**

```css
.theme {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: #e9e6df;
  color: #1a1a1a;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  box-sizing: border-box;
}

.stage {
  max-width: 420px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.pinLabel {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-family: Constantia, Georgia, serif;
  color: #4b5440;
  margin: 0;
}

.message {
  font-family: Rockwell, Georgia, serif;
  color: #4b5440;
  margin: 0;
}
```

- [ ] **Step 3: Verify it compiles**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/room/panels/WaitingPanel.tsx frontend/src/room/panels/WaitingPanel.module.css
git commit -m "feat: add Player WaitingPanel"
```

---

### Task 12: `QuestionPanel` (Player)

**Files:**
- Create: `frontend/src/room/panels/QuestionPanel.tsx`
- Create: `frontend/src/room/panels/QuestionPanel.module.css`

**Interfaces:**
- Consumes: `QuestionStartMessage` from `../../types/room` (Task 2).
- Produces: `QuestionPanel({ question, onSubmit }: { question: QuestionStartMessage; onSubmit: (selected: number[]) => void })` — used by `PlayerPage` (Task 16), remounted per round via `key={question.round}` so its internal `submitted` state resets automatically (same pattern as the existing `Flashcard` component's `key={currentIndex}`).

- [ ] **Step 1: Write the component**

```tsx
import { useState } from 'react';
import type { QuestionStartMessage } from '../../types/room';
import styles from './QuestionPanel.module.css';

interface QuestionPanelProps {
  question: QuestionStartMessage;
  onSubmit: (selected: number[]) => void;
}

export function QuestionPanel({ question, onSubmit }: QuestionPanelProps) {
  const [selected, setSelected] = useState<number[]>([]);
  const [submitted, setSubmitted] = useState(false);

  const toggleOption = (position: number) => {
    if (submitted) return;
    if (!question.is_select_all) {
      setSelected([position]);
      setSubmitted(true);
      onSubmit([position]);
      return;
    }
    setSelected((prev) => (prev.includes(position) ? prev.filter((p) => p !== position) : [...prev, position]));
  };

  const submitSelectAll = () => {
    if (submitted || selected.length === 0) return;
    setSubmitted(true);
    onSubmit(selected);
  };

  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <p className={styles.round}>
          Round {question.round} of {question.total_rounds}
        </p>
        <h1 className={styles.questionText}>{question.question_text}</h1>
        <div className={styles.options}>
          {question.options.map((option, i) => {
            const position = i + 1;
            const isSelected = selected.includes(position);
            return (
              <button
                key={position}
                className={isSelected ? styles.optionSelected : styles.option}
                onClick={() => toggleOption(position)}
                disabled={submitted}
              >
                {option}
              </button>
            );
          })}
        </div>
        {question.is_select_all && (
          <button
            className={styles.submitBtn}
            onClick={submitSelectAll}
            disabled={submitted || selected.length === 0}
          >
            Submit
          </button>
        )}
        {submitted && <p className={styles.waiting}>Waiting for other players…</p>}
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Write the CSS module**

```css
.theme {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: #e9e6df;
  color: #1a1a1a;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  box-sizing: border-box;
}

.stage {
  max-width: 480px;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

.round {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-family: Constantia, Georgia, serif;
  color: #4b5440;
  margin: 0;
}

.questionText {
  font-family: Rockwell, Georgia, serif;
  color: #4b5440;
  text-align: center;
  margin: 0;
}

.options {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.option,
.optionSelected {
  font-family: Constantia, Georgia, serif;
  font-size: 15px;
  text-align: left;
  border: 1px solid #4b6043;
  border-radius: 2px;
  background: #f4f2e6;
  color: #4b5440;
  padding: 10px 14px;
  cursor: pointer;
}

.optionSelected {
  background: #4b6043;
  color: #f4f2e6;
}

.option:disabled,
.optionSelected:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.submitBtn {
  font-size: 12.5px;
  border: 1px solid #4b6043;
  background: #4b6043;
  color: #f4f2e6;
  padding: 8px 20px;
  border-radius: 2px;
  font-family: Rockwell, Georgia, serif;
  cursor: pointer;
}
.submitBtn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.waiting {
  font-family: Constantia, Georgia, serif;
  font-size: 13px;
  color: #4b5440;
  opacity: 0.7;
  margin: 0;
}
```

- [ ] **Step 3: Verify it compiles**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/room/panels/QuestionPanel.tsx frontend/src/room/panels/QuestionPanel.module.css
git commit -m "feat: add Player QuestionPanel (tap-to-submit MC, multi-select+Submit)"
```

---

### Task 13: `RevealPanel` (Player)

**Files:**
- Create: `frontend/src/room/panels/RevealPanel.tsx`
- Create: `frontend/src/room/panels/RevealPanel.module.css`

**Interfaces:**
- Consumes: `AnswerResult` from `../../types/room` (Task 2).
- Produces: `RevealPanel({ questionText, options, correctAnswers, explanation, result }: { questionText: string; options: string[]; correctAnswers: number[]; explanation: string; result: AnswerResult | undefined })` — used by `PlayerPage` (Task 16).

- [ ] **Step 1: Write the component**

```tsx
import type { AnswerResult } from '../../types/room';
import styles from './RevealPanel.module.css';

interface RevealPanelProps {
  questionText: string;
  options: string[];
  correctAnswers: number[];
  explanation: string;
  result: AnswerResult | undefined;
}

export function RevealPanel({ questionText, options, correctAnswers, explanation, result }: RevealPanelProps) {
  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <p className={result?.correct ? styles.correct : styles.incorrect}>
          {result?.correct ? 'Correct!' : 'Incorrect'}
          {result ? ` +${result.points} pts` : ''}
        </p>
        <h1 className={styles.questionText}>{questionText}</h1>
        <ul className={styles.optionList}>
          {options.map((option, i) => {
            const position = i + 1;
            const isCorrect = correctAnswers.includes(position);
            return (
              <li key={position} className={isCorrect ? styles.correctOption : styles.option}>
                {option}
              </li>
            );
          })}
        </ul>
        <p className={styles.explanation}>{explanation}</p>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Write the CSS module**

```css
.theme {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: #e9e6df;
  color: #1a1a1a;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  box-sizing: border-box;
}

.stage {
  max-width: 480px;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.correct,
.incorrect {
  font-family: Rockwell, Georgia, serif;
  font-size: 14px;
  margin: 0;
}

.correct {
  color: #4b6043;
}

.incorrect {
  color: #a13d2c;
}

.questionText {
  font-family: Rockwell, Georgia, serif;
  color: #4b5440;
  text-align: center;
  margin: 0;
}

.optionList {
  list-style: none;
  padding: 0;
  margin: 0;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.option,
.correctOption {
  font-family: Constantia, Georgia, serif;
  font-size: 14px;
  border: 1px solid #4b6043;
  border-radius: 2px;
  padding: 8px 12px;
  color: #4b5440;
}

.correctOption {
  background: #4b6043;
  color: #f4f2e6;
}

.explanation {
  font-family: Constantia, Georgia, serif;
  font-size: 13px;
  color: #4b5440;
  text-align: center;
  margin: 0;
}
```

- [ ] **Step 3: Verify it compiles**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/room/panels/RevealPanel.tsx frontend/src/room/panels/RevealPanel.module.css
git commit -m "feat: add Player RevealPanel"
```

---

### Task 14: `HostPage`

**Files:**
- Create: `frontend/src/room/HostPage.tsx`

**Interfaces:**
- Consumes: `useRoomSocket` (Task 5); `LobbyPanel` (Task 7), `QuestionActivePanel` (Task 8), `LeaderboardPanel` (Task 9), `FinishedPanel` (Task 10), `RoomErrorPanel` (Task 6); `useParams` from `react-router-dom`.
- Produces: `HostPage()` — mounted at `/host/:pin` in Task 17.

- [ ] **Step 1: Write the component**

```tsx
import { useParams } from 'react-router-dom';
import { useRoomSocket } from './useRoomSocket';
import { LobbyPanel } from './panels/LobbyPanel';
import { QuestionActivePanel } from './panels/QuestionActivePanel';
import { LeaderboardPanel } from './panels/LeaderboardPanel';
import { FinishedPanel } from './panels/FinishedPanel';
import { RoomErrorPanel } from './panels/RoomErrorPanel';

export function HostPage() {
  const { pin } = useParams<{ pin: string }>();
  const { state, send } = useRoomSocket({ pin: pin ?? '', role: 'host' });

  if (!pin) {
    return <RoomErrorPanel title="Room not found" message="No room PIN was given." />;
  }

  if (state.connection === 'closed') {
    return <RoomErrorPanel title="Disconnected" message="Lost connection to the room." />;
  }

  switch (state.phase) {
    case 'lobby':
      return <LobbyPanel pin={pin} roster={state.roster} onStart={() => send({ type: 'advance' })} />;
    case 'question_active':
    case 'reveal':
      return (
        <QuestionActivePanel
          round={state.currentQuestion?.round ?? 0}
          totalRounds={state.currentQuestion?.total_rounds ?? 0}
          answeredCount={state.answeredCount}
        />
      );
    case 'leaderboard':
      return (
        <LeaderboardPanel
          standings={state.standings}
          round={state.currentQuestion?.round ?? 0}
          totalRounds={state.currentQuestion?.total_rounds ?? 0}
          isFinal={state.isFinalRound}
          hostControls={{
            onNext: () => send({ type: 'advance' }),
            onEndGame: () => send({ type: 'end_game' }),
          }}
        />
      );
    case 'finished':
      return (
        <FinishedPanel standings={state.gameOver?.final_standings ?? []} reason={state.gameOver?.reason ?? 'natural_end'} />
      );
  }
  return null;
}
```

- [ ] **Step 2: Verify it compiles**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/room/HostPage.tsx
git commit -m "feat: add HostPage (phase-driven panel switch)"
```

---

### Task 15: `JoinPage`

**Files:**
- Create: `frontend/src/room/JoinPage.tsx`
- Create: `frontend/src/room/JoinPage.module.css`

**Interfaces:**
- Consumes: `RoomPrecheck` from `../types/room` (Task 2); `RoomErrorPanel` from `./panels/RoomErrorPanel` (Task 6); `useParams`, `useNavigate` from `react-router-dom`.
- Produces: `JoinPage()` — mounted at `/join/:pin` in Task 17. Calls `GET /rooms/{pin}` on mount (pre-check), then `POST /rooms/{pin}/join` on submit, navigating to `/play/:pin?player_id=...` on success.

- [ ] **Step 1: Write the component**

```tsx
import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import type { RoomPrecheck } from '../types/room';
import { RoomErrorPanel } from './panels/RoomErrorPanel';
import styles from './JoinPage.module.css';

export function JoinPage() {
  const { pin } = useParams<{ pin: string }>();
  const navigate = useNavigate();
  const [precheck, setPrecheck] = useState<RoomPrecheck | 'not_found' | 'loading'>('loading');
  const [nickname, setNickname] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!pin) return;
    let cancelled = false;
    fetch(`/rooms/${pin}`)
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data: RoomPrecheck) => {
        if (!cancelled) setPrecheck(data);
      })
      .catch(() => {
        if (!cancelled) setPrecheck('not_found');
      });
    return () => {
      cancelled = true;
    };
  }, [pin]);

  if (!pin) {
    return <RoomErrorPanel title="Room not found" message="No room PIN was given." />;
  }

  if (precheck === 'loading') {
    return null;
  }

  if (precheck === 'not_found') {
    return <RoomErrorPanel title="Room not found" message={`No room with PIN ${pin} exists.`} />;
  }

  if (precheck.status === 'finished') {
    return <RoomErrorPanel title="Game over" message="This room's game has already finished." />;
  }

  if (precheck.status === 'in_progress') {
    return <RoomErrorPanel title="Already started" message="This room's game is already in progress." />;
  }

  if (precheck.player_count >= 10) {
    return <RoomErrorPanel title="Room full" message="This room already has 10 players." />;
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    const response = await fetch(`/rooms/${pin}/join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nickname }),
    });
    setSubmitting(false);
    if (!response.ok) {
      setSubmitError(response.status === 409 ? 'This room is full or already started.' : 'Room not found.');
      return;
    }
    const data = (await response.json()) as { player_id: string };
    navigate(`/play/${pin}?player_id=${data.player_id}`);
  };

  return (
    <main className={styles.theme}>
      <form className={styles.stage} onSubmit={handleSubmit}>
        <p className={styles.pinLabel}>Joining Room {pin}</p>
        <input
          className={styles.nicknameInput}
          value={nickname}
          onChange={(event) => setNickname(event.target.value)}
          placeholder="Your nickname"
          required
        />
        {submitError && <p className={styles.error}>{submitError}</p>}
        <button className={styles.joinBtn} type="submit" disabled={submitting || nickname.trim() === ''}>
          Join Room
        </button>
      </form>
    </main>
  );
}
```

- [ ] **Step 2: Write the CSS module**

```css
.theme {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: #e9e6df;
  color: #1a1a1a;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  box-sizing: border-box;
}

.stage {
  max-width: 360px;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.pinLabel {
  font-family: Constantia, Georgia, serif;
  font-size: 13px;
  color: #4b5440;
  margin: 0;
}

.nicknameInput {
  width: 100%;
  font-family: Constantia, Georgia, serif;
  font-size: 15px;
  border: 1px solid #4b6043;
  border-radius: 2px;
  padding: 10px 12px;
  background: #f4f2e6;
  color: #1a1a1a;
  box-sizing: border-box;
}

.error {
  font-family: Constantia, Georgia, serif;
  font-size: 13px;
  color: #a13d2c;
  margin: 0;
}

.joinBtn {
  font-size: 12.5px;
  border: 1px solid #4b6043;
  background: #4b6043;
  color: #f4f2e6;
  padding: 8px 20px;
  border-radius: 2px;
  font-family: Rockwell, Georgia, serif;
  cursor: pointer;
}
.joinBtn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
```

- [ ] **Step 3: Verify it compiles**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/room/JoinPage.tsx frontend/src/room/JoinPage.module.css
git commit -m "feat: add JoinPage with GET /rooms/{pin} pre-check"
```

---

### Task 16: `PlayerPage`

**Files:**
- Create: `frontend/src/room/PlayerPage.tsx`

**Interfaces:**
- Consumes: `useRoomSocket` (Task 5); `WaitingPanel` (Task 11), `QuestionPanel` (Task 12), `RevealPanel` (Task 13), `LeaderboardPanel` (Task 9), `FinishedPanel` (Task 10), `RoomErrorPanel` (Task 6); `useParams`, `useSearchParams` from `react-router-dom`.
- Produces: `PlayerPage()` — mounted at `/play/:pin` in Task 17.

- [ ] **Step 1: Write the component**

```tsx
import { useParams, useSearchParams } from 'react-router-dom';
import { useRoomSocket } from './useRoomSocket';
import { WaitingPanel } from './panels/WaitingPanel';
import { QuestionPanel } from './panels/QuestionPanel';
import { RevealPanel } from './panels/RevealPanel';
import { LeaderboardPanel } from './panels/LeaderboardPanel';
import { FinishedPanel } from './panels/FinishedPanel';
import { RoomErrorPanel } from './panels/RoomErrorPanel';

export function PlayerPage() {
  const { pin } = useParams<{ pin: string }>();
  const [searchParams] = useSearchParams();
  const playerId = searchParams.get('player_id');

  const { state, send } = useRoomSocket({ pin: pin ?? '', role: 'player', playerId: playerId ?? undefined });

  if (!pin || !playerId) {
    return <RoomErrorPanel title="Missing player info" message="Join the room again to get a valid player link." />;
  }

  if (state.connection === 'closed') {
    return <RoomErrorPanel title="Disconnected" message="Lost connection to the room." />;
  }

  switch (state.phase) {
    case 'lobby':
      return <WaitingPanel pin={pin} />;
    case 'question_active':
      return state.currentQuestion ? (
        <QuestionPanel
          key={state.currentQuestion.round}
          question={state.currentQuestion}
          onSubmit={(selected) => send({ type: 'submit_answer', round: state.currentQuestion!.round, selected })}
        />
      ) : null;
    case 'reveal':
      return state.currentQuestion && state.lastReveal ? (
        <RevealPanel
          questionText={state.currentQuestion.question_text}
          options={state.currentQuestion.options}
          correctAnswers={state.lastReveal.correct_answers}
          explanation={state.lastReveal.explanation}
          result={state.lastReveal.results[playerId]}
        />
      ) : null;
    case 'leaderboard':
      return (
        <LeaderboardPanel
          standings={state.standings}
          round={state.currentQuestion?.round ?? 0}
          totalRounds={state.currentQuestion?.total_rounds ?? 0}
          isFinal={state.isFinalRound}
          currentPlayerId={playerId}
        />
      );
    case 'finished':
      return (
        <FinishedPanel
          standings={state.gameOver?.final_standings ?? []}
          reason={state.gameOver?.reason ?? 'natural_end'}
          currentPlayerId={playerId}
        />
      );
  }
  return null;
}
```

- [ ] **Step 2: Verify it compiles**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/room/PlayerPage.tsx
git commit -m "feat: add PlayerPage (phase-driven panel switch)"
```

---

### Task 17: Routing + Create Room entry point

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/FlashcardView.tsx`
- Modify: `frontend/src/components/FlashcardView.module.css`

**Interfaces:**
- Consumes: `HostPage` (Task 14), `JoinPage` (Task 15), `PlayerPage` (Task 16); `BrowserRouter`, `Routes`, `Route`, `useNavigate` from `react-router-dom`.
- Produces: the 4 live routes (`/`, `/host/:pin`, `/join/:pin`, `/play/:pin`); `FlashcardView` gains a required `onCreateRoom: () => void` prop and renders a "Create Room" button next to "Start Review".

- [ ] **Step 1: Add the `onCreateRoom` prop and button to `FlashcardView`**

Modify `frontend/src/components/FlashcardView.tsx`:

```tsx
import { useState } from 'react';
import type { Question, QuestionSet } from '../types/question';
import { distinctConcepts } from '../lib/renameConcept';
import { Flashcard } from './Flashcard';
import styles from './FlashcardView.module.css';

interface FlashcardViewProps {
  questionSet: QuestionSet;
  onStartReview: () => void;
  onUpdateQuestion: (index: number, updated: Question, renameFrom?: string) => void;
  onCreateRoom: () => void;
}

export function FlashcardView({ questionSet, onStartReview, onUpdateQuestion, onCreateRoom }: FlashcardViewProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isEditing, setIsEditing] = useState(false);
  const total = questionSet.questions.length;
  const current = questionSet.questions[currentIndex];

  const goPrev = () => setCurrentIndex((i) => Math.max(0, i - 1));
  const goNext = () => setCurrentIndex((i) => Math.min(total - 1, i + 1));

  return (
    <main className={styles.theme}>
      <div className={styles.cardStage}>
        <Flashcard
          key={currentIndex}
          question={current}
          otherConcepts={distinctConcepts(questionSet.questions, current.concept)}
          onSave={(updated, renameFrom) => onUpdateQuestion(currentIndex, updated, renameFrom)}
          onEditingChange={setIsEditing}
        />
        <p className={styles.flipHint}>Click to flip card</p>
        <div className={styles.cardNav}>
          <button className={styles.navBtn} onClick={goPrev} disabled={isEditing || currentIndex === 0}>
            ‹ prior
          </button>
          <span className={styles.progress}>
            Card {currentIndex + 1} of {total}
          </span>
          <button className={styles.navBtn} onClick={goNext} disabled={isEditing || currentIndex === total - 1}>
            next ›
          </button>
        </div>
        <div className={styles.actionRow}>
          <button className={styles.startReviewBtn} onClick={onStartReview} disabled={isEditing}>
            Start Review
          </button>
          <button className={styles.createRoomBtn} onClick={onCreateRoom} disabled={isEditing}>
            Create Room
          </button>
        </div>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Add `.actionRow` and `.createRoomBtn` to `FlashcardView.module.css`**

Append to the end of `frontend/src/components/FlashcardView.module.css`:

```css

.actionRow {
  display: flex;
  gap: 10px;
}

.createRoomBtn {
  font-size: 12.5px;
  border: 1px solid #4b6043;
  background: none;
  color: #4b6043;
  padding: 8px 20px;
  border-radius: 2px;
  font-family: Rockwell, Georgia, serif;
  cursor: pointer;
}
```

- [ ] **Step 3: Wire up routing and the Create Room handler in `App.tsx`**

Replace `frontend/src/App.tsx`'s contents with:

```tsx
import { useState } from 'react';
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import type { Question, QuestionSet } from './types/question';
import { renameConceptEverywhere } from './lib/renameConcept';
import { FlashcardView } from './components/FlashcardView';
import { ReviewSession } from './components/ReviewSession';
import { fixtureQuestionSet } from './fixtures/fixture';
import { HostPage } from './room/HostPage';
import { JoinPage } from './room/JoinPage';
import { PlayerPage } from './room/PlayerPage';

function FlashcardHome() {
  const [view, setView] = useState<'browse' | 'review'>('browse');
  const [questionSet, setQuestionSet] = useState<QuestionSet>(fixtureQuestionSet);
  const navigate = useNavigate();

  const updateQuestion = (index: number, updated: Question, renameFrom?: string) => {
    setQuestionSet((prev) => {
      let questions = prev.questions.map((q, i) => (i === index ? updated : q));
      if (renameFrom) {
        questions = renameConceptEverywhere(questions, renameFrom, updated.concept);
      }
      return { questions };
    });
  };

  const handleCreateRoom = async () => {
    const response = await fetch('/rooms', { method: 'POST' });
    if (!response.ok) return;
    const data = (await response.json()) as { pin: string };
    navigate(`/host/${data.pin}`);
  };

  if (view === 'review') {
    return <ReviewSession questionSet={questionSet} onExit={() => setView('browse')} />;
  }

  return (
    <FlashcardView
      questionSet={questionSet}
      onStartReview={() => setView('review')}
      onUpdateQuestion={updateQuestion}
      onCreateRoom={handleCreateRoom}
    />
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<FlashcardHome />} />
        <Route path="/host/:pin" element={<HostPage />} />
        <Route path="/join/:pin" element={<JoinPage />} />
        <Route path="/play/:pin" element={<PlayerPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
```

- [ ] **Step 4: Verify it compiles**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/FlashcardView.tsx frontend/src/components/FlashcardView.module.css
git commit -m "feat: wire up Room routes and Create Room entry point"
```

---

### Task 18: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Type-check**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 2: Lint**

Run: `npm run lint`
Expected: no errors.

- [ ] **Step 3: Run the full test suite**

Run: `npm test`
Expected: all tests pass, including the 12 new tests from Tasks 3-4 plus every pre-existing test.

- [ ] **Step 4: Fix any failures found**

If any step above fails, fix the specific issue and re-run that step before moving on — do not proceed to Task 19 with a red build.

---

### Task 19: Manual live smoke test

**Files:** none (manual verification only, matching the existing `PROGRESS.md`-documented approach for both the backend build and Build 1's flashcard prototype — no mocked-WebSocket test harness exists in this repo)

- [ ] **Step 1: Start the backend**

Run from `backend/` (separate terminal, left running):
```bash
uvicorn app.main:app --reload
```
Expected: `Uvicorn running on http://127.0.0.1:8000`

- [ ] **Step 2: Start the frontend**

Run from `frontend/` (separate terminal, left running):
```bash
npm run dev
```
Expected: Vite prints a local URL (e.g. `http://localhost:5173`).

- [ ] **Step 3: Host flow — create and start a Room**

In a browser tab, open the frontend URL. Click "Create Room" on the flashcard view.
Expected: navigates to `/host/<4-digit-pin>`, shows the Lobby panel with the PIN, a QR code, and "Players (0/10)".

- [ ] **Step 4: Player flow — join from a second tab**

Open a second tab (or an incognito window) at `/join/<pin>` (the PIN from Step 3). Enter a nickname, click "Join Room".
Expected: navigates to `/play/<pin>?player_id=...`, shows "Waiting for the host to start the game…". Back in the Host tab, the new nickname appears in the roster within a second or two (via `player_joined`).

- [ ] **Step 5: Start the game and answer a round**

In the Host tab, click "Start Game".
Expected: Host tab shows "Round 1 of 8" / "Waiting for answers…"; Player tab shows the question with options.

In the Player tab, select an answer (tap an option for Multiple-Choice, or select 1+ options and click Submit for Select-All).
Expected: Player tab shows "Correct!"/"Incorrect" plus points and the explanation within ~1 second (single connected Player, so the round ends as soon as they answer). Host tab shows the Leaderboard panel with the Player's score and rank, plus "Next Question"/"Finish" and "End Game" buttons.

- [ ] **Step 6: Play through to the end**

Click "Next Question" repeatedly (answering each round in the Player tab) until the last round.
Expected: after the final round's Leaderboard, the Host's button reads "Finish"; clicking it shows the Finished panel with final standings on both tabs.

- [ ] **Step 7: Verify no console errors**

Check the browser DevTools console in both tabs throughout Steps 3-6.
Expected: no uncaught errors (WebSocket connect/disconnect logs, if any, are not errors).

- [ ] **Step 8: Record the result**

If all steps pass, note in your final report to Tri that the manual smoke test passed, listing the two commands used to start backend/frontend. If anything failed, fix the specific issue, re-run the affected verification task, and re-attempt this smoke test before considering the plan done — do not report success on a failed smoke test.
