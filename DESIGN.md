# Design — Note Review (v1)

Structure and architecture for the generation pipeline: turning an uploaded Note (PDF) into a Question Set, and displaying that Question Set for review. See `CONTEXT.md` for canonical terminology and `requirements.md` for functional scope. This doc covers *how* generation works internally and the concrete data model, which `requirements.md` intentionally leaves at the behavioral level.

Out of scope for this doc: the real Review Session (shuffle, scoring, Summary) and the Kahoot-style Room/live-game mode. Both are deferred to later work per `requirements.md`. This phase only covers generation plus a minimal linear flashcard display used to verify the pipeline end-to-end.

## Pipeline

```
Upload PDF
   |
   v
Extract text (once, cached as plain string — reused by every agent call below)
   |
   v
Analyzer (runs once, not part of the loop)
   - identifies key concepts in the Note
   - assigns each concept a weight_percentage (all weights sum to 100;
     small drift is auto-corrected, see Weight reconciliation below)
   - extracts each concept's snippets: verbatim quotes + page_number,
     one or more per concept (see Snippet grounding below)
   - allocates a question_count per concept
     (honors user-specified total count if given; otherwise decides itself,
      per requirements.md's existing generation rules)
   |
   v
User checkpoint
   - user reviews the concept/weight/question_count breakdown
   - can inline-edit any weight_percentage or question_count
   - must re-sum to 100 before confirming
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
   - results are reassembled, in concept order, into one fixed-length list,
     indexed 1..N — this same list, same length, same index meaning, is
     reused for the rest of the pipeline
   |
   v
Verify loop (up to 5 iterations)
   - Verifier checks every Question by index — one concurrent call per
     concept, each seeing the FULL Note plus only that concept's Questions
     (see Verify Loop Detail, Concurrent generation below)
   - if satisfactory == true (every concept's call agreed): break early
   - else: Generator patches (in place, same index) only the flagged Questions —
     one concurrent call per concept among the flagged indices, not one call
     per index and not one call for everything — loop continues, list length
     never changes
   - after 5 iterations with no satisfactory result: ship the list as-is
     (best-effort), no error — surface a non-blocking note if issues
     remain, consistent with the existing sparse-content notice pattern
   |
   v
Freeze QuestionSet
   - list is locked into the final QuestionSet.questions, unchanged in size
     from what Generator's initial pass produced
   |
   v
Linear flashcard display (this phase's UI)
   |
   v
In-place editing (any time after generation, from the flashcard view)
```

## Agents (OpenAI Agents SDK, on Groq)

Three distinct agents, each with a structured Pydantic `output_type`. Orchestration (the checkpoint, the up-to-5 verify loop, patch dispatch) is plain Python control flow — **not** agent-internal handoffs or a self-driven tool loop. Each agent call is stateless; Note text and any other needed context is passed explicitly into every call.

- **Analyzer** — input: Note text (+ optional user-specified target question count). Output: `list[ConceptAllocation]` (concept, weight, question count, and each concept's verbatim snippets). Runs exactly once, before the loop.
- **Generator** — never reads the full Note, in either shape; only ever sees snippets:
  - **Initial pass**: one call per concept, run concurrently. Input is that concept's `(concept, question_count)` slot plus the Analyzer's snippets for it. Output: exactly `question_count` `Question` objects for that concept.
  - **Patch pass**: one call per *concept among the flagged indices*, run concurrently (not one call for every flagged index across the whole set). Input is the current numbered Question list, that concept's flagged indices + feedback, and the Verifier's snippets backing that fix. Output: replacement `Question` objects only for the indices it was asked to patch — same indices, list length unchanged.
- **Verifier** — one call per concept, run concurrently (see Concurrent generation below). Input: the FULL Note text (the only agent that ever gets it — see Snippet grounding below for why) plus only that concept's Questions, addressed by their permanent global index. Output per call: a critique for that concept's flagged indices (now including the Verifier's own extracted snippets backing each fix, not just prose feedback) plus a per-call `satisfactory: bool`; the round's overall result is `satisfactory` iff every concept's call was.

### Concurrent generation

The Generator's initial pass is one `call_agent` per concept, fired together via `asyncio.gather` rather than one serial call covering every concept slot. A first live end-to-end test (see `PROGRESS.md`) found the single-call version spent 62% of total pipeline wall time in that one call; splitting it by concept turns that stage's cost from *sum of every concept's call time* into roughly *the slowest single concept's call time* — concurrent branches hide each other's latency, so the stage is bounded by its slowest branch (including that branch's own retries), not the total.

The Generator's patch pass uses the same fan-out, grouped by concept rather than fully per-index: every verify round's flagged `VerifierIssue`s are bucketed by `questions[issue.question_index].concept`, and one concurrent call goes out per bucket, carrying only that bucket's snippets (concatenated from its issues' `snippets`). Grouping (not fully per-index) matters here specifically — two flagged questions on the same concept land in the *same* call, so the patch agent sees them together and can't independently write two near-duplicate replacements for that concept the way two isolated per-index calls could. Each patch call is validated to return patches for exactly its assigned indices (not fewer, not more, not another group's) before being merged back into the shared Question list. Expected win is smaller here than the initial pass's — patch batches were already small (2-3 flagged questions per round in testing) — but real whenever flagged questions span more than one concept, plus the same input-size reduction as the initial pass now that patch is snippet-scoped too.

