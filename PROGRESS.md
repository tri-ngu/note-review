# Progress & Todos — Note Review (v1)

## Done

### Planning & requirements docs

- Established domain terminology in `CONTEXT.md` (Note, Question Set, Question, Multiple-Choice/Select-All, Review Session, Summary, Concept, Analyzer, Generator, Verifier, v2 Room/Host/Player).
- Wrote `requirements.md` v1 functional scope (input constraints, generation rules, Review Session behavior, error handling, platform/persistence) plus v1.x/v2 planned-version notes.
- Evaluated `SessionStore` backing-storage options in `storage-options.md`; recommended lock-guarded nested hashmap (#13) as the structure that carries unchanged from v1 into v2 Room state.
- Wrote `DESIGN.md`: generation pipeline (Analyzer → user checkpoint → Generator → Verifier loop → freeze → flashcard display → in-place editing), 3-agent architecture (Analyzer/Generator/Verifier, Python-orchestrated loop capped at 5 verify iterations), and full data model (`ConceptAllocation`, `Question`, `QuestionSet`, Pydantic-validated fixed sizes).
- Created GitHub repo (`note-review`) to store progress, plus a separate `flashcard-prototype` branch for the first barebone flashcard implementation.
- Grilling session: resolved a stale NVIDIA NIM → Groq (`deepseek-r1-distill-llama-70b`) inconsistency between `requirements.md` and `DESIGN.md`/`CONTEXT.md` (flagging the model-specific empirical claims in `DESIGN.md` — speed, rate limit, quirks — as unverified until re-tested against the new model); added Intended User & Needs, consolidated Non-Goals, and a Given/When/Then Acceptance Criteria section to `requirements.md`; fixed v1.x ordering and v2-after-v1.x sequencing.
- `DESIGN.md` rework: added Capacity map (upload/rate-limit/verify-loop/Room caps), API contract (FastAPI endpoints), Extraction section (`[Page N]` heading format, matches `water_cycle_note.txt`), Concurrency cap plan for the Generator/Verifier fan-out; reworked Pipeline for per-concept Question lists with a global index assigned upfront (was: single flat list from the start), and added deterministic largest-remainder reconciliation for per-concept `question_count` (mirrors the existing weight-drift correction). Live dummy call to Groq confirmed `deepseek-r1-distill-llama-70b` is decommissioned (HTTP 400, `model_decommissioned`) — model swapped to `gpt-oss-120b` throughout `DESIGN.md`, with its free-tier rate limits (30 RPM, 1K RPD, 8K TPM, 200K TPD) recorded in Capacity map.
- Drafted and iterated actual agent prompts (Analyzer, Generator initial/patch, Verifier) in `agents.txt`, switching from an SDK-level structured `output_type` to free-text `--START--/--END--`-delimited output parsed deterministically by Python; settled that Python (not the Analyzer) derives/decides `question_count` and the default total when unspecified. Merged the finished `## Agents` + `## Agent prompts` content from `agents.txt` into `DESIGN.md`.
- Consistency pass across `CONTEXT.md`/`requirements.md`/`DESIGN.md`: updated `CONTEXT.md`'s Required Documents (Capacity map, API contract now marked existing), provider/model name (`gpt-oss-120b`), and Analyzer/Generator definitions to match the Python-derives-question_count architecture; updated `requirements.md`'s generation-rules wording to match.
- All 5 card themes in `assets/card-themes/` (Botanical Field Guide, Chalkboard Classroom, Neubrutalist Quiz Show, Riso Print Zine, Vintage Postcard) standardized to one card size (`min(420px, 92vw)` × 540px) with no scrolling needed, and stripped down to just flashcard view + Prev/Next + Card X/total — ready to use as-is. Prototype build will only wire up the default (Botanical Field Guide); the other four stay saved for the later theme-switching build.



## Current State

`requirements.md` considered done — scope fully defined (intended user, needs, use cases, non-goals, acceptance criteria, planned-version ordering). `DESIGN.md` rework considered done: Capacity map, API contract, and Extraction sections added; Pipeline/Concurrent generation/Snippet grounding/Weight reconciliation updated for the per-concept-list restructure and the `gpt-oss-120b` model swap; actual Agent prompts (Analyzer/Generator/Verifier) written, iterated, and merged in from `agents.txt`. `CONTEXT.md` and `requirements.md` cross-checked against `DESIGN.md` and brought back in sync. No implementation code exists right now (`src/` was removed). Nothing has been prototyped or wired yet this round — next up is the flashcard-display prototype and wiring the agents.

## Todo

- [ ] Build a prototype flashcard display using a hand-written (not agent-generated) sample Question, to validate the display/UX independent of the generation pipeline before any agent is wired up. Ten aesthetic directions were explored and narrowed to five, saved as standalone reference files in `assets/card-themes/` (Botanical Field Guide as the default; Neubrutalist Quiz Show, Chalkboard Classroom, Riso Print Zine, and Vintage Postcard kept for later theme-switching) — the prototype build styles the real flashcard component off the default reference, reusing its card mechanics (click-to-flip, radio/checkbox by question type, Next/Prev + progress) rather than redesigning from scratch. Split into three builds next session:
  - [ ] Build 1 — flashcard display and navigation only (front/back flip, Next/Prev, progress indicator), no editing yet.
  - [ ] Build 2 — in-place editing from the flashcard view (per DESIGN.md's Editing section: field edits, Save/Cancel, concept rename/reassign).
  - [ ] Build 3 — theme switching, wiring the four saved reference themes in as selectable alternatives to the default.
- [ ] Implement and wire the agents (Analyzer/Generator/Verifier), and test their real output — this comes after the above two are settled.



## Deferred (not started, tracked in `requirements.md` Planned Versions)

- Real Review Session: shuffled forward-only pass, per-answer feedback, end Summary.
- v1.x: multi-PDF merge, regeneration controls, difficulty levels, larger file support, spaced-repetition/requeue mechanics.
- v2: Kahoot-style Room/Host/Player live game mode.

