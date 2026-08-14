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

# Groq's slug for this model is "openai/gpt-oss-120b" (vendor-prefixed). The Agents
# SDK misparses the "/" as a litellm-style provider prefix and silently strips it,
# sending a bare "gpt-oss-120b" that 404s — same failure mode as NIM's slugs (see
# DESIGN.md's Provider section). OpenAIChatCompletionsModel bypasses the SDK's
# string parsing entirely to avoid this.
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
    cached_tokens: int = 0  # Groq prompt-caching hit count, from
    # usage.prompt_tokens_details.cached_tokens — only meaningful on
    # gpt-oss-120b/gpt-oss-20b calls (see DESIGN.md's Concurrent generation:
    # Dual-model Generator pool); 0 on llama-3.3-70b-versatile, which doesn't
    # support caching at all, and may be 0 elsewhere on a cold/expired cache


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
Note, using ONLY the snippets provided at the end of this prompt — you have
not seen and must not assume anything about the rest of the Note.

For each Question, output a block with these fields:
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
- Incorrect options must be closely related to the question, requiring real
  thought to rule out — but must not convey the same meaning as any correct
  answer, just reworded
- A distractor must not be something the given snippets themselves state as
  true — if a wrong option is also asserted true elsewhere in the snippets
  and could defensibly answer the question, that's an ambiguous second
  correct answer, not a clean distractor
- Don't bundle multiple distinct facts into a single option
- If question_count exceeds what the snippets can support distinctly, vary
  phrasing/format/tested detail rather than repeating — never fabricate to
  hit the count
- source_quote must be an exact substring of one of the provided snippets
- source_quote must come from exactly ONE snippet — never join multiple
  snippets together (e.g. with "and"), even if the answer draws on facts
  from more than one. If a Question needs facts from multiple snippets,
  ground it in whichever single snippet most directly supports the core
  answer, or write it as two separate, simpler Questions instead

Output format:
- Separate each Question's block from the next with at least 2 newlines
- Output nothing but the Question blocks — no preamble, no closing remarks
- Wrap the entire output between --START-- and --END-- markers, exactly as
  shown in the example below
- Use double quotes only for every string value — question_text, each
  options entry, explanation, and source_quote. Never use single quotes,
  including when writing the options list in a Python-list-like style.

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

Concept: {concept}
Snippets:
{snippets}

Write exactly {question_count} Questions covering the Concept above, using
ONLY the given Snippets, following the fields/quality bar/output format
specified above.
"""

GENERATOR_PATCH_INSTRUCTIONS = """\
You are a tutor helping a student improve their review questions to study for an exam. Their
question list has been reviewed prior and the ones not up to quality have been marked for you
to fix. Fix ONLY the flagged Questions provided at the end of this prompt, using ONLY the new
snippets provided for each fix. Follow the critique to reevaluate the question and apply an
appropriate fix.

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
  Question's pre-fix source_quote given alongside each flagged Question below

Each flagged Question's existing source_quote, given for context below, is
what the flag is critiquing, not a valid source for your replacement. Do not
reuse it in your output unless it also happens to appear verbatim among that
flag's fix snippets.

Do not touch Questions that weren't flagged — they are not in your input
and must not appear in your output.

Quality bar:
- Every fact used must trace to a provided fix snippet — never invent
  content, never use outside/general knowledge even if believed true, and
  never fall back to the pre-fix Question's own source_quote/explanation
- Distractors must be plausible — wrong in a way a student could realistically
  believe, not absurd or trivially eliminable, not duplicates of each other
  or the correct answer
- Incorrect options must be closely related to the question, requiring real
  thought to rule out — but must not convey the same meaning as any correct
  answer, just reworded
- A distractor must not be something the fix snippets themselves state as
  true — if a wrong option is also asserted true elsewhere in the fix
  snippets and could defensibly answer the question, that's an ambiguous
  second correct answer, not a clean distractor
