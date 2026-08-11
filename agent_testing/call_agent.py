"""Groq wiring + the 3 agents (Analyzer, Generator, Verifier), built from the
exact prompts in DESIGN.md's Agent prompts section. Each agent returns a
formatted free-text response (--START--/--END--) parsed by parsers.py, not
an SDK-level structured output_type — see DESIGN.md's Agents section for why.

Every call is logged to CALL_LOG (label, input, output, elapsed seconds) for
agent-test-log.md entries.
"""

import asyncio
import os
import re
import time
from dataclasses import dataclass, field

from agents import Agent, ModelSettings, Runner, RunConfig, set_default_openai_client, set_default_openai_api, set_tracing_disabled
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from dotenv import load_dotenv
from openai import AsyncOpenAI, RateLimitError

load_dotenv()

_client = AsyncOpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1",
)
set_default_openai_client(_client)
set_default_openai_api("chat_completions")
set_tracing_disabled(True)

# Groq's actual slug for this model is "openai/gpt-oss-120b" (vendor-prefixed) as of
# this session's live /v1/models check — NOT "gpt-oss-120b" as DESIGN.md's Model
# section currently states. The Agents SDK misparses the "/" as a litellm-style
# provider prefix and silently strips it (confirmed live: sending plain MODEL string
# produced a 404 for "gpt-oss-120b", not the "openai/..." slug actually requested) —
# same failure mode DESIGN.md already documented for NIM's slugs, contradicting that
# section's guess that Groq's slugs (assumed "/"-free) wouldn't need this wrap.
# OpenAIChatCompletionsModel bypasses the SDK's string parsing entirely.
MODEL = "openai/gpt-oss-120b"
_model = OpenAIChatCompletionsModel(model=MODEL, openai_client=_client)


@dataclass
class CallLogEntry:
    label: str
    input_text: str
    output_text: str
    elapsed_seconds: float
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


CALL_LOG: list[CallLogEntry] = []
CALL_LOG_HOOK = None  # optional callable(CallLogEntry) -> None, for live progress
RATE_LIMIT_HITS = 0  # total 429s caught across all calls — read/reset by callers for run comparisons

# Pipeline-wide cap on simultaneous in-flight calls (DESIGN.md's Concurrency cap
# section flagged this as a placeholder needing live tuning against Groq's 8K TPM
# ceiling). Live-tested: uncapped concurrent fan-out (asyncio.gather over all
# concepts at once) hit 21 rate-limit hits on a 9-concept note and ended up no
# faster than sequential — the retries just serialized it back into a queue. A
# no-op in sequential mode (calls are already one-at-a-time there).
CONCURRENCY_CAP = 3
_semaphore = asyncio.Semaphore(CONCURRENCY_CAP)


ANALYZER_INSTRUCTIONS = """\
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
"""

GENERATOR_INITIAL_INSTRUCTIONS = """\
You are writing exam-style questions for one Concept from a student's study
Note, using ONLY the snippets provided below — you have not seen and must
not assume anything about the rest of the Note.

Concept: {concept}
Snippets:
{snippets}

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
"""

GENERATOR_PATCH_INSTRUCTIONS = """\
You are a tutor helping a student improve their review questions to study for an exam. Their
question list has been reviewed prior and the ones not up to quality have been marked for you
to fix. Fix ONLY the flagged Questions below, using ONLY the new snippets provided
for the fix. Follow the critique to reevaluate the question and apply an appropriate fix.

Concept: {concept}
Flagged Questions (with the Verifier's critique and fix snippets):
{flagged_questions}

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
"""

VERIFIER_INSTRUCTIONS = """\
You are fact-checking and quality-checking Questions made by a student to review for an exam
against their Note's FULL text below. Ensure that the questions and their answers match the note,
and are comprehensive enough to be of quality for a review. You are only checking questions for
the particular concept provided, and provide critique. DO NOT CHANGE any of the question contents.

Note text:
{note_text}

Questions to check (all belong to Concept: {concept}):
{questions}

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
"""

# Analyzer's instructions have no per-call placeholders — Note text is
# passed as the call's input instead (see DESIGN.md: "input: Note text
# only"). Generator/Verifier instructions DO have inline {field}
# placeholders filled per call by the build_*_prompt functions below, so
# those agents get minimal generic instructions and the filled template is
# passed as input instead — same call_agent_async either way.
GENERIC_INSTRUCTIONS = "Follow the user's instructions exactly."

analyzer_agent = Agent(name="Analyzer", instructions=ANALYZER_INSTRUCTIONS, model=_model)
generator_initial_agent = Agent(name="Generator (initial)", instructions=GENERIC_INSTRUCTIONS, model=_model)
generator_patch_agent = Agent(name="Generator (patch)", instructions=GENERIC_INSTRUCTIONS, model=_model)
verifier_agent = Agent(name="Verifier", instructions=GENERIC_INSTRUCTIONS, model=_model)