The Verifier gets the same per-concept fan-out too, one concurrent call per concept present in the current Question list. Unlike the Generator's calls, each Verifier call still gets the **entire Note** — narrowing it wouldn't be safe, since judging correctness against the source is the Verifier's whole job (see Snippet grounding below). What shrinks per call instead is the Question list: each call only checks the Questions belonging to its own concept, addressed by their real global index (so a call scoped to indices `{2, 5, 9}` reports issues against those same indices, not a local 0..2 range) — cutting the Questions-list portion of the input without touching the Note portion. A round's overall `satisfactory` is the AND of every concept's call; any single unsatisfactory concept sends the round to patch. Each call is validated to only flag indices from its own assigned set — a concept-scoped call misreporting another concept's index would silently corrupt the merge.

`call_agent`'s implementation is `async` (`call_agent_async`, using the Agents SDK's `Runner.run` rather than `Runner.run_sync`) with a synchronous wrapper (`call_agent`) for the pipeline's one remaining non-concurrent call site (the single Analyzer call). Every call carries an explicit `label` (e.g. `"Generator (initial: Krebs cycle)"`, `"Verifier (round 2)"`) recorded alongside its input/output/timing in an in-memory `CALL_LOG`, since multiple concurrent calls can share the same underlying `Agent` and would otherwise be indistinguishable in a transcript. An optional `CALL_LOG_HOOK` lets a caller stream each call the instant it completes, for live progress/transcript tooling (see `_e2e_test_pipeline.py`) — the pipeline itself never reads `CALL_LOG` back.

### Snippet grounding

The Verifier is the only agent in the whole pipeline that ever reads the full Note. The Analyzer and the Generator (both its shapes) work entirely from **snippets** — verbatim quotes + `page_number`, formatted as `["quoted text" : page N]` — never the raw Note text:

