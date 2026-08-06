# Progress & Todos — Note Review (v1)

## Done

### Planning & requirements docs

- Established domain terminology in `CONTEXT.md` (Note, Question Set, Question, Multiple-Choice/Select-All, Review Session, Summary, Concept, Analyzer, Generator, Verifier, v2 Room/Host/Player).
- Wrote `requirements.md` v1 functional scope (input constraints, generation rules, Review Session behavior, error handling, platform/persistence) plus v1.x/v2 planned-version notes.
- Evaluated `SessionStore` backing-storage options in `storage-options.md`; recommended lock-guarded nested hashmap (#13) as the structure that carries unchanged from v1 into v2 Room state.
- Wrote `DESIGN.md`: generation pipeline (Analyzer → user checkpoint → Generator → Verifier loop → freeze → flashcard display → in-place editing), 3-agent architecture (Analyzer/Generator/Verifier, Python-orchestrated loop capped at 5 verify iterations), and full data model (`ConceptAllocation`, `Question`, `QuestionSet`, Pydantic-validated fixed sizes).
- Created GitHub repo (`note-review`) to store progress, plus a separate `flashcard-prototype` branch for the first barebone flashcard implementation.



## Current State

Planning/requirements/design docs exist and are considered the solid, confirmed starting point. No implementation code exists right now (`src/` was removed). Nothing has been prototyped or wired yet this round.

## Todo

- [ ] Refine `requirements.md` and `DESIGN.md` further — in particular, write out the actual specified prompts/instructions for each of the 3 agents (Analyzer, Generator, Verifier), not just their role/shape. Should cover what each agent is told about its input, output contract, and the quality bar it's expected to enforce.
- [ ] Build a prototype flashcard display using a hand-written (not agent-generated) sample Question, to validate the display/UX independent of the generation pipeline before any agent is wired up.
- [ ] Implement and wire the agents (Analyzer/Generator/Verifier), and test their real output — this comes after the above two are settled.



## Deferred (not started, tracked in `requirements.md` Planned Versions)

- Real Review Session: shuffled forward-only pass, per-answer feedback, end Summary.
- v1.x: multi-PDF merge, regeneration controls, difficulty levels, larger file support, spaced-repetition/requeue mechanics.
- v2: Kahoot-style Room/Host/Player live game mode.

