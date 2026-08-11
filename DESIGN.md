# Design — Note Review

Structure and architecture for the full product: the v1 generation pipeline (uploaded Note → Question Set → flashcard review) and the v2 Room mode (Kahoot-style live multiplayer game). See `CONTEXT.md` for canonical terminology and `requirements.md` for functional scope — this doc covers *how* each part works internally and the concrete data model, which `requirements.md` intentionally leaves at the behavioral level. Room mode's architecture (Room pipeline, state machine, join/answer/scoring flow, data model, WebSocket protocol) is fully designed and implemented in the Room sections below — see `PROGRESS.md` for current build status.

This phase covers generation, a minimal linear flashcard display used to verify the pipeline end-to-end, and the real Review Session (shuffled order, strictly forward-only, per-question immediate feedback, ends in a Summary screen — see `requirements.md`'s Review Session acceptance criteria) reachable via a "Start Review" button on that flashcard display. (This pulls the Review Session forward from originally-deferred "later work" into this phase's scope — same pattern as Editing below.)

## Generation pipeline

```
Upload PDF
   |
   v
Extract text (once, cached as plain string with `[Page #]` headings inserted
   between pages — see Extraction below — reused by certain agent calls below)
   |
   v
Analyzer (runs once, not part of the loop)
   - identifies key concepts in the Note
   - assigns each concept a weight_percentage (all weights sum to 100;
     small drift is auto-corrected, see Weight reconciliation below)
   - extracts each concept's snippets: verbatim quotes + page_number,
     one or more per concept (see Snippet grounding below)
   - estimates a question_count per concept: round(weight_percentage / 100 * total),
     then reconciled (largest-remainder) so counts sum exactly to the total —
     see Weight reconciliation below
     (honors user-specified total count if given; otherwise Python decides a
      default total itself — not the Analyzer — per requirements.md's
      existing generation rules, then applies the same rounding+reconciliation
      against that total)
   |
   v
