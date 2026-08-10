# Design — Note Review (v1)

Structure and architecture for the generation pipeline: turning an uploaded Note (PDF) into a Question Set, and displaying that Question Set for review. See `CONTEXT.md` for canonical terminology and `requirements.md` for functional scope. This doc covers *how* generation works internally and the concrete data model, which `requirements.md` intentionally leaves at the behavioral level.

Out of scope for this doc: the Kahoot-style Room/live-game mode, deferred to later work per `requirements.md`. This phase covers generation, a minimal linear flashcard display used to verify the pipeline end-to-end, and the real Review Session (shuffled order, strictly forward-only, per-question immediate feedback, ends in a Summary screen — see `requirements.md`'s Review Session acceptance criteria) reachable via a "Start Review" button on that flashcard display. (This pulls the Review Session forward from originally-deferred "later work" into this phase's scope — same pattern as Editing below.)

## Pipeline

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

Text extraction (`pypdf`) runs once per upload, producing the single cached string every downstream call works from (see Pipeline). Pages are extracted one at a time and joined with an explicit page heading, so every agent reading Note text can attribute a quote to the page it came from — this is what the Analyzer's and Verifier's snippet `page_number` fields ultimately trace back to.

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
| Room Players | 10 | v2, not built | Per `requirements.md` |

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

