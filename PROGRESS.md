# Progress & Todos — Note Review (v1)

## Done

### Planning & requirements docs

- Established domain terminology in `CONTEXT.md` (Note, Question Set, Question, Multiple-Choice/Select-All, Review Session, Summary, Concept, Analyzer, Generator, Verifier, v2 Room/Host/Player).
- Wrote `requirements.md` v1 functional scope (input constraints, generation rules, Review Session behavior, error handling, platform/persistence) plus v1.x/v2 planned-version notes.
- Evaluated `SessionStore` backing-storage options in `storage-options.md`; recommended lock-guarded nested hashmap (#13) as the structure that carries unchanged from v1 into v2 Room state.
- Wrote `DESIGN.md`: generation pipeline (Analyzer → user checkpoint → Generator → Verifier loop → freeze → flashcard display → in-place editing), 3-agent architecture (Analyzer/Generator/Verifier, Python-orchestrated loop capped at 5 verify iterations), and full data model (`ConceptAllocation`, `Question`, `QuestionSet`, Pydantic-validated fixed sizes).
- Created GitHub repo (`note-review`) to store progress, plus a separate `flashcard-prototype` branch for the first barebone flashcard implementation.
- Grilling session: resolved a stale NVIDIA NIM → Groq (`deepseek-r1-distill-llama-70b`) inconsistency between `requirements.md` and `DESIGN.md`/`CONTEXT.md` (flagging the model-specific empirical claims in `DESIGN.md` — speed, rate limit, quirks — as unverified until re-tested against the new model); added Intended User & Needs, consolidated Non-Goals, and a Given/When/Then Acceptance Criteria section to `requirements.md`; fixed v1.x ordering and v2-after-v1.x sequencing.



## Current State

`requirements.md` considered done — scope fully defined (intended user, needs, use cases, non-goals, acceptance criteria, planned-version ordering). `DESIGN.md` still needs major rework, not just the Groq/model swap already patched in: capacity map (rate limits, upload cap, verify-loop cap, Room cap — currently scattered/missing), API contract/schema (FastAPI endpoints, request/response shapes), agent prompts (Analyzer/Generator/Verifier actual instructions), and re-verification of the model-specific claims flagged unverified after the Groq swap (speed, wiring, quirks). No implementation code exists right now (`src/` was removed). Nothing has been prototyped or wired yet this round.

## Todo

- [ ] Rework `DESIGN.md`:
  - [ ] Write capacity map (upload size cap, Groq rate limit — re-measure, don't reuse NIM's ~40 RPM, verify-loop 5-iteration cap, Room's 10-Player cap).
  - [ ] Write API contract/schema (FastAPI endpoint list + request/response shapes, or generate from OpenAPI once built).
  - [ ] Write out actual specified prompts/instructions for each of the 3 agents (Analyzer, Generator, Verifier), not just their role/shape — input, output contract, quality bar enforced.
  - [ ] Re-verify the Groq-swap claims flagged unverified: `OpenAIChatCompletionsModel` wrapping still needed or not, R1-distill chain-of-thought vs structured `output_type` parsing, speed/quirk re-test against `deepseek-r1-distill-llama-70b`.
- [ ] Build a prototype flashcard display using a hand-written (not agent-generated) sample Question, to validate the display/UX independent of the generation pipeline before any agent is wired up.
- [ ] Implement and wire the agents (Analyzer/Generator/Verifier), and test their real output — this comes after the above two are settled.



## Deferred (not started, tracked in `requirements.md` Planned Versions)

- Real Review Session: shuffled forward-only pass, per-answer feedback, end Summary.
- v1.x: multi-PDF merge, regeneration controls, difficulty levels, larger file support, spaced-repetition/requeue mechanics.
- v2: Kahoot-style Room/Host/Player live game mode.

