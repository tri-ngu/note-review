# Requirements — Note Review (v1)

Turns a student's PDF notes into an AI-generated Question Set, reviewable as a single-pass Review Session, and playable as a live multiplayer Game Room. See `CONTEXT.md` for canonical terminology.

## Intended User & Needs

**Intended user**: any student self-studying from PDF notes or textbook excerpts — any age/level, any subject — working alone to prepare for a test/exam.

**User needs** (equal weight, not ranked):
- Time savings — skip manually turning notes into a testable question set.
- Self-testing capacity the student doesn't have alone — passive familiarity with material becomes an actual question bank.
- Turns solo review into a social/competitive study activity via Game Room.

**Main use cases**:
1. Upload a Note, review/adjust the Analyzer's concept breakdown, generate a Question Set, review it (Review Session).
2. Re-review the same Question Set any number of times (reshuffled each time) without regenerating.
3. Edit a Question's text/options/answers/explanation in place, any time, without regenerating.
4. Retry generation after a pipeline failure, without re-uploading.
5. Upload a new Note, discarding the previous session's Question Set.
6. Host a live Game Room from a Question Set; Players join via PIN/QR and compete in real time.

## Functional Requirements

### Input

- User uploads exactly one PDF Note per generation request.
- Note must be text-based (selectable text). Scanned/image-only PDFs are rejected with a clear error — no OCR in v1.
- Max upload size: 20MB. No separate page-count limit.
- Note content must be in English. No multi-language support in v1.



### Question generation

- Uses the OpenAI Agents SDK (the orchestration framework) via three agents (Analyzer, Generator, Verifier) plus a self-checking verify loop. The underlying model calls run against Groq's free API (not OpenAI's own billed models) — see `DESIGN.md` for the model comparison and why. Full pipeline detail, agent responsibilities, and data model live in `DESIGN.md` — this section states behavior only.
- Before generation, an Analyzer pass identifies key concepts in the Note and weighs their relative importance; a question count per concept is then derived from those weights. The user reviews and can adjust this concept/weight/count breakdown before generation proceeds.
- After the Analyzer's allocation is confirmed, generation runs through an internal generate-then-verify loop (capped at 5 verify iterations) that checks each Question for correctness and quality against the Note before the Question Set is finalized. This loop is internal to one generation request — it is not user-facing regeneration.
- Generation is one-shot per upload from the user's perspective: no user-triggered regenerating of the whole Question Set or individual Questions in v1. To try again, user re-uploads (or retries after a failure — see below).
- If user specifies a desired question count, the agent honors it. To hit the count, the agent may generate multiple Questions covering the same underlying point, as long as each is distinct in phrasing, format, or answer choices.
- If user does not specify a count, the system decides how many Questions to generate based on how many key points it identifies in the Note.
- The agent generates as many Questions as the content reasonably supports. If the resulting total is fewer than 5, the response includes an explanation of why (e.g. sparse content).
- Each Question has exactly 4 answer options.
- The agent freely decides, per Question, whether it is Multiple-Choice (1 correct option) or Select-All (1–4 correct options) based on what best fits the content. Users cannot control or override this.
- Multiple-Choice Questions render with radio-button controls; Select-All Questions render with checkbox controls, so the type is visually obvious independent of how many options are actually correct.
- Each Question includes a short explanation (grounded in the Note's content and citing the Note page it's drawn from) used for post-answer feedback.
- After generation, the user can edit any Question's text, options, correct answers, or explanation in place from the flashcard display (browse view), at any time. No adding or removing Questions from the set in v1.



### Review Session

- Single pass through the Question Set, in shuffled (random) order.
- Forward-only navigation — no going back to a previous Question.
- After answering each Question, the user immediately sees correct/incorrect plus the Question's explanation.
- At the end of the session, show a Summary: score (X/Y correct) and the list of missed Questions with their explanations.
- User can restart the Review Session (reshuffled) any number of times on the same Question Set. Each pass is independent — no score history kept across passes.



### Error handling

- Non-PDF file, oversized file, or scanned/image-only PDF: reject upload with a clear, specific error before generation is attempted.
- Generation pipeline failure or timeout (e.g. from the Groq API — the free tier has no production SLA and can be flaky, per `DESIGN.md`): show a generic error message with a retry button that re-attempts generation using the already-uploaded Note (no re-upload needed).



### Platform & persistence

- Web app (responsive). No native mobile/desktop app — permanent non-goal, not just a v1 cut (see Non-Goals).
- No user accounts or login — permanent non-goal, not just a v1 cut (see Non-Goals). Session identified via HTTP-only cookie.
- Question Set and Review Session state persist server-side, in memory, keyed by that cookie, until the server process restarts. No database, no persistence across a server restart.
- One Question Set per session at a time — a new upload replaces the previous Question Set. No browsing or switching between previously-generated Question Sets in v1.



### Game Room

