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



## Current State

All 4 core docs are in sync. The flashcard prototype (all 3 builds), Game Room, and the agent pipeline are built and merged into `main`; the flashcard/Review/editing frontend is wired to the real backend session. Remaining gap: no frontend upload/Analyzer-checkpoint UI yet, so a new Question Set can currently only be created by calling the backend directly — see Todo.

## Todo

- [ ] Live end-to-end verification of the merged pipeline — upload a real Note, confirm agent generation, then flashcard display/Review Session/Game Room all work against that same `QuestionSet`. Attempted 2026-08-13 (`french_revolution_note.txt`); blocked mid-Verifier-round-1 by Groq's daily token cap (resets on a rolling 24h window) — retry once it resets.
- [ ] Build frontend upload + Analyzer-checkpoint screens — the flashcard/edit view is wired to the backend, but there's still no way to create a new Question Set from the browser. Deferred to a later session per Tri's call.
- [ ] User accounts to store previous question sets.
- [ ] Research a way to store/rate questions so models can learn from them without spending a lot more tokens.



## Deferred (not started, tracked in `requirements.md` Planned Versions unless noted)

- Theme switching — wiring the four saved reference themes (`assets/card-themes/`) in as selectable alternatives to the default.
- v1.x: multi-PDF merge, regeneration controls, difficulty levels, larger file support, spaced-repetition/requeue mechanics.
- Write a real root/main project README — `frontend/README.md` is still stock Vite template boilerplate, kept as-is for now to use as a base later.