User checkpoint
   - user reviews the concept/weight/question_count breakdown
   - can inline-edit any weight_percentage or question_count
   - must re-sum to 100 before confirming — submission is blocked, not just
     flagged, while weights don't sum to 100
   - confirmed allocation (weights, counts, AND each concept's snippets) is
     handed to the Generator
   - total question_count across all concepts is now LOCKED — this is the
     final QuestionSet size, fixed before Generator ever runs
   |
   v
Generator — initial pass (unlooped, but fanned out concurrently)
   - one Generator call PER CONCEPT, fired concurrently (asyncio.gather),
     not one serial call covering every concept — see Concurrent generation
     below
   - each call sees only that concept's snippets, not the full Note
   - each call produces exactly the concept's allocated question_count
   - each Question gets its permanent global index (1..N, concept order,
     cumulative offset) the moment it's produced — index never changes after
     this point (see Data model)
   - results are kept in per-concept lists through the rest of the pipeline
     (convenient for the concept-scoped Verifier/patch fan-out below), each
     Question already carrying its fixed global index — not re-merged into
     one flat list until Freeze
   |
   v
Verify loop (up to 5 iterations)
   - Verifier checks every Question — one concurrent call per concept, each
     call sees only its own concept's Question list (addressed by their
     permanent global index) but the FULL Note
     (see Verify Loop Detail, Concurrent generation below)
   - if satisfactory == true (every concept's call agreed): break early
   - else: Generator patches (in place, same index) only the flagged Questions —
     one concurrent call per concept among the flagged indices, not one call
     per index and not one call for everything — loop continues, per-concept
     list lengths never change
   - after 5 iterations with no satisfactory result: ship as-is (best-effort),
     no error — surface a non-blocking note if issues remain, consistent with
     the existing sparse-content notice pattern
   |
   v
Freeze QuestionSet
   - per-concept lists are concatenated (ordered by each Question's already-
     fixed global index) into the final QuestionSet.questions — a merge in
     name only, since index was fixed back at the initial pass; total size
     unchanged from what Generator's initial pass produced
   |
   v
Linear flashcard display (this phase's UI)
   |
   +--> In-place editing (any time after generation, from the flashcard view)
   |
   +--> Review Session (via "Start Review"; shuffled, forward-only, ends in Summary)
```



## Extraction

Text extraction (`pypdf`) runs once per upload, producing the single cached string every downstream call works from (see Generation pipeline). Pages are extracted one at a time and joined with an explicit page heading, so every agent reading Note text can attribute a quote to the page it came from — this is what the Analyzer's and Verifier's snippet `page_number` fields ultimately trace back to.

Format: each page's heading is `[Page N]` (1-indexed, matching the PDF's actual page number) on its own line, followed by a blank line, then that page's extracted text, followed by a blank line before the next page's heading:

```
[Page 1]

<page 1 text>

[Page 2]

<page 2 text>
```

See `water_cycle_note.txt` for a full sample in this format. No other markup is inserted — paragraph breaks within a page are whatever `pypdf` produces from the source PDF, not normalized or reflowed.

## Capacity map

Hard limits and enforced caps, gathered in one place — scattered across the doc before this.

| Limit | Value | Enforced where | Notes |
|---|---|---|---|
| Note upload size | 20MB | Upload validation, before Analyzer runs | Per `requirements.md`; no separate page-count limit |
| Groq free tier (`gpt-oss-120b`) | 30 RPM, 1K RPD, 8K TPM, 200K TPD | Not enforced in code yet | [console.groq.com/docs/rate-limits](https://console.groq.com/docs/rate-limits). Tied to `gpt-oss-120b` — re-check on any model swap (`deepseek-r1-distill-llama-70b` decommissioned mid-project, see Weight reconciliation) |
| Verify loop iterations | 5 | Python orchestration loop, hard stop | Ships best-effort past cap, no error |
| Room Players | 10 | `POST /rooms/{pin}/join` | Per `requirements.md` |
| Room PIN space | 10,000 (4-digit) | PIN generation, retry-on-collision | Real usage ~3 concurrent Rooms — collision is rare, retry loop is trivial |
| Room question timer | 30s | Server-side, per QUESTION_ACTIVE round | Server-authoritative, see Room answer submission below |
| Room state TTL | 5 min | Periodic sweep, from `terminal_at` (or creation time for abandoned lobbies) | See Room cleanup below |
| Concurrent Rooms | unbounded (architecturally) | PIN-keyed dict | Expected real usage ~3; single-instance-pinned deployment assumption (see Room data model below) doesn't scale beyond what one Vercel Fluid Compute instance can hold in memory |

**Concurrency vs. rate limit**: worst case per request is N concurrent initial-pass calls + 5 rounds × (up to N Verifier calls + up to N patch calls), N = concept count. TPM (8K) is the tighter constraint in practice, not RPM (30) — every Verifier call alone carries the full Note, so a handful of concurrent Verifier calls burns TPM budget before RPM becomes the issue. No concurrency cap and no 429 backoff/retry exist yet (see Concurrent generation's Concurrency cap below) — a 429 currently surfaces as a generic pipeline failure, inheriting the existing retry-button behavior (`requirements.md` Error handling) rather than being handled inside the pipeline.

## Agents (OpenAI Agents SDK, on Groq)

Three distinct agents, each returning a formatted free-text response that Python parses deterministically into the corresponding objects — not an SDK-level structured Pydantic `output_type`. Orchestration (the checkpoint, the up-to-5 verify loop, patch dispatch) is plain Python control flow — **not** agent-internal handoffs or a self-driven tool loop. Each agent call is stateless; Note text and any other needed context is passed explicitly into every call. When calling any agent, send only that agent's own prompt below — the block wrapped in ``` — with any `{field}` placeholders filled in by Python control flow before sending. All agent output will be wrapped between --START-- and --END-- to indicate which parts should be read.

- **Analyzer** — input: Note text only (a user-specified target question count, if given, isn't used by this call — see the note below the Analyzer prompt). Output: free text, one block per Concept, parsed by Python into `concept` + `weight_percentage` + `snippets` — the `ConceptAllocation` fields minus `question_count`, which Python derives afterward from `weight_percentage` (see Weight reconciliation). Runs exactly once, before the loop.
- **Generator** — never reads the full Note, in either shape; only ever sees snippets:
  - **Initial pass**: one call per concept, run concurrently. Input is that concept's `(concept, question_count)` slot plus the Analyzer's snippets for it. Output: exactly `question_count` `Question` objects for that concept.
  - **Patch pass**: one call per *concept among the flagged indices*, run concurrently (not one call for every flagged index across the whole set). Input is the current numbered Question list, that concept's flagged indices + feedback, and the Verifier's snippets backing that fix. Output: replacement `Question` objects only for the indices it was asked to patch — same indices, list length unchanged.
- **Verifier** — one call per concept, run concurrently (see Concurrent generation below). Input: the FULL Note text (the only agent that ever gets it — see Snippet grounding below for why) plus only that concept's Questions, addressed by their permanent global index. Output per call: a critique for that concept's flagged indices (now including the Verifier's own extracted snippets backing each fix, not just prose feedback) plus a per-call `satisfactory: bool`; the round's overall result is `satisfactory` iff every concept's call was.



### Concurrent generation

Generator's initial pass fires one call per concept concurrently (`asyncio.gather`), not one serial call over the whole allocation — live testing found a single serial call spent 62% of pipeline wall time in that step; splitting by concept bounds the stage by the slowest single concept's call (incl. its retries), not the sum of all concepts.

Patch pass mirrors the per-concept fan-out directly — since a Verifier call's findings are already scoped to one concept's list, patch dispatch buckets by concept for free: one call per concept with any flagged issues, not one call per flagged index across the whole set. Grouping still matters for the same reason — two flagged Questions on the same concept land in one call, so the patch agent can't independently write near-duplicate fixes the way isolated per-index calls could. Each call is validated to return exactly its assigned (global) indices before merging back into that concept's list.

Verifier gets the same per-concept fan-out — one call per concept, operating on that concept's own Question list (each entry still carrying its permanent global index from the initial pass) — but unlike the Generator, every Verifier call still carries the full Note (narrowing it isn't safe, see Snippet grounding). A round's `satisfactory` is the AND of every concept's call; each call is validated to only return indices belonging to its own concept's list.

`call_agent` has an async implementation (`call_agent_async`, via `Runner.run`) with a sync wrapper for the pipeline's one non-concurrent call site (the Analyzer). Every call carries a `label`, recorded in an in-memory `CALL_LOG` (input/output/timing) since concurrent calls sharing an `Agent` would otherwise be indistinguishable in a transcript; optional `CALL_LOG_HOOK` streams each call on completion for live progress tooling.

**Concurrency cap**: nothing bounds simultaneous in-flight calls today — a high-concept-count Note can fire enough concurrent calls in one round to exceed Groq's free-tier limits (see Capacity map), TPM more often than RPM, since every Verifier call alone carries the full Note. Plan: a pipeline-wide semaphore capping simultaneous in-flight calls (placeholder N, needs live tuning against the 8K TPM ceiling), applying across the initial pass and every round's Verifier/patch fan-outs alike, not just one stage.

### Snippet grounding

The Verifier is the only agent in the whole pipeline that ever reads the full Note. The Analyzer and the Generator (both its shapes) work entirely from **snippets** — verbatim quotes + `page_number`, formatted as `["quoted text" : N]` (`N` = page number) — never the raw Note text:

- The Analyzer extracts one or more snippets per Concept during its single pass (a Concept discussed in multiple places gets multiple snippets). These become the Generator's **entire** view of the Note for that Concept's initial-pass call.
- The Verifier, when it flags a Question, extracts its own snippets backing the requested fix — reusing the Question's existing `source_quote` if that's already the right grounding, or pulling different/additional quotes if the actual problem is something the original grounding missed (e.g. a caveat stated elsewhere in the Note). These become the Generator's **entire** view of the Note for that patch call. This is *how* the pipeline still gets a wide-context safety net despite the Generator never reading the full Note: the Verifier is the one agent that does, so it's positioned to notice when a fix needs Note content beyond what a Question's own narrow slice contained, and to hand exactly that content forward — rather than either narrowing everything (losing the safety net) or handing the full Note to every call (losing the size/latency win).
- Every snippet, wherever it's produced — Analyzer's initial extraction, Verifier's per-issue extraction, or a Generator's `source_quote` copied from either — is validated deterministically as an exact (whitespace-normalized) substring of its source text (the Note, for Analyzer/Verifier snippets; the snippets it was given, for a Generator's `source_quote`) before being trusted. Any failure retries the call that produced it. Never trust a model's claim that a quote is real — same philosophy as the weight-sum and question-count checks elsewhere in this pipeline.
- `Question.source_quote` is stored on the Question itself, not just used internally to build prompts — a permanent field, part of the domain model (see Data model below), even though nothing in v1's UI displays it yet. Intended for a future citation UI (jump to/highlight the exact source text), and it also makes `page_number` provably correct rather than a separately-guessed field, since both come from the same verified snippet.

Net effect: the Note's full text is read by exactly one agent — the Verifier, on every one of its concurrent per-concept calls each round, plus the Analyzer once overall. Every Generator call, initial or patch, works from a narrow, pre-verified slice sized to what that specific call actually needs; the Verifier alone always gets the whole thing, which is what lets its concurrent calls stay safe despite each only checking one concept's Questions (see Concurrent generation above).

### Weight reconciliation

`ConceptAllocation`/`ConceptWeight.weight_percentage` values must sum to 100. Rather than always retrying the whole Analyzer call on any drift (a full network round-trip on the free tier — ~1-3min was NIM's figure, not yet re-measured for Groq), small drift is fixed deterministically in Python: if `abs(sum - 100) <= 10`, every weight is rescaled in place by `100 / sum` (preserves each concept's relative importance ratio) and the call succeeds as-is — no retry, no network cost. Drift beyond ±10 is treated as a genuine Analyzer mistake (e.g. a dropped or duplicated concept, not just rounding noise) and still falls back to `call_agent`'s blind full-call retry. Confirmed via live testing: a 102-vs-100 drift (2% — clearly rounding noise) was the only drift observed in testing so far.

**Question count derivation**: per-concept `question_count` is `round(weight_percentage / 100 * total)`, then reconciled deterministically in Python — largest-remainder method (concepts with the biggest rounding remainder each get +1, in order, until counts sum exactly to `total`) — same drift-correction philosophy as weights above, not left to agent judgment. Applies whether `total` is user-specified or Python-chosen (the Analyzer never decides or sees the total — see Agents above).

**Provider**: the `openai-agents` framework itself is unchanged, but model calls run against [Groq](https://groq.com)'s free OpenAI-compatible API (`https://api.groq.com/openai/v1`) instead of OpenAI's own billed models — wired via `set_default_openai_client()` + `set_default_openai_api("chat_completions")` + `set_tracing_disabled(True)`. **Confirmed (agent-testing branch, live Agents-SDK call)**: Groq's actual slug for this model is `openai/gpt-oss-120b` (vendor-prefixed — a live `GET /v1/models` check returned `openai/gpt-oss-120b`, not the bare `gpt-oss-120b` previously assumed here). The `/` in that slug hits the exact same SDK misparsing this section previously flagged only for NIM: the Agents SDK treats it as a `litellm/`-style provider prefix and silently strips it, so an unwrapped `Agent(model="openai/gpt-oss-120b")` sends bare `gpt-oss-120b` to Groq and gets back HTTP 404 `model_not_found`. Each `Agent`'s `model=` must be wrapped in `OpenAIChatCompletionsModel(model="openai/gpt-oss-120b", openai_client=...)`, same as the NIM wiring — this section's prior guess that Groq's slugs were `/`-free and wouldn't need it was wrong.

**Model**: `openai/gpt-oss-120b` (Groq's current vendor-prefixed slug — see Provider above), replacing `deepseek-r1-distill-llama-70b` — confirmed via a live dummy call during this doc's rework that Groq has decommissioned `deepseek-r1-distill-llama-70b` (HTTP 400, `model_decommissioned`); it's no longer usable regardless of provider preference. `gpt-oss-120b` is itself a reasoning model (OpenAI's open-weight release, harmony response format with a separate reasoning/analysis channel) — the same chain-of-thought-vs-structured-`output_type` concern flagged for the old model still applies, just not yet re-tested against this specific model/format. Prior empirical findings (call speed, `correct_answers` handling, the bundled-multiple-facts-in-one-option flaw) were measured against `deepseek-v4-pro` on NIM and don't carry over to `gpt-oss-120b` either. Not tracked as active work — flagged for whenever it becomes relevant.

**Rate limits**: see Capacity map above for `gpt-oss-120b`'s current Groq free-tier numbers.

Deterministic Python loop, not an LLM-controlled loop, because the 5-iteration cap and early-exit need to be reliably enforced rather than trusted to model judgment.

## Agent prompts

Actual instructions each Agent is constructed with (`Agent(name=..., instructions=..., output_type=...)`), not just role/shape from the Agents section above. Verifier's quality bar mirrors Verify loop detail's criteria verbatim (quoted here, not altering that section). Agent doesn't directly output `Question` or set objects, but rather formatted response that will be read by control flow and turned into said objects.

**Analyzer**
```
You are a tutor helping a student analyze their study Note and help them identify key concepts for review question generation.

Given the Note's full text, identify the Note's key Concepts — the distinct topics or ideas a student
would need to understand separately to master the material and weigh them based on importance. Each
page has been separated and has a heading [Page #] to be used as reference.

For each Concept, output:
- concept: a short, specific label (not "Introduction" or "Overview"). Format as
  "Concept name". 
- weight_percentage: this Concept's share of the Note's overall importance,
  as a float; across all Concepts these must sum to ~100 (small drift is
  corrected downstream — aim for accuracy, don't hand-round to force a sum).
  Use a number up to 2 decimal points for format.
- snippets: 1 or more verbatim quotes from the Note that ground this Concept,
  each paired with the page number it appears on. Quotes must be copied
  exactly, character-for-character — do not paraphrase or summarize. If a
  Concept is discussed in multiple places, include a snippet from each.
  Follow the format ["Quoted text" : N] for each snippet, where N is the
  page number the quote appears on.

Quality bar:
- Concepts must be non-overlapping — don't split one idea into two Concepts,
  don't let two Concepts describe the same underlying idea
- Weight should reflect depth of coverage in the Note, not position or length
  alone
- Every snippet must be an exact substring of the provided Note text — a
  fabricated or paraphrased quote fails downstream validation and forces a
  retry
- Do not invent Concepts not actually present in the Note

Output format:
- Separate each Concept's block from the next with at least 2 newlines
- Output nothing but the Concept blocks — no preamble, no closing remarks
- Wrap the entire output between --START-- and --END-- markers, exactly as
  shown in the example below

--START--
concept: "Blood vessel types"
weight_percentage: 20.33
snippets: ["Arteries carry blood away from the heart under high pressure." : 2],
	  ["Arterioles are smaller branches of arteries that regulate blood pressure." : 3]

concept: "Bone types"
weight_percentage: 79.67
snippets: ["Long bones act as levers to help you move, e.g. the femur." : 1]
--END--

```
Python parses this text deterministically into `concept` + `weight_percentage` + `snippets` per block — the agent just has to hit the format, Python builds the actual objects. `question_count` is never part of this call's output: when a target total is given, Python derives it from `weight_percentage` (see Weight reconciliation); when no target was specified, Python decides a default total itself — not the Analyzer — before applying that same derivation.

**Generator — initial pass**
```
You are writing exam-style questions for one Concept from a student's study
Note, using ONLY the snippets provided below — you have not seen and must
not assume anything about the rest of the Note.

Concept: {concept}
Snippets:
{snippets, each as ["quoted text" : N]}

Write exactly {question_count} Questions covering this Concept. For each,
output a block with these fields:
- question_text: a clear, self-contained question, as a quoted string
- options: exactly 4 answer choices, as a quoted-string list, e.g.
  ["Option A", "Option B", "Option C", "Option D"]
- correct_answers: 1-4 of the option positions (1-based) that are correct,
  as an int list, e.g. [1, 4]
- is_select_all: true or false — true if more than one option is intended
  as correct, or if "select all that apply" framing fits this content
  better than single-answer; false otherwise. Choose deliberately — not
  inferred from len(correct_answers).
- explanation: a quoted string explaining why the correct answer(s) are
  correct, using only the given snippets
- page_number: the page number (int) the grounding snippet came from
- source_quote: the exact snippet text (or relevant portion), as a quoted
  string, copied verbatim from a provided snippet — not paraphrased

Quality bar:
- Every fact used must trace to a provided snippet — never invent content,
  never use outside/general knowledge even if believed true
- Distractors must be plausible — wrong in a way a student could realistically
  believe, not absurd or trivially eliminable, not duplicates of each other
  or the correct answer
- Don't bundle multiple distinct facts into a single option
- If question_count exceeds what the snippets can support distinctly, vary
  phrasing/format/tested detail rather than repeating — never fabricate to
  hit the count
- source_quote must be an exact substring of one of the provided snippets

Output format:
- Separate each Question's block from the next with at least 2 newlines
- Output nothing but the Question blocks — no preamble, no closing remarks
- Wrap the entire output between --START-- and --END-- markers, exactly as
  shown in the example below

--START--
question_text: "Which process describes liquid water turning into vapor?"
options: ["Evaporation", "Condensation", "Infiltration", "Runoff"]
correct_answers: [1]
is_select_all: false
explanation: "Evaporation is liquid water becoming vapor, driven by the sun's heat."
page_number: 1
source_quote: "Evaporation is the process by which liquid water changes into water vapor and rises into the atmosphere."

question_text: "Which of the following are forms of precipitation?"
options: ["Rain", "Snow", "Evaporation", "Hail"]
correct_answers: [1, 2, 4]
is_select_all: true
explanation: "Rain, snow, and hail are precipitation forms; evaporation is a different process, not a form of it."
page_number: 3
source_quote: "Precipitation can take several forms depending on atmospheric temperature: rain, snow, sleet, or hail."
--END--

```
Python parses each block deterministically into a `Question` object (`concept` filled in by Python from the call context; each Question's permanent global index assigned positionally in output order — see Generation pipeline) — not an SDK-level structured `output_type` (see Agents section above).

**Generator — patch pass**
```
You are a tutor helping a student improve their review questions to study for an exam. Their
question list has been reviewed prior and the ones not up to quality have been marked for you
to fix. Fix ONLY the flagged Questions below, using ONLY the new snippets provided
for the fix. Follow the critique to reevaluate the question and apply an appropriate fix.

Concept: {concept}
Flagged Questions (with the Verifier's critique and fix snippets):
{for each flagged index: index, current Question fields, critique, snippets}

Each flagged Question's existing source_quote is shown above for context
only — it is what the flag is critiquing, not a valid source for your
replacement. Do not reuse it in your output unless it also happens to
appear verbatim among that flag's fix snippets.

For each flagged index, output a full replacement Question block — all
fields, not just the changed ones — prefixed with the index it replaces:
- index: the global index (int) of the Question this block replaces — must
  be one of the indices you were given, and every given index must appear
  exactly once in your output
- question_text: a clear, self-contained question, as a quoted string
- options: exactly 4 answer choices, as a quoted-string list, e.g.
  ["Option A", "Option B", "Option C", "Option D"]
- correct_answers: 1-4 of the option positions (1-based) that are correct,
  as an int list, e.g. [1, 4]
- is_select_all: true or false — true if more than one option is intended
  as correct, or if "select all that apply" framing fits this content
  better than single-answer; false otherwise. Choose deliberately — not
  inferred from len(correct_answers).
- explanation: a quoted string explaining why the correct answer(s) are
  correct, using only the given snippets
- page_number: the page number (int) the grounding snippet came from
- source_quote: the exact snippet text (or relevant portion), as a quoted
  string, copied verbatim from that flag's fix snippets — NOT from the
  Question's pre-fix source_quote shown above for context

Do not touch Questions that weren't flagged — they are not in your input
and must not appear in your output.

Quality bar:
- Every fact used must trace to a provided fix snippet — never invent
  content, never use outside/general knowledge even if believed true, and
  never fall back to the pre-fix Question's own source_quote/explanation
- Distractors must be plausible — wrong in a way a student could realistically
  believe, not absurd or trivially eliminable, not duplicates of each other
  or the correct answer
- Don't bundle multiple distinct facts into a single option
- source_quote must be an exact substring of one of that flag's fix
  snippets — copying the pre-fix source_quote unchanged is only acceptable
  if it also appears verbatim among the fix snippets

Output format:
- Separate each Question's block from the next with at least 2 newlines
- Output nothing but the Question blocks — no preamble, no closing remarks
- Only output the fixed version of each Question — do not also output its pre-fix fields
- Wrap the entire output between --START-- and --END-- markers, exactly as
  shown in the example below

--START--
index: 5
question_text: "Which process describes liquid water turning into vapor?"
options: ["Evaporation", "Condensation", "Infiltration", "Runoff"]
correct_answers: [1]
is_select_all: false
explanation: "Evaporation is liquid water becoming vapor, driven by the sun's heat."
page_number: 1
source_quote: "Evaporation is the process by which liquid water changes into water vapor and rises into the atmosphere."

index: 8
question_text: "Which of the following are forms of precipitation?"
options: ["Rain", "Snow", "Evaporation", "Hail"]
correct_answers: [1, 2, 4]
is_select_all: true
explanation: "Rain, snow, and hail are precipitation forms; evaporation is a different process, not a form of it."
page_number: 3
source_quote: "Precipitation can take several forms depending on atmospheric temperature: rain, snow, sleet, or hail."
--END--

```
Python parses each block into its replacement `Question`, matched to the existing Question at that same global index — index is never reassigned.

**Verifier**
```
You are fact-checking and quality-checking Questions made by a student to review for an exam
against their Note's FULL text below. Ensure that the questions and their answers match the note,
and are comprehensive enough to be of quality for a review. You are only checking questions for
the particular concept provided, and provide critique. DO NOT CHANGE any of the question contents. 

Note text:
{full note text}

Questions to check (all belong to Concept: {concept}):
{for each: index (global), question_text, options, correct_answers,
  is_select_all, explanation, page_number, source_quote}

For EACH Question, output one block with these fields:
- index: the Question's global index (int), copied from its input — every
  index you were given must appear exactly once in your output
- action: "keep" or "patch" — "keep" if it fully passes the quality bar
  below, "patch" if it fails on any point
- critique: a quoted string explaining what's wrong, referencing the
  specific criterion — required when action is "patch", empty string ""
  when action is "keep"
- snippets: your own verbatim quotes + page numbers backing the requested
  fix, in the same ["quoted text" : N] format as the Analyzer — required
  when action is "patch", empty list [] when action is "keep"

Quality bar, checked against the Note (verbatim from Verify loop detail):
- Answer correctness is grounded in the Note (no fabricated facts)
- Distractors are plausible — not trivially wrong or duplicates of each other
- is_select_all matches the intended semantics (deliberate choice, not
  count-inferred). A Select-All Question (is_select_all: true) legitimately
  has anywhere from 1 to all 4 options correct — a single correct answer
  does NOT by itself mean is_select_all should be false. Only flag
  is_select_all if the question's own phrasing/framing doesn't fit its
  value (e.g. stem clearly invites a single choice but is_select_all is
  true, or stem clearly invites multiple selection but is_select_all is
  false) — never flag it purely because len(correct_answers) is 1
- No ambiguous or multiple-valid-reading phrasing
- explanation actually explains the correct answer using Note content
- Question actually matches its assigned concept
- source_quote is a real quote genuinely present on page_number and matches verbatim, and it
  actually supports correct_answers/explanation — not fabricated, vague, or
  contradicting page_number

Output format:
- Separate each Question's block from the next with at least 2 newlines
- Output nothing but the Question blocks, plus one trailing line
  (see below) — no preamble, no closing remarks
- Wrap the entire output between --START-- and --END-- markers
- After all Question blocks, add one line: satisfactory: true or
  satisfactory: false — true only if every Question in this call was "keep"

--START--
index: 3
action: "patch"
critique: "source_quote does not actually support correct_answers — the quote describes condensation, but the Question and explanation are about precipitation."
snippets: ["Precipitation is the primary way water returns from the atmosphere to the Earth's surface." : 2]

index: 4
action: "keep"
critique: ""
snippets: []

satisfactory: false
--END--

```
Python parses each block into a `VerifierIssue` (or a no-op for "keep") plus the trailing `satisfactory` line — not an SDK-level structured `output_type` (see Agents section above). Do not flag Questions outside your assigned index set. Every snippet you extract must be an exact substring of the Note text above.

## Expected behavior

Behavioral contracts for each agent's call — properties any valid output must have — plus one concrete worked example per agent, grounded in `water_cycle_note.txt`. Written for the `agent-testing` branch (isolated per-call testing before pipeline wiring); see `agent-test-log.md` for actual runs against these.

### Analyzer

**General contract:**
- Every `weight_percentage` sums to ~100 across Concepts in one call (drift beyond ±10 is a genuine Analyzer mistake, not rounding noise — see Weight reconciliation above).
- Concepts are non-overlapping — none re-describes another's topic.
- Every snippet is an exact (whitespace-normalized) substring of the given Note text — a fabricated or paraphrased quote is a contract violation regardless of whether it's factually true.
- A sparse Note (few distinct ideas) yields few Concepts — the Analyzer must not invent Concepts to pad coverage.
- Concepts collectively cover the Note's actual content spread — a multi-page Note shouldn't come back with every Concept's snippets drawn from only one page while other pages' content goes unrepresented.

**Worked example** — given `water_cycle_note.txt` (3 pages: evaporation/transpiration/runoff on Page 1, condensation/precipitation on Page 2, precipitation forms/infiltration/groundwater/collection on Page 3), a reasonable Analyzer output partitions into roughly 4-6 Concepts spanning all three pages — e.g. "Evaporation and Transpiration" (Page 1), "Condensation and Precipitation" (Page 2-3), "Runoff and Groundwater Storage" (Page 1, 3), "Collection" (Page 3). Concept boundaries/count can reasonably vary (this grouping vs. finer-grained per-process Concepts are both defensible); the contract is non-overlap plus full-Note coverage, not an exact concept count or wording match.

### Generator — initial pass

**General contract:**
- Output has exactly `question_count` Questions.
- Every `options` list has exactly 4 entries; `correct_answers` has 1-4 entries, each a valid option position.
- `source_quote` is an exact substring of one of the *given snippets* — never the full Note, since this call never sees it.
- No fact used traces outside the given snippets — outside/general knowledge is a contract violation even where it happens to be true.
- When `question_count` exceeds what the snippets can distinctly support, Questions vary in phrasing/format/tested detail rather than repeating near-identically or fabricating new facts to fill the count.

**Worked example** — given concept "Evaporation and Transpiration" and snippet `["The sun's heat provides the energy needed for evaporation, primarily from oceans, lakes, and rivers, which together account for the vast majority of water entering the atmosphere." : 1]`, a valid Question: `question_text: "What provides the energy needed for evaporation?"`, correct option "The sun's heat", `page_number: 1`, `source_quote` copied verbatim from that snippet (not paraphrased).

### Generator — patch pass

**General contract:**
- Output contains exactly the flagged indices, each exactly once — no extra Questions, none dropped, no untouched Question re-emitted.
- The critique is actually addressed by the new Question content — not just cosmetic rewording carrying the same flaw.
- `source_quote` in the patched Question is an exact substring of the *new fix snippets* provided for that flag — not the Question's original (possibly-flawed) `source_quote`.

**Worked example** — flagging a Question whose explanation only lists precipitation's forms without saying what determines which form occurs, given fix snippet `["Rain is the most common form of precipitation in warmer climates, while snow and sleet occur when temperatures near the ground are at or below freezing." : 3]`, the patched `explanation` should explain the temperature-dependence, not just restate the list of forms.

### Verifier

**General contract:**
- Every given index appears in the output exactly once.
- `action: "patch"` requires non-empty `critique` and non-empty `snippets`; `action: "keep"` requires `critique: ""` and `snippets: []`.
- `satisfactory: true` iff every Question in the call was `"keep"`.
- A Question gets `action: "patch"` if any of: `source_quote` isn't a real, verbatim, on-`page_number` quote; the quote doesn't actually support `correct_answers`/`explanation`; distractors are implausible or near-duplicates of each other; `is_select_all` doesn't match what the grounding actually supports; phrasing admits more than one valid reading; or `concept` doesn't match the Question's actual topic.
- A Question passing all of the above gets `action: "keep"`, even if a different, equally-valid Question could have been written instead — the Verifier judges the given Question as written, not whether it's the best possible Question for that Concept.

**Worked example** — given Note text including `"The sun's heat provides the energy needed for evaporation, primarily from oceans, lakes, and rivers..." (Page 1)` and a Question claiming `source_quote: "NASA satellite data confirms 90 percent of atmospheric moisture originates from ocean evaporation."`, expect `action: "patch"` with a critique naming the fabricated quote — that sentence never appears in the Note (see `agent-test-log.md`'s `verifier-evaporation-mixed` case).

## Data model

All models are Pydantic, with validators enforcing fixed sizes where the domain requires them — Python has no native fixed-length string/int array, so "fixed size" here means validated-fixed, not a literal fixed-capacity container.

```python
class ConceptSnippet(BaseModel):
    quote: str                        # verbatim substring of the Note, character-for-character
    page_number: int                  # page this quote appears on

class ConceptAllocation(BaseModel):
    concept: str
    weight_percentage: float          # all ConceptAllocations in a set sum to 100
    question_count: int
    snippets: list[ConceptSnippet]    # 1+; the Generator's initial pass sees only these,
                                       # not the full Note — see Snippet grounding above

class Question(BaseModel):
    concept: str                      # matches a ConceptAllocation.concept; quick topic label
    question_text: str
    options: list[str]                # validated: exactly 4 entries
    correct_answers: list[int]        # validated: 1-4 entries, each value in {1,2,3,4}
                                       # e.g. [1, 4] = options 1 and 4 are correct
    is_select_all: bool               # False = Multiple-Choice (radio), True = Select-All (checkbox)
    explanation: str                  # grounded in Note content
    page_number: int                  # page in the Note this Question is drawn from;
                                       # future: button to jump to/highlight that page in Note view
    source_quote: str                 # verbatim Note text grounding this specific Question;
                                       # not surfaced in v1's UI yet, but stored for a future
                                       # citation display — see Snippet grounding above

class QuestionSet(BaseModel):
    questions: list[Question]         # length locked at the user-confirmed total question_count
                                       # before Generator's initial pass; never resized after
```

`is_select_all` is stored explicitly rather than inferred from `len(correct_answers)`, since a Select-All Question can legitimately have only one correct option — the count alone can't distinguish it from Multiple-Choice.

`questions` is the same fixed-length list from Generator's initial pass through the entire verify loop to the final `QuestionSet` — array index is the Question's identity throughout, no ids, no dict, no index-shifting to account for. This only works because the loop has exactly one action available (`patch`, always same-index) — see Verify Loop Detail below for why `remove`/`split` were deliberately dropped from the design to preserve this.

Note text itself: a plain `str`, extracted from the PDF once at upload, held in memory — never re-extracted mid-pipeline. Passed as input only to the Analyzer (once) and the Verifier (every concurrent per-concept call, every round — see Snippet grounding above); every Generator call, initial or patch, receives snippets instead.

### Room data model

Extends the models above for the v2 Room mode — `RoomState.question_set` is a plain `QuestionSet` (see above), same model, same fixed shape, sourced from a fixed, hand-written `QuestionSet` (the Room fixture — see Room pipeline below), shuffled per-Room at creation.

```python
class PlayerState(BaseModel):
    player_id: str
    nickname: str              # auto-suffixed on collision at join time
    score: int = 0
    connected: bool = True     # false once mid-game disconnect occurs;
                                # Player stays in roster/leaderboard either way

class RoomState(BaseModel):
    pin: str                   # 4-digit, zero-padded string (e.g. "0042"), not an int
    host_session_id: str       # matches the Host's existing v1 session cookie
    question_set: QuestionSet  # per-Room shuffled copy of the fixture (Fisher-Yates,
                                # see Room pipeline); source fixture itself never mutated
    status: Literal["lobby", "question_active", "answer_reveal", "leaderboard", "finished"]
    current_round: int = 0     # 0-indexed into question_set.questions
    question_start_time: float | None = None   # server clock, set on question_start broadcast
    players: dict[str, PlayerState]             # keyed by player_id
    answers: dict[str, Answer]                  # keyed by player_id, cleared each round
    terminal_reason: Literal["natural_end", "host_ended", "host_disconnected"] | None = None
    terminal_at: float | None = None            # set when status becomes "finished"; TTL sweep basis
    created_at: float          # server clock, set on Room creation; TTL basis for abandoned
                                # Lobbies (Room never left LOBBY) — see Room cleanup below

class Answer(BaseModel):
    player_id: str
    selected: list[int]        # option positions, 1-based — length 1 for Multiple-Choice
    elapsed: float              # server-measured, seconds
    correct: bool
    points: int
```

`RoomState` instances live in a PIN-keyed dict, in-memory, single-process — same "nested hashmap" pattern `requirements.md` already calls out for Game Room, carried over from v1's `SessionStore` decision. Many-Rooms-capable (no architectural cap on the dict itself), even though real usage tops out around 3 concurrent Rooms.

**Vercel note**: Fluid Compute reuses function instances across concurrent requests but doesn't guarantee a single instance under load — this design accepts that risk and pins the deployment to effectively single-instance (capped max concurrency) rather than moving Room state to an external store (e.g. Redis). Revisit only if real usage ever exceeds what a single instance can hold — not expected at this project's scale.

## Verify loop detail

**Verifier criteria**, checked per Question against the Note text:

- Answer correctness is grounded in the Note (no fabricated facts)
- Distractors are plausible — not trivially wrong or duplicates of each other
- `is_select_all` matches the intended semantics (deliberate choice, not count-inferred). A Select-All Question (`is_select_all: true`) legitimately has anywhere from 1 to all 4 options correct — a single correct answer does NOT by itself mean `is_select_all` should be `false`. Only flag `is_select_all` if the question's own phrasing/framing doesn't fit its value — never flag it purely because `len(correct_answers)` is 1
- No ambiguous or multiple-valid-reading phrasing
- `explanation` actually explains the correct answer using Note content
- Question actually matches its assigned `concept`
- `source_quote` is a real quote genuinely present on `page_number`, and it actually supports `correct_answers`/`explanation` — not fabricated, vague, or contradicting `page_number` (this check has real teeth against fabrication: `source_quote` is also verified deterministically as a verbatim substring wherever it's produced, but *whether it actually supports the answer* is a judgment call only the Verifier can make)

Every flagged issue also carries its own `snippets` (verbatim Note quotes + page numbers backing the requested fix) — the Verifier extracts these itself, since it's the only agent reading the full Note; the patch call that acts on the feedback never sees the Note, only these (see Snippet grounding above).

**Per-Question action** the Verifier can return: `keep` or `patch`. There is deliberately no `remove` or `split` — the Question list's length is locked at the user-confirmed total (see Generation pipeline above), so any action that changes list length is out of scope for the verify loop:

- A Question judged unnecessary/redundant isn't deleted — Generator patches that index into a *different* Question (same `concept`, fresh angle), achieving the same practical outcome without touching list length.
- A Question judged as trying to cover too much isn't split into two — Generator patches it into one tighter, more focused Question instead. If a concept genuinely needs more coverage than one Question can give it, that's fixed earlier, at the Analyzer checkpoint (user raises that concept's `question_count` before confirming) — not something the post-hoc verify loop tries to solve by resizing.

**Satisfactory** is `true` only when zero Questions in the current list are flagged with an issue. `false` triggers another loop iteration (if under the 5-iteration cap).

**Loop count**: the initial Generator pass is unlooped ("pass 0") but fans out to one concurrent call per concept (see Concurrent generation above), not one call total. Up to 5 Verifier→patch cycles follow; the cycles themselves are sequential (each round needs the previous round's result), but within a round BOTH the Verifier step and the patch step fan out concurrently, one call per concept (Verifier: every concept present; patch: only concepts among that round's flagged indices). Worst case: N concurrent initial calls + 5 rounds of (up to N concurrent Verifier calls + up to N concurrent patch calls), where N = concept count, not counting the single Analyzer call.

## API contract

FastAPI backend, session identified via HTTP-only cookie (set on first `/upload`), keyed into the in-memory `SessionStore` (lock-guarded nested hashmap).

### `POST /upload`
- Request: `multipart/form-data` — `file` (PDF), optional `target_question_count: int`
- Response `200`: `{ concepts: list[ConceptAllocation] }` — Analyzer's pre-checkpoint output. Sets session cookie.
- Errors `400`: `not_a_pdf` / `file_too_large` / `no_extractable_text` (per `requirements.md` Error handling) — Analyzer never runs on these.

### `POST /generate`
- Request: `{ allocations: list[ConceptAllocation] }` — the full user-confirmed (possibly edited) checkpoint allocation, weights re-summed to 100, sent whole (per `CONTEXT.md`'s client-side-edit direction).
- Response: **SSE stream**. Each event: `{ stage: "generator_initial" | "verify_round" | "patch" | "done" | "error", concept?: str, round?: int }`; terminal `done` event carries the full `QuestionSet`. `error` event carries the generic failure message from `requirements.md`.
- Locks `question_count` total server-side on receipt — matches the Analyzer-checkpoint acceptance criteria.

### `POST /generate/retry`
- Request: empty body — reuses the already-uploaded Note held server-side under the session cookie.
- Response: same SSE shape as `/generate`.
- Precondition: session has an uploaded Note and no successful `QuestionSet` (last run failed).

### `PATCH /questions/{index}`
- Request: partial `Question` fields (`question_text`, `options`, `correct_answers`, `is_select_all`, `explanation`, `page_number`).
- Response `200`: the updated `Question`.
- Errors `404`: no active `QuestionSet` for this session, or `index` out of range. Never resizes the list (see Editing).

### `PATCH /concepts/{old_name}`
- Request: `{ new_name: str }`
- Response `200`: `{ concept: str, updated_count: int }` — the new label plus how many Questions were affected.
- Errors: `404` if `old_name` doesn't match any Question's `concept` in the session's `QuestionSet`; `409` if `new_name` already matches a different existing concept (rename is blocked, not merged — see Editing's Concept editing). Once a real backend exists, Rename fires this as a second, conditional request rather than folding into the `PATCH /questions/{index}` call.

### `GET /session`
Lets the frontend rehydrate on page load without re-uploading — needed for `requirements.md`'s persistence acceptance criteria (closing/reopening the browser mid-server-run must still show existing state).
- Response `200`: `{ status: "empty" | "checkpoint_pending" | "generating" | "ready" | "failed", allocations?: list[ConceptAllocation], questions?: list[Question] }` — `allocations` present for `checkpoint_pending`, `questions` present for `ready`.

### `POST /rooms`
- Request: empty body — every Room is created from the one fixed `QuestionSet` fixture (see Room pipeline below).
- Auth: Host's existing session cookie
- Response `200`: `{ pin: str }`
- Sets `RoomState.host_session_id` from the session cookie

### `POST /rooms/{pin}/join`
- Request: `{ nickname: str }`
- Response `200`: `{ player_id: str, nickname: str }` (nickname echoed back, possibly auto-suffixed)
- Errors: `404 room_not_found`, `409 room_full`, `409 already_started`

### `GET /rooms/{pin}` (optional, for a Player's join-page pre-check before showing the nickname form)
- Response `200`: `{ status: "lobby" | "in_progress" | "finished", player_count: int }` — collapses `RoomState.status`'s 5 internal values down to what a pre-join Player actually needs: `in_progress` covers `question_active`, `answer_reveal`, and `leaderboard` alike (all equally mean "too late to join")
- Errors: `404 room_not_found`
- Used exactly for this purpose by the frontend's `/join/:pin` join page (see Room join flow's Join-page pre-check above).

### `WS /ws/room/{pin}`
- Host: authenticated via session cookie, must match `RoomState.host_session_id`
- Player: `?player_id=...` query param, must match an existing `PlayerState` on this Room
- See Room WebSocket message protocol below for the message shapes exchanged after connect

## Flashcard display (this phase)

Minimal linear view to prove the pipeline works end-to-end — **not** the real Review Session. This phase is also proven against a hand-written fixture instead of a live pipeline run (see Test fixture below).

### Test fixture

Since this phase builds/tests the flashcard view itself, not the generation pipeline, its `QuestionSet` comes from a hand-written JSON fixture, not a live Analyzer/Generator/Verifier run:

- Fixture JSON mirrors the `QuestionSet`/`Question` Pydantic models exactly (same field names, same shapes) — validated by loading it through those same models before use, catching hand-typing mistakes (missing field, wrong option count, etc.) rather than trusting manual review alone.
- Loaded directly by the frontend (plain import), no mock server/endpoint involved — API integration is separate, later work.
- Content grounded in `water_cycle_note.txt` (already in repo). Covers every rendering/edit case the view needs to prove: ~6-8 Questions, mixing a standard Multiple-Choice, a Select-All with 2-3 correct, a Select-All with all 4 correct, a Select-All edge case with only 1 correct (checkbox control despite the single-answer count), 2-3 distinct `concept` values, varying `page_number`s, and at least one Question with longer `question_text`/`explanation` to test wrap/overflow.
- Edits made against this fixture (see Editing below) only mutate local frontend state — nothing persists past a reload until a real backend exists.

### Card mechanics

Applies to the flashcard display's default (browse) view — the Review Session (below) reuses the same `QuestionSet` and card visual language but has its own, graded interaction rules.

- Iterates `QuestionSet.questions` in array index order (generation/freeze order); Next/Prev buttons move between cards — Prev is allowed here (unlike the Review Session, which is forward-only per `requirements.md`), since this view is a display/editing tool, not a graded pass.
- A "Card X of N" position indicator is shown alongside Next/Prev.
- Each card flips between front and back on click/tap; navigating to a different card (Next/Prev) always resets that card to its front — never lands mid-flip.
- Front side: `question_text` + all 4 `options`, rendered with radio controls (Multiple-Choice) or checkboxes (Select-All) per `is_select_all` — visually distinct per `requirements.md`'s rule, but inert: no selection/scoring here. (The Review Session's front is the one place selection is live — see below.)
- Back side: `question_text`, all 4 `options` repeated (same radio/checkbox rendering as front) with the correct one(s) visually marked, `explanation`, `page_number`, and `concept` (trimmed for display — see below).
- **Concept trim rule**: split the `concept` string on its first `:`, `—`, `-`, or `,` (whichever occurs first) and display only the clause before it (e.g. "Blood Vessels: structure, operations and significance" → "Blood Vessels"). If no delimiter is present, display the full untrimmed string — no fallback character cap. Trimming is display-only; the full `concept` string is always what's stored and what any edit (see Editing below) operates on.
- No shuffling, no scoring, no Summary screen in this view — those belong to the Review Session below, reusing this same `QuestionSet`.

### Review Session

Reachable via a "Start Review" button beneath the browse view's Next/Prev row. Reuses the same `QuestionSet` and the browse view's card visual language (theme, flip animation, option-mark shapes), with `requirements.md`'s Review Session rules:

- Question order is shuffled on entry (Fisher–Yates), independent of the browse view's fixed array order.
- Forward-only: no Prev. Next is disabled until the current card is submitted.
- Front side options are live: `is_select_all: false` renders as a radio group (one selectable option), `true` as independent checkboxes — real (visually-hidden) `<input>` elements under the existing `.optMark` styling, not inert.
- A Submit button is disabled until at least one option is selected. Submitting flips the card to the back and locks it — no changing the selection or flipping back afterward. This is this build's concrete mechanism for `requirements.md`'s "after answering each Question, the user immediately sees correct/incorrect plus the Question's explanation."
- Back side marks each option by combined correctness + selection state: correct & selected (filled), correct & not selected (outline only), incorrect & selected (filled, distinct color), not-correct & not selected (neutral, unmarked) — on top of the existing explanation/page_number/concept display. No Edit button here — editing (see below) is browse-view-only; a Review Session card is not editable.
- After the last card is submitted, the Summary screen shows the score (X/Y correct) and the list of missed questions with their explanations, plus a way to restart: a fresh Review Session on the same `QuestionSet`, reshuffled, independent of the previous pass's score — no score history kept across passes, per `requirements.md`.



## Editing

From the flashcard display's browse view, at any time after generation, the user can edit a Question's fields in place. Not available in a Review Session — its cards carry no Edit button (see Review Session above). No adding or removing Questions from the set via the UI in v1 — the array stays the size it was frozen at. (This pulls "manual editing" forward from `requirements.md`'s v1.x-deferred list into v1 scope — see that file's changelog.)

### Entry & save

- An "Edit" button lives on the back of the card only (front stays a clean question view; every editable field is already visible on the back). Editing is inline — fields on the card itself become inputs, no modal/overlay.
- A single "Save" button commits every field changed during that edit session in one action; "Cancel" discards in-progress edits and reverts the card to its last-saved values. (No per-field autosave — fields like `is_select_all` and `correct_answers` need to land together, not independently, to stay valid.) Save is always clickable, never pre-emptively disabled — clicking validates and shows inline field errors (options non-empty, `correct_answers` count vs `is_select_all`, `page_number`, concept collision) while keeping the draft open on failure, rather than gating the button on live validity.
- This phase has no real backend: Save mutates local frontend state only (matching the shape of the API calls below, but not actually calling them) — edits are lost on reload until a real backend exists.
- Whole-card flip-to-front and the browse view's Next/Prev/Start Review controls are all disabled while a card is mid-edit, so navigating or flipping away can't silently discard an in-progress draft.
- Frontend structure: `QuestionSet` lives in App-level state as the single source of truth; a `QuestionEditForm` component holds its own draft state (cloned from the `Question` on Edit, discarded on Cancel) and reports a finished edit upward via one `onSave(updated, renameFrom?)` callback.

### Editable fields & validation

- `question_text`, `explanation`: free text.
- `options`: always exactly 4 slots (no add/remove option), each must be non-empty.
- `correct_answers`: exactly 1 marked correct when `is_select_all` is false (radio, even in edit mode); 1-4 marked correct when true (checkboxes).
- `is_select_all`: togglable; if toggling would leave the current `correct_answers` count invalid for the new value (e.g. 3 marked correct, toggling to Multiple-Choice), Save is blocked with an inline error until the user manually fixes the selection — no auto-correction. Edited via an explicit two-option Multiple-Choice/Select-All toggle, not a single ambiguous checkbox.
- `page_number`: positive integer (>=1); inline error otherwise.
- `concept`: editable via two separate controls (see below). `source_quote` is never editable (not surfaced in v1 UI at all — see Snippet grounding).

### Concept editing

`concept` is a plain string tag on each Question (no separate Concept entity survives past Freeze — see Data model), so two different edits are possible:

- **Rename** — a text field showing the current label. Saving a change renames it everywhere: every Question in the Set currently tagged with the old string is updated to the new string. Blocked (error, not merge) if the new name collides with a different concept string already present elsewhere in the Set — renaming and reassigning are different intents, and a same-name collision should not silently merge two concepts.
- **Reassign** — a dropdown listing the other distinct `concept` values currently present in the Set (derived by scanning `QuestionSet.questions` for unique `concept` strings, excluding the current one). Picking one moves only this single Question to that existing concept; other Questions are unaffected. Disabled when no other concept exists in the Set.
- Rename and Reassign are mutually exclusive within one edit session — editing one clears the other's pending value (last-touched wins), since a Question's `concept` can only end up one way per Save.

## Room pipeline

The Room mode's end-to-end flow, mirroring the style of the Generation pipeline diagram above — from Room creation through cleanup. Entered directly from a fixed, hand-written `QuestionSet` fixture — independent of the v1 upload/Analyzer/Generator/Verifier pipeline; Room mode doesn't depend on a generated Question Set to run.

The entry point is a "Create Room" button on the flashcard browse view (next to "Start Review"). The button sits alongside that view's own (separate) fixture content, but `POST /rooms` always creates the Room from the backend's own fixed `QuestionSet` fixture — the two are intentionally unrelated Question Sets; Room mode's content isn't tied to whatever Question Set the browse view happens to be showing.

```
Host has a QuestionSet (this phase: one hardcoded fixture, not the real pipeline)
   |
   v
POST /rooms  (Host, authenticated via existing session cookie)
   - generates a unique 4-digit PIN (random, retried on collision against
     currently active Rooms)
   - shuffles the fixture's Questions (Fisher-Yates, same approach as the
     Review Session) into this Room's own question_set.questions order —
     per requirements.md's "Questions cycle in random order during the
     game"; the source fixture itself is never mutated, so a fresh shuffle
     is drawn per Room, not shared across Rooms
   - creates RoomState in the PIN-keyed in-memory store, status = LOBBY
   - Host's WS connects: /ws/room/{pin}  (role = host, matched via session
     cookie against RoomState.host_session_id)
   |
   v
LOBBY
   - frontend renders the PIN + a client-generated QR code (encodes
     {origin}/join/{pin}) for Host to display/share
   - Players join independently (see Room join flow below), each appearing
     in Host's live roster as they connect
   - Host starts whenever ready, no minimum Player count (per requirements.md)
   |
   v  (Host clicks "Start Game")
QUESTION_ACTIVE  (round 1..N, N = fixture's QuestionSet length)
   - join window closes — no further joins accepted (see Room join flow)
   - server broadcasts question_start to Host + every connected Player:
     full Question fields EXCEPT correct_answers/explanation (withheld
     until reveal), plus server's own broadcast timestamp
   - server starts its own 30s authoritative timer for this question
   - Players answer (see Room answer submission below); Host sees a live
     answered-count and a countdown timer (cosmetic, client-computed from
     receipt time — see Room answer submission), not individual answers
   - phase ends when either every connected, not-yet-disconnected Player
     has submitted, or the 30s server timer expires — whichever first
   |
   v
ANSWER_REVEAL
   - server broadcasts answer_reveal: correct_answers, explanation, and
     each connected client's own result (correct/incorrect, points earned)
   - per-Player score updated server-side (see Room scoring below)
   - Room stays in ANSWER_REVEAL until Host advances (see below) — Host
     sees a distinct reveal view (own screen, not merged into Leaderboard),
     mirroring the Player's reveal view; both wait here until Host acts
   |
   v  (Host clicks "Show Leaderboard" — sends `advance`)
LEADERBOARD
   - server broadcasts leaderboard: ranked Player list (nickname, running
     total score, rank) — tied scores share the same rank (standard/skip
     ranking, see Room scoring below)
   - Host sees "Next Question" (or "Finish" if this was the last Question,
     in which case "End Game" is hidden — Finish alone covers it) and
     "End Game" (only when not the last round), both host-triggered — no
     auto-advance
   |
   +--> Host clicks "Next Question" --> back to QUESTION_ACTIVE (round+1)
   |
   +--> Host clicks "End Game" (early, before last Question) --> FINISHED
   |
   +--> (round == N, was already the last Question) --> FINISHED
   |
   v
FINISHED
   - server broadcasts game_over: final leaderboard, built from whichever
     Questions were actually played (full set on natural end, partial on
     early End Game — same message shape either way)
   - RoomState marked terminal; 5-minute TTL starts (see Room cleanup below)
   - WS connections stay open (so the final leaderboard remains visible)
     until the client navigates away or the TTL sweep evicts the Room
   |
   v
(5 min later, or immediately on Host WS close before FINISHED)
CLEANUP
   - periodic sweep evicts any Room whose TTL has elapsed from the
     PIN-keyed store — PIN becomes reusable
```

**Frontend routing**: `/host/:pin` (Host) and `/play/:pin?player_id=...` (Player) are each a single route whose screen swaps panels by `RoomState.status`, delivered live over the WebSocket — not separate routes per phase, since phase transitions are server-driven, not navigation events. The Host's screen collapses ANSWER_REVEAL directly into its LEADERBOARD-phase panel (both broadcasts land back-to-back with no Host action between); the wire protocol itself is unchanged, this only affects what the Host's screen renders. `/join/:pin` pre-fills the PIN from the URL (see Room join flow below); a separate `/join` route (no PIN param) renders a manual PIN-entry form instead, reached via a "Join Room" button on the home page (`/`) next to "Create Room" — submitting navigates to `/join/:pin`, re-entering the same precheck flow. The Lobby's QR code is generated client-side via the `qrcode.react` library, no network call.

**Host-disconnect short-circuit**: at any point after LOBBY, if the Host's WS closes (not a graceful "End Game," an actual connection loss/close), the Room transitions straight to FINISHED with a `host_disconnected` reason, broadcasting the same `game_over` shape (partial results, as of whatever was last completed) to remaining Players, then follows the same 5-minute TTL cleanup. No grace period — matches `requirements.md`'s "Room ends immediately for everyone" exactly as worded.

## Room states

```
LOBBY --(Host starts)--> QUESTION_ACTIVE --(all answered / timeout)--> ANSWER_REVEAL --(Host: advance)--> LEADERBOARD
                              ^                                                              |
                              |______________(Host: Next Question, round < N)________________|

LEADERBOARD --(Host: Next Question, round == N)--> FINISHED
LEADERBOARD --(Host: End Game, any round)--------> FINISHED
LOBBY / QUESTION_ACTIVE / ANSWER_REVEAL / LEADERBOARD --(Host WS closes)--> FINISHED (host_disconnected)
FINISHED --(5 min TTL)--> evicted from store
```

## Room join flow

```
Player has: {origin}/join/{pin}  (typed manually, or via QR scan — same URL either way)
   |
   v
Join page pre-fills PIN from the URL param; Player enters a nickname
   |
   v
POST /rooms/{pin}/join  { nickname }
   - 404 room_not_found     — PIN doesn't match any active Room
   - 409 room_full          — already at 10 Players
   - 409 already_started    — Room is past LOBBY (join window closed)
   - 200 { player_id, ... } — nickname auto-suffixed ("(1)", "(2)", ...)
     if it collides with an existing Player in this Room; player_id is
     scoped to this Room only, not reused across Rooms
   |
   v
WS connects: /ws/room/{pin}?player_id={player_id}  (role = player)
   - server validates player_id belongs to an active Player record on
     this Room before accepting the connection
   |
   v
Player appears live in Host's LOBBY roster
```

**Lobby-phase disconnect**: if a Player's WS closes while the Room is still in LOBBY, they're removed from the roster immediately (frees their nickname/slot). Reconnecting is just a fresh `POST /rooms/{pin}/join` — server doesn't need to remember they were ever there. This only applies pre-game; once QUESTION_ACTIVE starts, disconnect is terminal for that Player (per `requirements.md` — not removed, but cannot rejoin, score frozen wherever it stood).

**Join-page pre-check**: before showing the nickname form, the Player's `/join/:pin` page calls `GET /rooms/{pin}` (see API contract below) — a `room_not_found` response, `status: "finished"`, `status: "in_progress"` (join window already closed), or `status: "lobby"` with `player_count` already at the 10-Player cap all skip straight to an error screen instead of showing the form. `POST /rooms/{pin}/join`'s own 404/409 responses remain the authoritative check (e.g. a Room that fills in the gap between this pre-check and the actual join submission) — the pre-check only improves the common case.

**Duplicate connection (same `player_id`)**: if a second WS connects with a `player_id` that already has a live connection, the server closes the old socket (server-initiated close) before registering the new one — the old client sees a normal `connection_closed` and can no longer act; the new connection becomes the sole live one for that Player.

## Room answer submission

Two shapes, chosen by `Question.is_select_all`, both ending in the same one-shot lock:

- **Multiple-Choice** (`is_select_all: false`): tapping any option immediately sends the answer message — no separate Submit step.
- **Select-All** (`is_select_all: true`): tapping toggles local selection state only (no message sent per tap); an explicit Submit button (enabled once ≥1 option is selected) sends the final selected set as one answer message.

Either way, the answer message is one-shot: the first answer message the server accepts for a given Player+Question is final. Any further answer message for that same Question from that Player is rejected (already answered).

**Timing**: server records `question_start_time` the instant it broadcasts `question_start`. When an answer message arrives, server computes `elapsed = arrival_time - question_start_time` using its own clock only — the message carries no client-reported timing field at all, so there's nothing for a client to lie about. `elapsed` is clamped to the 30s window; anything arriving after the server's own cutoff is rejected as late (treated as a timeout, scores 0). Client-side countdowns are purely cosmetic UI, not consulted for scoring. Host's countdown UI uses its own message-receipt timestamp as t0, not `server_time` directly — `server_time` is a server-process-relative monotonic value, not epoch time, so it isn't diffable against a client's wall clock.

Each Player's own device renders the full question (text + all 4 options) directly — self-contained, not a shared-screen model — matching Players joining from different devices and different networks, per this project's Room mode goal.

## Room scoring

- **Multiple-Choice**: correct iff the selected option matches the single entry in `correct_answers`.
- **Select-All**: correct iff the selected set exactly equals the `correct_answers` set — no partial credit for a subset/superset match.
- **Points**: on a correct answer, `elapsed` (server-measured, see Room answer submission above) maps to the existing bracket table from `requirements.md`: 0-5s=100, 5-10s=95, 10-15s=90, 15-20s=85, 20-25s=80, 25-30s=75. Incorrect answers and timeouts score 0, per `requirements.md`.
- Running total accumulates across the Room's lifetime (not reset per question); shown on every `leaderboard` broadcast.
- **Ranking**: standard competition ranking ("1224") — Players with equal score share the same rank (e.g. two Players tied at 2nd both show rank 2), and the next distinct score skips ahead accordingly (next Player is rank 4, not 3). No tie-break needed, so nothing extra is tracked per Player to break ties — `score` alone determines rank.

## Room cleanup

Periodic sweep (e.g. every 30s) evicts any `RoomState` where `terminal_at` is set and `now - terminal_at > 300` (5 minutes). Applies uniformly to all three terminal paths (natural end, Host-triggered End Game, Host-disconnect) — same TTL, same sweep, no special-casing per reason. Abandoned lobbies (Room created, Host never starts) use the same TTL mechanism, measured from `RoomState` creation time instead of a terminal-state transition — treat "never left LOBBY" past the TTL as its own implicit terminal case.

## Room WebSocket message protocol

Single endpoint per Room (`/ws/room/{pin}`), one connection per client (Host or Player), envelope shape mirrors this doc's existing SSE event style (used in `/generate`'s response, see API contract):

**Server → client** (broadcast to everyone in the Room, unless noted):
- `player_joined` — `{ player_id, nickname }` (lobby roster update)
- `player_left` — `{ player_id }` (lobby-phase disconnect only, per Room join flow above)
- `question_start` — `{ round, total_rounds, question_text, options, is_select_all, page_number, concept, server_time }` — no `correct_answers`/`explanation`
- `answered_count` — `{ answered, total_connected }` (progress ping during QUESTION_ACTIVE, Host-facing mainly but harmless to broadcast to all)
- `answer_reveal` — `{ round, correct_answers, explanation, results: { [player_id]: { correct, points } } }`
- `leaderboard` — `{ round, total_rounds, standings: [{ player_id, nickname, score, rank }], is_final: bool }` — `rank` computed server-side (standard/skip ranking, see Room scoring), not derived client-side from array order
- `game_over` — `{ reason: "natural_end" | "host_ended" | "host_disconnected", final_standings: [...] }`
- `error` — `{ code, message }` (e.g. rejected late/duplicate answer)

**Client → server**:
- `submit_answer` — `{ round, selected: list[int] }` (Player only; Multiple-Choice sends on first tap, Select-All sends on explicit Submit)
- `advance` — `{}` (Host only; means "Start Game" from LOBBY, "Show Leaderboard" from ANSWER_REVEAL, "Next Question" from LEADERBOARD when round < N)
- `end_game` — `{}` (Host only; valid from any LEADERBOARD, including the final one)

Server validates every client→server message against the sender's role (Player messages rejected if sent by Host's connection and vice versa) and current `RoomState.status` (e.g. `submit_answer` rejected outside QUESTION_ACTIVE) before acting on it.

**Frontend handling notes**: the frontend consumes this protocol through one hook per connection (`useRoomSocket`), a reducer keyed on each message's `type` field. `error` is modeled client-side per the shape above, but nothing in the current backend implementation (`rooms_ws.py`) ever sends it — every invalid `submit_answer` (wrong status, already answered, wrong round, late arrival) is currently a silent no-op server-side, not a broadcast `error`; a rejected submission today just has no visible effect client-side. The frontend does not attempt to reconnect a dropped WS connection, for either role, at any phase — a client-side build-simplicity choice, distinct from and broader than this doc's Room join flow / `requirements.md`'s narrower rule that a Player who disconnects mid-game specifically cannot rejoin. WS close codes (`4403` cookie mismatch, `4404` room not found) aren't distinguished from an ordinary network drop in the client UI — both show the same generic disconnected state.

## Room mode — deferred / out of scope

- **Multiple selectable prewritten fixtures**: explicitly not building this — one fixture only, permanently within Room mode's scope.
- **External shared state store** (Redis/etc.): only revisit if single-instance in-memory state actually proves insufficient in practice.
- **Partial credit for Select-All scoring**: explicitly decided against (all-or-nothing) — would need its own formula if ever revisited.
- **Reload/resume mid-game**: a Host or Player reloading while the Room is still `lobby`/`question_active`/`answer_reveal`/`leaderboard` gets a fresh client with no resume — only an already-`finished`/evicted Room is detected and shown gracefully (see Room join flow's precheck pattern, now also used by Host). True mid-game resume is not built.
- **WS auto-reconnect**: the frontend does not retry a dropped connection (see Room WebSocket message protocol's Frontend handling notes above).