- Reachable via a "Create Room" button on the flashcard browse view, next to "Start Review".
- Host creates a Room from a Question Set; Players join via a 4-digit numeric PIN or QR code.
- Room capped at 10 Players. No accounts — nothing about a Player beyond their nickname and score is stored.
- Nickname entry per joining Player; duplicate nicknames are auto-suffixed ("(1)", "(2)", ...) rather than rejected.
- Host is spectator/controller only: starts the game manually whenever ready (no minimum Player count), does not answer Questions, has no score. No kick control.
- Join window closes once the Host starts the game — no joining mid-game.
- If a Player disconnects mid-game, they are not removed but cannot rejoin — no reconnect flow.
- If the Host disconnects, the Room ends immediately for everyone.
- Real-time sync (question changes, timer, leaderboard) via WebSocket connections.
- Questions cycle in random order during the game.
- 30-second time limit per Question. Once all Players have answered (or the timer runs out), each Player sees an answer-reveal screen (their answer vs. the correct answer, plus explanation); the Host sees the same reveal information and advances to the leaderboard manually, whenever ready.
- Scoring for correct answers is time-based: 0–5s = 100pts, 5–10s = 95pts, 10–15s = 90pts, 15–20s = 85pts, 20–25s = 80pts, 25–30s = 75pts. Incorrect answers and timeouts score 0.
- Leaderboard shown after each Question (Host-advanced from the reveal screen), plus a final leaderboard at game end.
- Room state (PINs, connected Players, scores, current Question) lives in server memory (a nested hashmap keyed by room code), not a persistent store — consistent with no-accounts, single-process scope.



## Non-Functional Notes

- English-only content and text-based-PDF-only input are deliberate scope cuts to keep generation quality and QA surface manageable.



## Non-Goals

**Permanent** — not deferred to any planned version, would require a scope decision to revisit:
- OCR / scanned or image-only PDFs.
- Multi-language Note content (English-only).
- User accounts or login.
- Native mobile or desktop app.

**v1-only** — cut for now, not scheduled, may be revisited:
- Export, download, or share of a Question Set (PDF/JSON/link). A Question Set exists only in-app, tied to the session cookie.
- Browsing or switching between multiple saved Question Sets — one active Question Set per session (see Platform & persistence above).



## Acceptance Criteria

### Upload & input validation
- Given a text-based PDF ≤20MB, when the user uploads it, then the upload succeeds and the Analyzer pass begins.
- Given a non-PDF file, when the user uploads it, then the upload is rejected with a specific "not a PDF" error before any generation attempt.
- Given a PDF over 20MB, when the user uploads it, then the upload is rejected with a specific "file too large" error before any generation attempt.
- Given a scanned/image-only PDF (no selectable text), when the user uploads it, then the upload is rejected with a specific "no extractable text" error before any generation attempt.
- Given a Note with non-English content, quality/behavior is best-effort and unvalidated in v1 — no dedicated rejection is required (English-only is a scope cut, not an enforced check).

### Analyzer checkpoint
- Given a successfully parsed Note, when the Analyzer pass completes, then the user sees a list of concepts, each with a `weight_percentage` and `question_count`, and the weights sum to 100.
- Given the checkpoint screen, when the user edits any `weight_percentage` or `question_count`, then totals recalculate live and confirmation is blocked until weights re-sum to 100.
- Given a confirmed allocation, when the user confirms, then the total `question_count` is locked and cannot change for the rest of that generation run.

### Generation & verify loop
- Given a confirmed allocation, when generation runs, then the resulting Question Set has exactly the locked total `question_count`, indexed 1..N, unchanged in length from Generator's initial pass through the verify loop.
- Given a generated Question, then it has exactly 4 options, is tagged Multiple-Choice (1 correct answer) or Select-All (1-4 correct answers), and includes an explanation and `page_number` grounded in the Note.
- Given the verify loop runs, when every concept's Verifier call returns satisfactory, then the loop exits early (before 5 iterations).
- Given the verify loop reaches 5 iterations without full satisfaction, then the Question Set ships as-is with a non-blocking notice, not an error.
- Given the user specified a target question count, when generation completes, then the Question Set's length equals that count (subject to the sparse-content case below).
- Given the user did not specify a count and the Note supports fewer than 5 Questions, when generation completes, then the response includes an explanation of why the count is low.

### Review Session
- Given a generated Question Set, when the user starts a Review Session, then Questions are presented one at a time, in shuffled order, with no backward navigation.
- Given the user answers a Question, then correct/incorrect feedback and that Question's explanation are shown immediately, before advancing.
- Given the last Question is answered, then a Summary appears showing score (X/Y correct) and the list of missed Questions with their explanations.
- Given a completed Review Session, when the user chooses to review again, then a new session starts on the same Question Set, reshuffled, independent of the previous pass's score.

### Editing
- Given a generated Question Set, when the user edits a Question's text, options, correct answers, or explanation from the flashcard display (browse view), then the change is saved and reflected immediately, without regenerating any other Question.
- Given an edit, then no Question can be added to or removed from the Question Set — length stays fixed at the frozen size.

### Error handling
- Given a generation pipeline failure or timeout, when it occurs, then a generic error message with a retry button is shown, and retry re-attempts generation using the already-uploaded Note without requiring re-upload.

### Persistence
- Given a valid session cookie, when the user closes and reopens the browser while the server process is still running, then their Question Set and Review Session state are still available.
- Given the server process restarts, then all in-memory Question Set/session state is lost — no recovery expected.
- Given a user uploads a new Note while a Question Set already exists for their session, then the previous Question Set is discarded and replaced.



## Planned Versions (1.x)

Features discussed or explicitly deferred during requirements gathering, not committed to v1. No hard dates — priority order only, fixed as listed.

1. Regeneration controls: regenerate the whole Question Set, or a single Question, without re-uploading.
2. Multi-PDF upload: merge multiple Notes into a single Question Set.
3. Deeper review mechanics: spaced repetition, requeueing missed Questions, "mark as known / still learning."
4. Adjustable difficulty levels for generated Questions.
5. Larger file support (raise or remove the 20MB cap, chunked processing for big Notes).