**Provider**: the `openai-agents` framework itself is unchanged, but model calls run against [Groq](https://groq.com)'s free OpenAI-compatible API (`https://api.groq.com/openai/v1`) instead of OpenAI's own billed models — wired via `set_default_openai_client()` + `set_default_openai_api("chat_completions")` + `set_tracing_disabled(True)`. **Flagged, not yet re-verified**: the NIM wiring needed each `Agent`'s `model=` wrapped in `OpenAIChatCompletionsModel` because NIM's `vendor/model` slugs contain a `/` the SDK misparsed as a `litellm/`-style provider prefix. Groq's slugs (e.g. `gpt-oss-120b`) have no `/`, so that specific wrapping is likely unnecessary — still unconfirmed against a live Agents-SDK call (a raw HTTP call to Groq's endpoint was confirmed working during this doc's rework, see Model below, but that doesn't exercise the SDK's own model-string parsing).

**Model**: `gpt-oss-120b`, replacing `deepseek-r1-distill-llama-70b` — confirmed via a live dummy call during this doc's rework that Groq has decommissioned `deepseek-r1-distill-llama-70b` (HTTP 400, `model_decommissioned`); it's no longer usable regardless of provider preference. `gpt-oss-120b` is itself a reasoning model (OpenAI's open-weight release, harmony response format with a separate reasoning/analysis channel) — the same chain-of-thought-vs-structured-`output_type` concern flagged for the old model still applies, just not yet re-tested against this specific model/format. Prior empirical findings (call speed, `correct_answers` handling, the bundled-multiple-facts-in-one-option flaw) were measured against `deepseek-v4-pro` on NIM and don't carry over to `gpt-oss-120b` either. Not tracked as active work — flagged for whenever it becomes relevant.

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
snippets: ["Arteries: Strong, thick-walled muscular vessels that carry blood away from the heart. They mostly transport oxygen-rich blood under high pressure." : 2],
	  ["Arterioles: Smaller, flexible branches of arteries that regulate blood pressure as they lead into tissues" : 3]

concept: "Bone types"
weight_percentage: 29.67
snippets: ["Long bones: Hard, cylindrical shafts that are longer than they are wide. They act as levers to help you move. Examples include the femur (thigh bone) and humerus (upper arm)" : 2],
	  ["Flat bones: Thin, broad, and often curved plates that protect vital organs and offer large areas for muscles to attach. Examples include the sternum (breastbone), scapula (shoulder blade), and skull bones." : 1]

concept: "Muscle types"
weight_percentage: 50
snippets: ["Cardiac MuscleControl: Involuntary (works on its own without you thinking about it).Location: Only in the walls of the heart.Function: Squeezes and relaxes to pump blood all through your body.Appearance: Striped or striated with a branched structure" : 5],
	  ["Smooth MuscleControl: Involuntary (works automatically).Location: In the walls of hollow internal organs like the stomach, intestines, and blood vessels.Function: Moves food through your digestive system and controls blood flow.Appearance: Smooth and solid, with no stripes" : 6]
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
question_text: "Which process describes liquid water changing into vapor and rising into the atmosphere?"
options: ["Evaporation", "Condensation", "Infiltration", "Runoff"]
correct_answers: [1]
is_select_all: false
explanation: "Evaporation is the process by which liquid water changes into water vapor and rises into the atmosphere, driven by the sun's heat."
page_number: 1
source_quote: "Evaporation is the process by which liquid water changes into water vapor and rises into the atmosphere."

question_text: "Which of the following are forms precipitation can take?"
options: ["Rain", "Snow", "Evaporation", "Hail"]
correct_answers: [1, 2, 4]
is_select_all: true
explanation: "Precipitation can take several forms depending on atmospheric temperature: rain, snow, sleet, or hail. Evaporation is a different process entirely, not a form of precipitation."
page_number: 3
source_quote: "Precipitation can take several forms depending on atmospheric temperature: rain, snow, sleet, or hail."
--END--

```
Python parses each block deterministically into a `Question` object (`concept` filled in by Python from the call context; each Question's permanent global index assigned positionally in output order — see Pipeline) — not an SDK-level structured `output_type` (see Agents section above).

**Generator — patch pass**
```
You are a tutor helping a student improve their review questions to study for an exam. Their
question list has been reviewed prior and the ones not up to quality have been marked for you
to fix. Fix ONLY the flagged Questions below, using ONLY the new snippets provided
for the fix. Follow the critique to reevaluate the question and apply an appropriate fix.

Concept: {concept}
Flagged Questions (with the Verifier's critique and fix snippets):
{for each flagged index: index, current Question fields, critique, snippets}

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
  string, copied verbatim from a provided snippet — not paraphrased

Do not touch Questions that weren't flagged — they are not in your input
and must not appear in your output.

Quality bar:
- Every fact used must trace to a provided snippet — never invent content,
  never use outside/general knowledge even if believed true
- Distractors must be plausible — wrong in a way a student could realistically
  believe, not absurd or trivially eliminable, not duplicates of each other
  or the correct answer
- Don't bundle multiple distinct facts into a single option
- source_quote must be an exact substring of one of the provided snippets

Output format:
- Separate each Question's block from the next with at least 2 newlines
- Output nothing but the Question blocks — no preamble, no closing remarks
- Only output the fixed version of each Question — do not also output its pre-fix fields
- Wrap the entire output between --START-- and --END-- markers, exactly as
  shown in the example below

--START--
index: 5
question_text: "Which process describes liquid water changing into vapor and rising into the atmosphere?"
options: ["Evaporation", "Condensation", "Infiltration", "Runoff"]
correct_answers: [1]
is_select_all: false
explanation: "Evaporation is the process by which liquid water changes into water vapor and rises into the atmosphere, driven by the sun's heat."
page_number: 1
source_quote: "Evaporation is the process by which liquid water changes into water vapor and rises into the atmosphere."

index: 8
question_text: "Which of the following are forms precipitation can take?"
options: ["Rain", "Snow", "Evaporation", "Hail"]
correct_answers: [1, 2, 4]
is_select_all: true
explanation: "Precipitation can take several forms depending on atmospheric temperature: rain, snow, sleet, or hail. Evaporation is a different process entirely, not a form of precipitation."
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
  count-inferred)
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

## Verify loop detail

**Verifier criteria**, checked per Question against the Note text:

- Answer correctness is grounded in the Note (no fabricated facts)
- Distractors are plausible — not trivially wrong or duplicates of each other
- `is_select_all` matches the intended semantics (deliberate choice, not count-inferred)
- No ambiguous or multiple-valid-reading phrasing
- `explanation` actually explains the correct answer using Note content
- Question actually matches its assigned `concept`
- `source_quote` is a real quote genuinely present on `page_number`, and it actually supports `correct_answers`/`explanation` — not fabricated, vague, or contradicting `page_number` (this check has real teeth against fabrication: `source_quote` is also verified deterministically as a verbatim substring wherever it's produced, but *whether it actually supports the answer* is a judgment call only the Verifier can make)

Every flagged issue also carries its own `snippets` (verbatim Note quotes + page numbers backing the requested fix) — the Verifier extracts these itself, since it's the only agent reading the full Note; the patch call that acts on the feedback never sees the Note, only these (see Snippet grounding above).

**Per-Question action** the Verifier can return: `keep` or `patch`. There is deliberately no `remove` or `split` — the Question list's length is locked at the user-confirmed total (see Pipeline above), so any action that changes list length is out of scope for the verify loop:

- A Question judged unnecessary/redundant isn't deleted — Generator patches that index into a *different* Question (same `concept`, fresh angle), achieving the same practical outcome without touching list length.
- A Question judged as trying to cover too much isn't split into two — Generator patches it into one tighter, more focused Question instead. If a concept genuinely needs more coverage than one Question can give it, that's fixed earlier, at the Analyzer checkpoint (user raises that concept's `question_count` before confirming) — not something the post-hoc verify loop tries to solve by resizing.

**Satisfactory** is `true` only when zero Questions in the current list are flagged with an issue. `false` triggers another loop iteration (if under the 5-iteration cap).

**Loop count**: the initial Generator pass is unlooped ("pass 0") but fans out to one concurrent call per concept (see Concurrent generation above), not one call total. Up to 5 Verifier→patch cycles follow; the cycles themselves are sequential (each round needs the previous round's result), but within a round BOTH the Verifier step and the patch step fan out concurrently, one call per concept (Verifier: every concept present; patch: only concepts among that round's flagged indices). Worst case: N concurrent initial calls + 5 rounds of (up to N concurrent Verifier calls + up to N concurrent patch calls), where N = concept count, not counting the single Analyzer call.

## API contract

FastAPI backend, session identified via HTTP-only cookie (set on first `/upload`), keyed into the in-memory `SessionStore` (lock-guarded nested hashmap, per `storage-options.md` #13).

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
- Errors: `404` if `old_name` doesn't match any Question's `concept` in the session's `QuestionSet`; `409` if `new_name` already matches a different existing concept (rename is blocked, not merged — see Editing's Concept editing).

### `GET /session`
Lets the frontend rehydrate on page load without re-uploading — needed for `requirements.md`'s persistence acceptance criteria (closing/reopening the browser mid-server-run must still show existing state).
- Response `200`: `{ status: "empty" | "checkpoint_pending" | "generating" | "ready" | "failed", allocations?: list[ConceptAllocation], questions?: list[Question] }` — `allocations` present for `checkpoint_pending`, `questions` present for `ready`.

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
- A single "Save" button commits every field changed during that edit session in one action; "Cancel" discards in-progress edits and reverts the card to its last-saved values. (No per-field autosave — fields like `is_select_all` and `correct_answers` need to land together, not independently, to stay valid.)
- This phase has no real backend: Save mutates local frontend state only (matching the shape of the API calls below, but not actually calling them) — edits are lost on reload until a real backend exists.

### Editable fields & validation

- `question_text`, `explanation`: free text.
- `options`: always exactly 4 slots (no add/remove option), each must be non-empty.
- `correct_answers`: exactly 1 marked correct when `is_select_all` is false (radio, even in edit mode); 1-4 marked correct when true (checkboxes).
- `is_select_all`: togglable; if toggling would leave the current `correct_answers` count invalid for the new value (e.g. 3 marked correct, toggling to Multiple-Choice), Save is blocked with an inline error until the user manually fixes the selection — no auto-correction.
- `page_number`: free int entry.
- `concept`: editable via two separate controls (see below). `source_quote` is never editable (not surfaced in v1 UI at all — see Snippet grounding).

### Concept editing

`concept` is a plain string tag on each Question (no separate Concept entity survives past Freeze — see Data model), so two different edits are possible:

- **Rename** — a text field showing the current label. Saving a change renames it everywhere: every Question in the Set currently tagged with the old string is updated to the new string. Blocked (error, not merge) if the new name collides with a different concept string already present elsewhere in the Set — renaming and reassigning are different intents, and a same-name collision should not silently merge two concepts.
- **Reassign** — a dropdown listing the other distinct `concept` values currently present in the Set (derived by scanning `QuestionSet.questions` for unique `concept` strings, excluding the current one). Picking one moves only this single Question to that existing concept; other Questions are unaffected. Disabled when no other concept exists in the Set.