- Don't bundle multiple distinct facts into a single option
- source_quote must be an exact substring of one of that flag's fix
  snippets — copying the pre-fix source_quote unchanged is only acceptable
  if it also appears verbatim among the fix snippets
- source_quote must come from exactly ONE fix snippet — never join multiple
  snippets together (e.g. with "and"), even if the answer draws on facts
  from more than one. If a fix genuinely needs facts from multiple
  snippets, ground it in whichever single snippet most directly supports
  the core answer

Output format:
- Separate each Question's block from the next with at least 2 newlines
- Output nothing but the Question blocks — no preamble, no closing remarks
- Only output the fixed version of each Question — do not also output its pre-fix fields
- Wrap the entire output between --START-- and --END-- markers, exactly as
  shown in the example below
- Use double quotes only for every string value — question_text, each
  options entry, explanation, and source_quote. Never use single quotes,
  including when writing the options list in a Python-list-like style.

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

Concept: {concept}
Flagged Questions (with the Verifier's critique and fix snippets):
{flagged_questions}

Fix the flagged Questions above per the instructions and quality bar given.
"""

VERIFIER_INSTRUCTIONS = """\
You are fact-checking and quality-checking Questions made by a student to review for an exam
against the Note text provided at the end of this prompt. Ensure that the questions and their
answers match the note, and are comprehensive enough to be of quality for a review. You are only
checking questions for the particular concept provided, and provide critique. DO NOT CHANGE any of
the question contents.

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
- correct_answers correctly identifies the intended option(s) by their
  1-based position in options — position 1 is the FIRST listed option, not
  the second; position 4 is the last, not out-of-range.
- Distractors are plausible — not trivially wrong or duplicates of each other
- No distractor is itself asserted true elsewhere in the Note text in a way
  that could defensibly also answer the question — a "wrong" option the Note
  itself confirms is also true is an ambiguous second correct answer, not a
  valid distractor, and should be patched. Check with a BEST-answer test:
  does the Note support exactly ONE option, or could a student defend more
  than one? A stem qualifier ("primary", "main", "most direct") only
  resolves the ambiguity if the Note itself draws that distinction — not
  just because the question-writer added the word.
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
- Question isn't a near-duplicate of another Question in this same call's
  list — if two Questions test the same underlying fact/answer off the same
  grounding with no meaningfully different angle (reworded phrasing alone
  doesn't count as different), patch the weaker/later one, and use the
  critique to name what distinct angle or detail the replacement should
  cover instead

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

Note text:
{note_text}

Questions to check (all belong to Concept: {concept}):
{questions}

Evaluate each Question above against the Note text and quality bar given.
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

# Dual-model Generator pool wiring — per
# docs/superpowers/specs/2026-08-12-dual-model-generator-design.md: the
# Generator (see pipeline.py/generator_pool.py) runs on these two models via
# a two-worker pool, instead of gpt-oss-120b alone. Analyzer and Verifier
# stay on gpt-oss-120b (_model/MODEL above), untouched.
GENERATOR_MODEL_NAMES = ("llama-3.3-70b-versatile", "openai/gpt-oss-20b")

_generator_models = {
    name: OpenAIChatCompletionsModel(model=name, openai_client=_client) for name in GENERATOR_MODEL_NAMES
}

# One Agent per (model, pass) — four total. Call labels built by pipeline.py/
# generator_pool.py's call sites include the model name so CALL_LOG entries
# identify which model produced a given result even though multiple Agents
# share this dict's structure.
generator_initial_agents = {
    name: Agent(name=f"Generator (initial, {name})", instructions=GENERIC_INSTRUCTIONS, model=model)
    for name, model in _generator_models.items()
}
generator_patch_agents = {
    name: Agent(name=f"Generator (patch, {name})", instructions=GENERIC_INSTRUCTIONS, model=model)
    for name, model in _generator_models.items()
}


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
        cached_tokens=(usage.input_tokens_details.cached_tokens if usage and usage.input_tokens_details else 0),
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
