# Dual-Model Generator Pool — Design

## Purpose

The Generator agent produces Questions from Note snippets, one call per Concept per generation stage. It runs on two models, `llama-3.3-70b-versatile` and `openai/gpt-oss-20b`, dispatched through a two-worker pool so both models make progress at the same time. The Analyzer and Verifier agents both run on `gpt-oss-120b`.

## Architecture

The Generator's work — one job per Concept for the initial pass, one job per flagged Concept for each patch round — is pushed onto a single shared queue. Two workers drain it, one bound to each model. Each worker processes exactly one job at a time, so a single model is never asked to do two things simultaneously, while the two workers run concurrently with each other. The pool's own two-worker structure is what governs Generator concurrency in practice. The pipeline's `CONCURRENCY_CAP` semaphore remains in place as shared infrastructure every agent call passes through, but since the pool never has more than two Generator calls in flight at once — one per worker — the cap is never the binding constraint for Generator; it continues to bind the Verifier and Analyzer's shared `gpt-oss-120b` calls as it does today. No special-case exclusion is needed.

## Components

**Agents**: four `Agent` objects — one pair (initial pass, patch pass) per model — each with its own `OpenAIChatCompletionsModel` client instance pointed at its model string, sharing the same underlying Groq client and key. Call labels include the model name so per-call logs identify which model produced a given result.

**Prompts**: the Generator initial and patch prompt instructions require double quotes for every string value (question_text, each options entry, explanation, source_quote), never single quotes, including when writing the options list in a Python-list-like style.

**Parsing**: `parse_list_str` accepts a bracketed list of double-quoted strings via its primary format check; if that check doesn't yield the expected count, it falls back to parsing the bracketed text as a Python list literal, which correctly handles single-quoted or mixed-quote strings including any internal apostrophes. The result still passes through the same downstream validation (exactly four options) regardless of which path produced it.

**Pool runner**: builds the job list for a given stage (initial pass or patch round), runs the two-worker queue-drain, and returns each Concept's resulting Questions in the same shape the rest of the pipeline already expects.

Scope: the pool covers the `batch_size=1` path (one Concept per call). Concept batching is a separate, independently-scoped feature.

## Data flow

The Analyzer produces the Concept allocation. After checkpoint confirmation, the Generator-initial stage builds one job per confirmed Concept and drains them through the two-worker pool, producing each Concept's Question list. The verify loop then runs: the Verifier evaluates each Concept's Questions; any Concept flagged for a patch becomes one job per flagged Concept, drained through the same pool used by the initial pass. This repeats each round until every Concept is satisfactory or the round cap is reached. The pool is invoked fresh each time Generator work exists.

## Error handling

Each job carries a set of model names it has already been tried on. A worker attempts its job on its own model with the standard per-call retry/backoff. If every retry on that model fails, the job is tagged with that model's name and pushed back onto the shared queue; a worker skips any job already tagged with its own model, so a requeued job is only picked up by the other worker, which attempts it fresh with its own full retry/backoff on the other model. If a job fails on both models, the pipeline raises a `PipelineError`, surfaced to the user as a generic error with a retry option.

## Testing plan

A full pipeline-scale run against the project's test note, checked with the existing quality-check tooling for parity against the established quality baseline. Wall-clock time is compared against the single-model baselines to confirm the pool delivers a real concurrency improvement. The failover path is exercised opportunistically if it triggers naturally during testing; it is not a required, deterministically-forced test case.

## Documentation updates

Scoped to the `agent-testing` branch only. DESIGN.md's Agents section, Concurrent generation section, and Capacity map describe the two-model pool and each model's rate limits. The Agent prompts section's Generator blocks carry the double-quote instruction. PROGRESS.md's Todo reflects this as in-progress work.