def format_snippets(snippets: list[tuple[str, int]]) -> str:
    """snippets: list of (quote, page_number) -> ["quote" : N] lines."""
    return ",\n".join(f'["{quote}" : {page}]' for quote, page in snippets)


def build_generator_initial_prompt(concept: str, question_count: int, snippets: list[tuple[str, int]]) -> str:
    return GENERATOR_INITIAL_INSTRUCTIONS.format(
        concept=concept, question_count=question_count, snippets=format_snippets(snippets)
    )


def build_generator_patch_prompt(concept: str, flagged_questions_text: str) -> str:
    return GENERATOR_PATCH_INSTRUCTIONS.format(concept=concept, flagged_questions=flagged_questions_text)


def build_verifier_prompt(note_text: str, concept: str, questions_text: str) -> str:
    return VERIFIER_INSTRUCTIONS.format(note_text=note_text, concept=concept, questions=questions_text)


# --- Batched (multi-concept per call) prompts --------------------------------
# One call now covers a small batch of Concepts (2-3) instead of exactly one —
# middle ground between the per-concept split design (many small calls, lots
# of repeated boilerplate) and the big-call design (one call for everything,
# which broke on output-length truncation — see PROGRESS.md). Each Question/
# verdict block is self-tagged with a `concept` field so Python can still
# route results back to the right concept's list.

GENERATOR_INITIAL_BATCH_INSTRUCTIONS = """\
You are writing exam-style questions for a batch of Concepts from a student's
study Note, using ONLY each Concept's own snippets below — you have not seen
and must not assume anything about the rest of the Note.

Concepts:
{concepts_block}

For each Concept, write exactly its requested number of Questions, using ONLY
that Concept's own snippets — never use one Concept's snippets to answer
another Concept's Question. For each Question, output a block with these
fields:
- concept: which Concept this Question belongs to, as a quoted string — must
  exactly match one of the Concept names above, character-for-character
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
  correct, using only that Concept's own snippets
- page_number: the page number (int) the grounding snippet came from
- source_quote: the exact snippet text (or relevant portion), as a quoted
  string, copied verbatim from that Concept's own snippets — not paraphrased

Quality bar:
- Every fact used must trace to a provided snippet — never invent content,
  never use outside/general knowledge even if believed true
- Distractors must be plausible — wrong in a way a student could realistically
  believe, not absurd or trivially eliminable, not duplicates of each other
  or the correct answer
- Don't bundle multiple distinct facts into a single option
- If a Concept's question_count exceeds what its snippets can support
  distinctly, vary phrasing/format/tested detail rather than repeating —
  never fabricate to hit the count
- source_quote must be an exact substring of one of that Question's own
  Concept's provided snippets

Output format:
- Separate each Question's block from the next with at least 2 newlines
- Output nothing but the Question blocks — no preamble, no closing remarks
- Wrap the entire output between --START-- and --END-- markers, exactly as
  shown in the example below

--START--
concept: "Evaporation"
question_text: "Which process describes liquid water turning into vapor?"
options: ["Evaporation", "Condensation", "Infiltration", "Runoff"]
correct_answers: [1]
is_select_all: false
explanation: "Evaporation is liquid water becoming vapor, driven by the sun's heat."
page_number: 1
source_quote: "Evaporation is the process by which liquid water changes into water vapor and rises into the atmosphere."

concept: "Precipitation"
question_text: "Which of the following are forms of precipitation?"
options: ["Rain", "Snow", "Evaporation", "Hail"]
correct_answers: [1, 2, 4]
is_select_all: true
explanation: "Rain, snow, and hail are precipitation forms; evaporation is a different process, not a form of it."
page_number: 3
source_quote: "Precipitation can take several forms depending on atmospheric temperature: rain, snow, sleet, or hail."
--END--
"""

GENERATOR_PATCH_BATCH_INSTRUCTIONS = """\
You are a tutor helping a student improve their review questions to study for
an exam. Their question list has been reviewed prior and the ones not up to
quality have been marked for you to fix, across a batch of Concepts. Fix ONLY
the flagged Questions below, using ONLY the new snippets provided for each
fix. Follow each critique to reevaluate that Question and apply an
appropriate fix.

Flagged Questions (grouped by Concept, with the Verifier's critique and fix
snippets):
{flagged_block}

Each flagged Question's existing source_quote is shown above for context
only — it is what the flag is critiquing, not a valid source for your
replacement. Do not reuse it in your output unless it also happens to
appear verbatim among that flag's fix snippets.

For each flagged index, output a full replacement Question block — all
fields, not just the changed ones:
- concept: which Concept this Question belongs to, as a quoted string —
  copied from its input, must not change
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
  correct, using only the given fix snippets
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
concept: "Evaporation"
index: 5
question_text: "Which process describes liquid water turning into vapor?"
options: ["Evaporation", "Condensation", "Infiltration", "Runoff"]
correct_answers: [1]
is_select_all: false
explanation: "Evaporation is liquid water becoming vapor, driven by the sun's heat."
page_number: 1
source_quote: "Evaporation is the process by which liquid water changes into water vapor and rises into the atmosphere."
--END--
"""

