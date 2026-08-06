# Note Review

## Responsibilities

**You (Tri):** project objective, scope, structure/tradeoff decisions, review and design all code, check real results, give feedback.

**Claude Code:** read and compile information, propose solutions after, implement per agreed design, find errors/inconsistencies, review and update this doc, clarify via /grilling whenever more info/context needed.

Turns a student's PDF notes into an AI-generated question set that can be reviewed like flashcards, and (in a later version) played as a live multiplayer quiz game.

## Required Documents

Docs this project runs on.

- **Requirements** (`requirements.md`) — functional scope, v1 behavior contract. Exists.
- **Design** (`DESIGN.md`) — pipeline architecture, agent responsibilities, data model. Exists.
- **State** (`PROGRESS.md`) — done/current/todo log, source of truth for what's actually built vs. planned. Exists.
- **Capacity map** — system limits (upload size cap, NIM rate limit ~40 RPM, verify-loop 5-iteration cap, Room's 10-Player cap, etc.). Not yet written.
- **API contract/schema** — FastAPI endpoint list + request/response shapes (or the auto-generated OpenAPI schema once built). Not yet written. Direction decided: FastAPI backend; SSE streaming on `POST /generate` for pipeline progress; session identified via HTTP-only cookie; Analyzer-checkpoint allocation edits are pure client-side, full edited allocation sent as the `/generate` request body.
- **Coding convention** — Not yet written as a standalone doc. Decided: Ruff (lint + format) and mypy for Python; React + TypeScript + Vite for frontend. Testing: pytest required for deterministic backend logic (Pydantic validators, weight reconciliation, snippet checks, SessionStore); live-LLM pipeline covered by a separate manual e2e script, not the required/CI suite; Vitest for frontend.
- **Parts not to touch**:
  - `.env` — never read contents into chat/commits, never modify values, only report what needs to change.
  - Planning docs (`CONTEXT.md`, `DESIGN.md`, `requirements.md`) — strictly read-only unless explicitly asked to update.
  - Provider/model choice (NVIDIA NIM, `deepseek-ai/deepseek-v4-pro`) — never switched unprompted; flag and let Tri decide.

## Definition

**Note**:
The single PDF document a user uploads as the source material for question generation.
*Avoid*: Document, file, PDF (when referring to the uploaded content as a domain object)

**Question Set**:
The collection of questions the agent generates from one Note in a single generation run.
*Avoid*: Deck, quiz, question bank

**Question**:
A single generated item with exactly 4 answer options, of type Multiple-Choice or Select-All.

**Multiple-Choice Question**:
A Question with exactly one correct option, presented with radio-button controls.
*Avoid*: Single-answer question

**Select-All Question**:
A Question where 1 to 4 of the 4 options may be correct, presented with checkbox controls so it's visually distinct from a Multiple-Choice Question regardless of how many options happen to be correct.
*Avoid*: Multi-select question, checkbox question

**Concept**:
A key topic the Analyzer identifies within a Note, assigned a weight (percentage of the Note's overall importance) and a corresponding allocated question count. Every generated Question is tagged with the Concept it came from.
*Avoid*: Topic, Section (when referring to this weighted allocation unit specifically)

**Analyzer**:
The agent that runs once per generation request, before Generation, to identify a Note's Concepts, weigh them, and allocate a question count to each. Its output is reviewed and can be adjusted by the user before Generation proceeds.
*Avoid*: Planner

**Generator**:
The agent that produces Questions from a Note, either for the initial full pass (from the confirmed Concept allocation, one Question per allocated slot) or for a patch pass (rewriting specific Questions, same index, flagged by the Verifier).

**Verifier**:
The agent that checks a generation run's Questions against the Note for correctness and quality, flagging individual Questions with a `keep`/`patch` action (list length is locked before generation starts, so no remove/split action exists). Drives the internal verify loop (capped at 5 iterations) that runs after the Generator's initial pass.
*Avoid*: Checker, Validator

**Review Session**:
A single forward-only pass through a Question Set, in shuffled order, ending in a Summary.
*Avoid*: Flashcard mode, study mode, practice mode

**Summary**:  
The end-of-Review-Session screen showing the score (correct/total) and the list of missed Questions with their explanations.  
*Avoid*: Results screen, recap

**Room**:
A live multiplayer game created by a Host from a Question Set, joined by Players via a 4-digit PIN or QR code, capped at 10 Players, ending immediately if the Host disconnects.
*Avoid*: Game, Lobby, Session (Session is reserved for Review Session)

**Host**:
The user who generated the Question Set and created the Room. Controls game flow (starts the game) but does not answer Questions and has no score.
*Avoid*: Presenter, Admin

**Player**:
A participant who joins a Room via PIN or QR code and answers Questions during the game to earn points.
*Avoid*: Guest, User