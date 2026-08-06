# Requirements — Note Review (v1)

Turns a student's PDF notes into an AI-generated Question Set, reviewable as a single-pass Review Session. See `CONTEXT.md` for canonical terminology.

v1 scope only. Kahoot-style live game mode is v2 (see Planned Versions below).

## Functional Requirements

### Input

- User uploads exactly one PDF Note per generation request.
- Note must be text-based (selectable text). Scanned/image-only PDFs are rejected with a clear error — no OCR in v1.
- Max upload size: 20MB. No separate page-count limit.
- Note content must be in English. No multi-language support in v1.



### Question generation

- Uses the OpenAI Agents SDK (the orchestration framework) via three agents (Analyzer, Generator, Verifier) plus a self-checking verify loop. The underlying model calls run against NVIDIA NIM's free API (not OpenAI's own billed models) — see `DESIGN.md` for the model comparison and why. Full pipeline detail, agent responsibilities, and data model live in `DESIGN.md` — this section states behavior only.
- Before generation, an Analyzer pass identifies key concepts in the Note, weighs their relative importance, and allocates a question count per concept. The user reviews and can adjust this concept/weight/count breakdown before generation proceeds.
- After the Analyzer's allocation is confirmed, generation runs through an internal generate-then-verify loop (capped at 5 verify iterations) that checks each Question for correctness and quality against the Note before the Question Set is finalized. This loop is internal to one generation request — it is not user-facing regeneration.
- Generation is one-shot per upload from the user's perspective: no user-triggered regenerating of the whole Question Set or individual Questions in v1. To try again, user re-uploads (or retries after a failure — see below).
- If user specifies a desired question count, the agent honors it. To hit the count, the agent may generate multiple Questions covering the same underlying point, as long as each is distinct in phrasing, format, or answer choices.
- If user does not specify a count, the agent decides how many Questions to generate based on how many key points it identifies in the Note.
- The agent generates as many Questions as the content reasonably supports. If the resulting total is fewer than 5, the response includes an explanation of why (e.g. sparse content).
- Each Question has exactly 4 answer options.
- The agent freely decides, per Question, whether it is Multiple-Choice (1 correct option) or Select-All (1–4 correct options) based on what best fits the content. Users cannot control or override this.
- Multiple-Choice Questions render with radio-button controls; Select-All Questions render with checkbox controls, so the type is visually obvious independent of how many options are actually correct.
- Each Question includes a short explanation (grounded in the Note's content and citing the Note page it's drawn from) used for post-answer feedback.
- After generation, the user can edit any Question's text, options, correct answers, or explanation in place from the flashcard/review view, at any time. No adding or removing Questions from the set in v1.



### Review Session

- Single pass through the Question Set, in shuffled (random) order.
- Forward-only navigation — no going back to a previous Question.
- After answering each Question, the user immediately sees correct/incorrect plus the Question's explanation.
- At the end of the session, show a Summary: score (X/Y correct) and the list of missed Questions with their explanations.



### Error handling

- Non-PDF file, oversized file, or scanned/image-only PDF: reject upload with a clear, specific error before generation is attempted.
- Generation pipeline failure or timeout (e.g. from the NVIDIA NIM API — the free tier has no production SLA and can be flaky, per `DESIGN.md`): show a generic error message with a retry button that re-attempts generation using the already-uploaded Note (no re-upload needed).



### Platform & persistence

- Web app (responsive), no native mobile/desktop app in v1.
- No user accounts or login. Question Sets and Review Session state persist per session/device only.



## Non-Functional Notes

- English-only content and text-based-PDF-only input are deliberate scope cuts to keep generation quality and QA surface manageable.



## Planned Versions (1.x – 2.x)

Features discussed or explicitly deferred during requirements gathering, not committed to v1. Ordering/timeline TBD — edit as needed.

### v1.x (flashcard/review track — incremental improvements)

- Multi-PDF upload: merge multiple Notes into a single Question Set.
- Regeneration controls: regenerate the whole Question Set, or a single Question, without re-uploading.
- Adjustable difficulty levels for generated Questions.
- Larger file support (raise or remove the 20MB cap, chunked processing for big Notes).
- Deeper review mechanics: spaced repetition, requeueing missed Questions, "mark as known / still learning."



### v2 (Kahoot-style live game mode)

Reuses the v1 upload → generate flow directly (no separate v2 upload path, no browsing previously-saved Question Sets). After generation, the user lands on a hub screen with two options — **Review** (v1 flow) or **Create Room** (below) — and returns to this hub after finishing either, so the same Question Set can be reviewed and/or used to host a Room repeatedly.

- Host creates a Room from a Question Set; Players join via a 4-digit numeric PIN or QR code.
- Room capped at 10 Players. No accounts — nothing about a Player beyond their nickname and score is stored.
- Nickname entry per joining Player; duplicate nicknames are auto-suffixed ("(1)", "(2)", ...) rather than rejected.
- Host is spectator/controller only: starts the game manually whenever ready (no minimum Player count), does not answer Questions, has no score. No kick control.
- Join window closes once the Host starts the game — no joining mid-game.
- If a Player disconnects mid-game, they are not removed but cannot rejoin — no reconnect flow in v2.
- If the Host disconnects, the Room ends immediately for everyone.
- Real-time sync (question changes, timer, leaderboard) via WebSocket connections.
- Questions cycle in random order during the game.
- 30-second time limit per Question; answer reveal happens after all Players have answered or the timer runs out.
- Scoring for correct answers is time-based: 0–5s = 100pts, 5–10s = 95pts, 10–15s = 90pts, 15–20s = 85pts, 20–25s = 80pts, 25–30s = 75pts. Incorrect answers and timeouts score 0.
- Leaderboard shown after each Question, plus a final leaderboard at game end.
- Room state (PINs, connected Players, scores, current Question) is expected to live in server memory (e.g. a nested hashmap keyed by room code) rather than a persistent store — consistent with no-accounts, single-process v2 scope. Revisit only if a multi-instance deployment becomes necessary.