VERIFIER_BATCH_INSTRUCTIONS = """\
You are fact-checking and quality-checking Questions made by a student to review for an exam
against their Note's text below (only the pages relevant to this batch of Concepts are
included). Ensure that the questions and their answers match the note, and are comprehensive
enough to be of quality for a review. You are checking questions for a batch of Concepts,
grouped below — provide critique per Question. DO NOT CHANGE any of the question contents.

Note text (relevant pages only):
{note_text}

Questions to check (grouped by Concept):
{questions_block}

For EACH Question, output one block with these fields:
- concept: which Concept this Question belongs to (copied from its input,
  must not change)
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
- Output nothing but the Question blocks — no preamble, no closing remarks,
  no trailing summary line
- Wrap the entire output between --START-- and --END-- markers

--START--
concept: "Precipitation"
index: 3
action: "patch"
critique: "source_quote does not actually support correct_answers — the quote describes condensation, but the Question and explanation are about precipitation."
snippets: ["Precipitation is the primary way water returns from the atmosphere to the Earth's surface." : 2]

concept: "Evaporation"
index: 4
action: "keep"
critique: ""
snippets: []
--END--
"""


def build_generator_initial_batch_prompt(concepts_block: str) -> str:
    return GENERATOR_INITIAL_BATCH_INSTRUCTIONS.format(concepts_block=concepts_block)


def build_generator_patch_batch_prompt(flagged_block: str) -> str:
    return GENERATOR_PATCH_BATCH_INSTRUCTIONS.format(flagged_block=flagged_block)


def build_verifier_batch_prompt(note_text: str, questions_block: str) -> str:
    return VERIFIER_BATCH_INSTRUCTIONS.format(note_text=note_text, questions_block=questions_block)


async def call_agent_async(
    agent: Agent, prompt: str, label: str, max_retries: int = 4, max_tokens: int | None = None
) -> str:
    """Plain retry-with-backoff on Groq's 429 — needed regardless of
    concurrency mode; matters more once concurrent fan-out is in play (see
    pipeline.py), since a burst of simultaneous calls is far more likely to
    exceed the 8K TPM ceiling than sequential calls ever were.

    `max_tokens`, when given, overrides this call's completion-token cap via
    RunConfig (rather than baking a fixed cap into each Agent) so callers can
    size it per call — e.g. bigger for a multi-question Generator batch than
    for a single Verifier verdict. Without an explicit cap, a truncated
    response (cut off mid-answer, never hits --END--) just parse-fails and
    retries blind at full price — this bounds that failure mode instead of
    preventing it outright; still needs to be sized generously enough to not
    truncate legitimate output."""
    global RATE_LIMIT_HITS
    run_config = RunConfig(model_settings=ModelSettings(max_tokens=max_tokens)) if max_tokens else None
    start = time.monotonic()
    attempt = 0
    while True:
        try:
            async with _semaphore:
                result = await Runner.run(agent, prompt, run_config=run_config)
            break
        except RateLimitError as e:
            attempt += 1
            RATE_LIMIT_HITS += 1
            if attempt > max_retries:
                raise
            wait_s = _parse_retry_after_seconds(str(e)) or (5 * attempt)
            await asyncio.sleep(wait_s)
    elapsed = time.monotonic() - start
    output = result.final_output
    usage = result.raw_responses[-1].usage if result.raw_responses else None
    entry = CallLogEntry(
        label=label,
        input_text=prompt,
        output_text=output,
        elapsed_seconds=elapsed,
        input_tokens=usage.input_tokens if usage else 0,
        output_tokens=usage.output_tokens if usage else 0,
        total_tokens=usage.total_tokens if usage else 0,
    )
    CALL_LOG.append(entry)
    if CALL_LOG_HOOK is not None:
        CALL_LOG_HOOK(entry)
    return output


def _parse_retry_after_seconds(error_text: str) -> float | None:
    """Groq formats this two ways depending on wait length: "31.07s" for
    short (TPM-level) waits, "5m48.624s" for longer (TPD-level) waits — the
    original regex only handled the first, so a daily-cap 429 silently fell
    back to the tiny default backoff and burned through all retries in
    seconds instead of recognizing it needed minutes."""
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", error_text)
    if not m:
        return None
    hours, minutes, seconds = m.groups()
    total = float(seconds) + (int(minutes or 0) * 60) + (int(hours or 0) * 3600)
    return total + 0.5


def call_agent(agent: Agent, prompt: str, label: str) -> str:
    """Sync wrapper — used for the Analyzer's one non-concurrent call site."""
    import asyncio

    return asyncio.run(call_agent_async(agent, prompt, label))
