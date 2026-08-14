# Progress & Todos — Note Review

## Done

### Planning & requirements docs

- Established domain terminology in `CONTEXT.md` and wrote `requirements.md`'s v1 functional scope, use cases, non-goals, and acceptance criteria.
- Designed `DESIGN.md`: generation pipeline (Analyzer → checkpoint → Generator → Verifier loop → freeze → flashcard display), 3-agent architecture, and full data model.
- Resolved a stale NVIDIA NIM → Groq model inconsistency across the docs; fixed v1.x/v2 version ordering in `requirements.md`.
- Reworked `DESIGN.md`: added Capacity map, API contract, Extraction section; restructured generation around per-concept Question lists with a global index assigned upfront; added deterministic weight/count reconciliation.
- Drafted and finalized the 3 agent prompts (Analyzer, Generator initial/patch, Verifier) as free-text `--START--/--END--` output, parsed deterministically by Python.
- Cross-checked `CONTEXT.md`/`requirements.md`/`DESIGN.md` for consistency after each major change.
- Standardized 5 card themes to one size/layout; picked Botanical Field Guide as the default for the prototype build.
- Designed Game Room end-to-end (pipeline, state machine, join/scoring flow, data model, WS protocol, endpoints) on an isolated branch, then merged into `DESIGN.md`.

### Game Room

Originally built in a separate local clone (`game-room-build/`, own `.git`) per Tri's request, then merged into `main`.

- Backend (FastAPI + Pydantic): data model/store (PIN-keyed `RoomStore`, TTL sweep), HTTP endpoints, WS protocol + state machine, game logic (scoring, ranking). Built test-first, 76 pytest cases; 2 real bugs found and fixed (a `store.mutate()` re-entry deadlock, a missing Multiple-Choice validation).
- Frontend (extends the existing Vite + React + TS app): new routes (`/host/:pin`, `/join/:pin`, `/play/:pin`), `useRoomSocket` hook + reducer driving 8 phase panels. 49/49 tests pass, smoke-tested live via Chrome across both Host and Player roles.
- Pushed to `origin/game-room-build` (17 commits), then merged into `main` (2026-08-11) ahead of the original "wait for v1.x" plan — wired to a hardcoded fixture Question Set, not the real agent pipeline, at merge time.
- Manual test pass found 7 flags, all fixed and verified.
- Full test pass (2026-08-11/12) across flashcard view, Review Session, and Game Room: found and fixed 2 more real bugs — a StrictMode double-connect that killed freshly-created Rooms, and abandoned-Lobby TTL eviction leaving clients stranded with no notification. Fixture content swapped water-cycle → digestive-system for fresh test coverage. 77/77 backend, 49/49 frontend tests pass.
- Manual test pass + UI polish (2026-08-12): concept navigation bar, card sizing/spacing, redesigned Review Session Summary, Game Room score badges, ~75% Game Room UI size increase.

### Flashcard prototype

Built off a hand-written fixture Question Set to validate display/UX independent of the generation pipeline, styled off the Botanical Field Guide reference.

- Build 1 (2026-08-10): flashcard display and navigation (flip, Next/Prev, progress indicator), no editing yet. Verified live via Chrome; 6/6 tests, `tsc` clean.
- Build 2 (2026-08-10): Review Session (shuffled, forward-only, Summary screen).
- Build 3 (2026-08-10): in-place editing (field edits, Save/Cancel, concept rename/reassign).

### Agent pipeline

Implemented and iterated on the `agent-testing` branch, then ported into `backend/app/` and merged into `main`.

