# Note Review

## Responsibilities

**You (Tri):** project objective, scope, structure/tradeoff decisions, review and design all code, check real results, give feedback.

**Claude Code:** read and compile information, propose solutions after, implement per agreed design, find errors/inconsistencies, review and update this doc, clarify via /grilling whenever more info/context needed.

Turns a student's PDF notes into an AI-generated question set that can be reviewed like flashcards, and (in a later version) played as a live multiplayer quiz game.

## Language

**Note**:
The single PDF document a user uploads as the source material for question generation.
_Avoid_: Document, file, PDF (when referring to the uploaded content as a domain object)

**Question Set**:
The collection of questions the agent generates from one Note in a single generation run.
_Avoid_: Deck, quiz, question bank

**Question**:
A single generated item with exactly 4 answer options, of type Multiple-Choice or Select-All.

**Multiple-Choice Question**:
A Question with exactly one correct option, presented with radio-button controls.
_Avoid_: Single-answer question

**Select-All Question**:
A Question where 1 to 4 of the 4 options may be correct, presented with checkbox controls so it's visually distinct from a Multiple-Choice Question regardless of how many options happen to be correct.
_Avoid_: Multi-select question, checkbox question

**Concept**:
A key topic the Analyzer identifies within a Note, assigned a weight (percentage of the Note's overall importance) and a corresponding allocated question count. Every generated Question is tagged with the Concept it came from.
_Avoid_: Topic, Section (when referring to this weighted allocation unit specifically)

**Analyzer**:
The agent that runs once per generation request, before Generation, to identify a Note's Concepts, weigh them, and allocate a question count to each. Its output is reviewed and can be adjusted by the user before Generation proceeds.
_Avoid_: Planner

**Generator**:
The agent that produces Questions from a Note, either for the initial full pass (from the confirmed Concept allocation, one Question per allocated slot) or for a patch pass (rewriting specific Questions, same index, flagged by the Verifier).

**Verifier**:
The agent that checks a generation run's Questions against the Note for correctness and quality, flagging individual Questions with a `keep`/`patch` action (list length is locked before generation starts, so no remove/split action exists). Drives the internal verify loop (capped at 5 iterations) that runs after the Generator's initial pass.
_Avoid_: Checker, Validator

**Review Session**:
A single forward-only pass through a Question Set, in shuffled order, ending in a Summary.
_Avoid_: Flashcard mode, study mode, practice mode

**Summary**:
The end-of-Review-Session screen showing the score (correct/total) and the list of missed Questions with their explanations.
_Avoid_: Results screen, recap

## Live Game (v2)

**Room**:
A live multiplayer game created by a Host from a Question Set, joined by Players via a 4-digit PIN or QR code, capped at 10 Players, ending immediately if the Host disconnects.
_Avoid_: Game, Lobby, Session (Session is reserved for Review Session)

**Host**:
The user who generated the Question Set and created the Room. Controls game flow (starts the game) but does not answer Questions and has no score.
_Avoid_: Presenter, Admin

**Player**:
A participant who joins a Room via PIN or QR code and answers Questions during the game to earn points.
_Avoid_: Guest, User