- The Analyzer extracts one or more snippets per Concept during its single pass (a Concept discussed in multiple places gets multiple snippets). These become the Generator's **entire** view of the Note for that Concept's initial-pass call.
- The Verifier, when it flags a Question, extracts its own snippets backing the requested fix — reusing the Question's existing `source_quote` if that's already the right grounding, or pulling different/additional quotes if the actual problem is something the original grounding missed (e.g. a caveat stated elsewhere in the Note). These become the Generator's **entire** view of the Note for that patch call. This is *how* the pipeline still gets a wide-context safety net despite the Generator never reading the full Note: the Verifier is the one agent that does, so it's positioned to notice when a fix needs Note content beyond what a Question's own narrow slice contained, and to hand exactly that content forward — rather than either narrowing everything (losing the safety net) or handing the full Note to every call (losing the size/latency win).
- Every snippet, wherever it's produced — Analyzer's initial extraction, Verifier's per-issue extraction, or a Generator's `source_quote` copied from either — is validated deterministically as an exact (whitespace-normalized) substring of its source text (the Note, for Analyzer/Verifier snippets; the snippets it was given, for a Generator's `source_quote`) before being trusted. Any failure retries the call that produced it. Never trust a model's claim that a quote is real — same philosophy as the weight-sum and question-count checks elsewhere in this pipeline.
- `Question.source_quote` is stored on the Question itself, not just used internally to build prompts — a permanent field, part of the domain model (see Data model below), even though nothing in v1's UI displays it yet. Intended for a future citation UI (jump to/highlight the exact source text), and it also makes `page_number` provably correct rather than a separately-guessed field, since both come from the same verified snippet.

Net effect: the Note's full text is read by exactly one agent — the Verifier, on every one of its concurrent per-concept calls each round, plus the Analyzer once overall. Every Generator call, initial or patch, works from a narrow, pre-verified slice sized to what that specific call actually needs; the Verifier alone always gets the whole thing, which is what lets its concurrent calls stay safe despite each only checking one concept's Questions (see Concurrent generation above).

### Weight reconciliation

`ConceptAllocation`/`ConceptWeight.weight_percentage` values must sum to 100. Rather than always retrying the whole Analyzer call on any drift (a full network round-trip on the free tier — ~1-3min was NIM's figure, not yet re-measured for Groq), small drift is fixed deterministically in Python: if `abs(sum - 100) <= 10`, every weight is rescaled in place by `100 / sum` (preserves each concept's relative importance ratio) and the call succeeds as-is — no retry, no network cost. Drift beyond ±10 is treated as a genuine Analyzer mistake (e.g. a dropped or duplicated concept, not just rounding noise) and still falls back to `call_agent`'s blind full-call retry. Confirmed via live testing: a 102-vs-100 drift (2% — clearly rounding noise) was the only drift observed in testing so far.

**Provider**: the `openai-agents` framework itself is unchanged, but model calls run against [Groq](https://groq.com)'s free OpenAI-compatible API (`https://api.groq.com/openai/v1`) instead of OpenAI's own billed models — wired via `set_default_openai_client()` + `set_default_openai_api("chat_completions")` + `set_tracing_disabled(True)`. **Flagged, not yet re-verified**: the NIM wiring needed each `Agent`'s `model=` wrapped in `OpenAIChatCompletionsModel` because NIM's `vendor/model` slugs contain a `/` the SDK misparsed as a `litellm/`-style provider prefix. Groq's slugs (e.g. `deepseek-r1-distill-llama-70b`) have no `/`, so that specific wrapping may no longer be necessary — confirm against a live call before assuming either way.

**Model**: `deepseek-r1-distill-llama-70b`, replacing NIM's `deepseek-ai/deepseek-v4-pro` (see `CONTEXT.md`'s Required Documents section for the provider-switch decision). **Flagged, not yet re-verified**: this is an R1-distill *reasoning* model, unlike the prior plain-instruct model — outputs may include chain-of-thought/`<think>` content unless stripped, which needs checking against the structured `output_type` parsing before trusting it. The prior model's specific empirical findings (20-50s/call speed, correct 1-based `correct_answers` handling, the bundled-multiple-facts-in-one-option flaw) were measured against `deepseek-v4-pro` on NIM and do **not** automatically carry over — re-run the same 4-candidate/4-call-shape/Select-All comparison from `PROGRESS.md` against this model before trusting those specifics for Groq.

**Free-tier caveat**: Groq's free-tier rate limit has not yet been measured for this pipeline (NIM's was ~40 RPM — do not assume the same figure applies). Check Groq's published limits for the current model and update this line before relying on it for the verify loop's concurrent per-concept fan-out.

Deterministic Python loop, not an LLM-controlled loop, because the 5-iteration cap and early-exit need to be reliably enforced rather than trusted to model judgment.

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

## Flashcard display (this phase)

Minimal linear view to prove the pipeline works end-to-end — **not** the real Review Session:
- Iterates `QuestionSet.questions` in array index order (generation/freeze order)
- Shows: question_text, all 4 options, correct answer(s), explanation, page_number, concept
- No shuffling, no scoring, no Summary screen — those belong to the real Review Session, built later per `requirements.md`, reusing this same `QuestionSet`.

## Editing

From the flashcard view, at any time after generation, the user can edit any Question's fields in place: `question_text`, any of the 4 `options`, `correct_answers`, `is_select_all`, `explanation`, `page_number`. No adding or removing Questions from the set via the UI in v1 — the array stays the size it was frozen at. (This pulls "manual editing" forward from `requirements.md`'s v1.x-deferred list into v1 scope — see that file's changelog.)