- Implemented and pipeline-wired the 3 agents; fixed 2 real prompt bugs found via live testing (Generator-patch reusing a stale `source_quote`, Verifier mis-flagging `is_select_all`).
- Compared split-per-concept vs. one big Generator call — big-call truncated and failed; split design kept, big-call branch dropped.
- Token/runtime optimizations: verify-loop skip, concurrency cap (parked — sequential stays default), explicit `max_tokens`, concept batching (tried, failed at scale, removed), Verifier page-scoping (~28% token cut). No quality regression across live validation.
- Built a dual-model Generator pool (`llama-3.3-70b-versatile` + `gpt-oss-20b`) with cross-model failover — a real concurrency win over single-model baselines.
- Quality pass on a new domain (French Revolution note): tightened ambiguous-distractor and duplicate-question quality-bar checks, added Groq prompt-caching-friendly prompt reordering, fixed a few incidental bugs (Unicode encoding, a tight `max_tokens` budget, a false-positive snippet rejection). One known issue left open: a concept can be allocated `question_count=0`, usually recovers after a retry.
- Merged all `agent-testing` architecture advances into `main`'s `DESIGN.md`, section by section, confirmed with Tri each time.
- Ported the pipeline code into `backend/app/`, wired real FastAPI endpoints with SSE progress streaming; added PDF text extraction (new work, not in `agent-testing`).
- Reconnected Game Room to source the real generated `QuestionSet` instead of the fixture default.
- Widened Verifier page-scoping to include neighbor pages (a fix snippet often needs context just before/after the source page).
- Added a Generator quality-bar rule on incorrect-option requirements (Generators only — Verifier prompt left untouched per Tri's call).
- Wired the frontend flashcard/edit view to the real backend session (`GET /session`, `PATCH /questions/{index}`, `PATCH /concepts/{old_name}`) instead of a local fixture; fixed a bug where a failed PATCH silently closed the edit form without saving; dropped a dead root-level `requirements.txt`.

### Frontend upload/checkpoint/generating UI

Built on branch `worktree-upload-checkpoint-generating-ui`, merged into `main` 2026-08-13, implementing the design from `design-mockups/selected-design.html` (demo-only "Preview state"/"Show next stage" controls dropped) and wiring it to the real pipeline.

- Three new stages — Upload (`POST /upload`, drag/drop + file picker, upload error mapping), Checkpoint (editable weight/count/name, delete-with-rebalance, source-quote view, live 100% balance gate), Generating (live progress dial driven by real `POST /generate` SSE events) — sharing a `JournalShell` chrome component.
- `App.tsx`'s session flow now routes Upload → Checkpoint → Generating → the existing flashcard/Review view, and resumes correctly from `GET /session` at any stage on reload (including polling to completion if reloaded mid-generation).
- Weight-rebalance, checkpoint-totals, SSE-buffer-parsing, and generation-progress logic extracted into pure `lib/` modules, TDD'd — 66/66 frontend tests pass; backend untouched (78/78 backend tests pass).
- Live-verified in Chrome against the real backend, not just unit tests: real Analyzer run (7 concepts from a synthetic water-cycle PDF), delete/rebalance, the imbalance guard, a full real `/generate` run through 4 verify rounds, landing on the real 18-question flashcard view, plus reload-while-ready resume. Reload-mid-generation resume verified by code review only (didn't catch a live window for it).

### Deployment

Backend moved onto Render (`render.yaml` Blueprint: Web Service + Postgres), driven by Game Room's WebSocket needs and the long multi-round generation pipeline not fitting a serverless model. Frontend, previously a separate cross-origin deployment on Vercel (`flashkahoo.vercel.app`), was then consolidated onto the same Render service to drop the CORS/cross-site-cookie complexity entirely.

- `render.yaml` at repo root: native Python Web Service (single instance, no autoscaling — matches the existing in-memory `SessionStore`/Room-dict design) + a Postgres instance, provisioned but no schema yet (reserved for future user-accounts/logging work, deliberately deferred). `buildCommand` now also builds the frontend (`npm ci && npm run build`) so the same deploy produces both.
- Backend: FastAPI serves the built frontend directly — Vite's `dist/assets` mounted as static files plus a SPA catch-all route registered after all API routes (see `main.py`). Same-origin, so `CORSMiddleware` and `FRONTEND_ORIGIN` are gone; session cookie is always `SameSite=Lax`, `Secure` gated on Render's auto-set `RENDER` env var. `/health/db` endpoint checks Postgres connectivity.
- Vercel project retired once this deployment is confirmed working live.
- Known issue: WebSocket connections to the Render backend are currently rejected at the edge (browser test: `closed code=1006`; curl: bare `403` with no app-level response header) — blocks Game Room in this deployment until resolved. Not something this consolidation fixes, since the rejection happens before the request reaches the app, regardless of caller origin. Rest of the pipeline (Upload → generation → flashcard/Review) unaffected.

## Current State

All 4 core docs are in sync. The flashcard prototype (all 3 builds), Game Room, the agent pipeline, and the Upload/Checkpoint/Generating frontend are all built and merged into `main`; the full flow (Upload → Checkpoint → Generating → flashcard/Review/editing) is wired to the real backend session — a new Question Set can be created end-to-end from the browser. Backend is now deployed on Render (see Deployment above); Game Room's WebSocket layer is currently broken in that deployment (see known issue).

## Todo

- [ ] Live end-to-end verification of the merged pipeline — upload a real Note, confirm agent generation, then flashcard display/Review Session/Game Room all work against that same `QuestionSet`. Attempted 2026-08-13 (`french_revolution_note.txt`); blocked mid-Verifier-round-1 by Groq's daily token cap (resets on a rolling 24h window). Upload→Checkpoint→Generating→flashcard-display leg now verified live on a separate synthetic Note (see Frontend upload/checkpoint/generating UI above) — Review Session and Game Room against that same freshly generated `QuestionSet` still unverified.
- [ ] User accounts to store previous question sets.
- [ ] Research a way to store/rate questions so models can learn from them without spending a lot more tokens.



## Deferred (not started, tracked in `requirements.md` Planned Versions unless noted)

- Theme switching — wiring the four saved reference themes (`assets/card-themes/`) in as selectable alternatives to the default.
- v1.x: multi-PDF merge, regeneration controls, difficulty levels, larger file support, spaced-repetition/requeue mechanics.
- Write a real root/main project README — `frontend/README.md` is still stock Vite template boilerplate, kept as-is for now to use as a base later.

