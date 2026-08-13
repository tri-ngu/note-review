"""Analyzer -> checkpoint -> Generator initial pass -> verify loop (up to 5
rounds) -> Freeze, per DESIGN.md's Pipeline section. The checkpoint itself
(user reviews/edits the Analyzer's allocation before confirming) lives in
the API layer (main.py's endpoints + SessionStore), not here — this module
is the pure orchestration logic each endpoint calls into.

Retries: DESIGN.md says "any [snippet-validation] failure retries the call
that produced it" — implemented here as a bounded per-call retry, same
philosophy as the weight-drift correction (small drift auto-fixed, large
drift or repeated bad output retries the underlying call).
"""

import asyncio
import math
import re
from typing import Callable

from pydantic import ValidationError

from agents import Agent

from app import call_agent, generator_pool
from app.call_agent import (
    analyzer_agent,
    build_generator_initial_prompt,
    build_generator_patch_prompt,
    build_verifier_prompt,
    call_agent_async,
    format_snippets,
    verifier_agent,
)
from app.models import ConceptAllocation, Question, QuestionSet, VerifierIssue
from app.parsers import (
    ParseError,
    is_exact_substring,
    parse_analyzer_output,
    parse_generator_initial_output,
    parse_generator_patch_output,
    parse_verifier_output,
)

MAX_RETRIES = 3
VERIFY_LOOP_CAP = 5
DEFAULT_QUESTIONS_PER_CONCEPT = 3

# Explicit completion-token caps, sized per call rather than one fixed value —
# base overhead (reasoning + formatting) plus a generous per-question/per-concept
# margin. Deliberately generous relative to observed live-run output — the goal
# is bounding runaway/pathological output, not shaving normal calls close to the
# edge (that's what broke the big-call design's single all-concepts-at-once
# call, see PROGRESS.md). Without any cap, a truncated response just parse-fails
# and blind-retries at full price instead of failing fast.
ANALYZER_MAX_TOKENS = 6000  # no per-call count available upfront (concept count is the Analyzer's own output)
GENERATOR_BASE_TOKENS = 1500
GENERATOR_PER_QUESTION_TOKENS = 700
VERIFIER_BASE_TOKENS = 1500
VERIFIER_PER_QUESTION_TOKENS = 600  # bumped from 1000/400 on agent-testing — the two new
# quality-bar criteria (distractor cross-check, cross-question duplicate check) make
# critique text longer; a 3-question call truncated mid-critique at the old 2200-token
# cap on a live run right after those criteria were added


class PipelineError(Exception):
    pass


def log(step_log: list[str], msg: str) -> None:
    step_log.append(msg)


# --- Analyzer + question_count derivation -----------------------------------

async def run_analyzer(note_text: str, target_total: int | None, step_log: list[str]) -> list[ConceptAllocation]:
    parsed = None
    for attempt in range(1, MAX_RETRIES + 1):
        raw = await call_agent_async(
            analyzer_agent, note_text, f"analyzer-attempt{attempt}", max_tokens=ANALYZER_MAX_TOKENS
        )
        try:
            candidate = parse_analyzer_output(raw)
        except (ParseError, ValidationError) as e:
            log(step_log, f"Analyzer attempt {attempt}: parse failure ({e}), retrying")
            continue

        bad_snippet = next(
            (
                snip.quote
                for c in candidate
                for snip in c["snippets"]
                if not is_exact_substring(snip.quote, note_text)
            ),
            None,
        )
        if bad_snippet is not None:
            log(step_log, f"Analyzer attempt {attempt}: fabricated snippet {bad_snippet[:60]!r}, retrying")
            continue

        weight_sum = sum(c["weight_percentage"] for c in candidate)
        drift = weight_sum - 100
        if abs(drift) > 10:
            log(step_log, f"Analyzer attempt {attempt}: weight drift {drift:+.2f} exceeds +/-10, retrying")
            continue

        if weight_sum != 100:
            scale = 100 / weight_sum
            for c in candidate:
                c["weight_percentage"] *= scale
            log(step_log, f"Analyzer attempt {attempt}: rescaled weights by {scale:.4f} (drift {drift:+.2f})")

        parsed = candidate
        log(step_log, f"Analyzer attempt {attempt}: OK, {len(parsed)} concepts")
        break

    if parsed is None:
        raise PipelineError(f"Analyzer failed after {MAX_RETRIES} attempts")

    num_concepts = len(parsed)
    total = target_total if target_total is not None else DEFAULT_QUESTIONS_PER_CONCEPT * num_concepts
    log(
        step_log,
        f"Target total question_count: {total} "
        f"({'user-specified' if target_total is not None else f'default = {DEFAULT_QUESTIONS_PER_CONCEPT} x {num_concepts} concepts'})",
    )

    counts = _derive_question_counts(parsed, total)

    allocations = []
    for c, count in zip(parsed, counts):
        allocations.append(
            ConceptAllocation(
                concept=c["concept"],
                weight_percentage=c["weight_percentage"],
                question_count=count,
                snippets=c["snippets"],
            )
        )
    return allocations


def _derive_question_counts(parsed: list[dict], total: int) -> list[int]:
    """round(weight_percentage/100*total) then largest-remainder reconciliation
    so counts sum exactly to total — per DESIGN.md's Weight reconciliation."""
    raw_shares = [c["weight_percentage"] / 100 * total for c in parsed]
    counts = [round(x) for x in raw_shares]
    diff = total - sum(counts)
    remainders = [raw - math.floor(raw) for raw in raw_shares]
    order = sorted(range(len(parsed)), key=lambda i: remainders[i], reverse=(diff > 0))
    i = 0
    while diff != 0:
        idx = order[i % len(order)]
        if diff > 0:
            counts[idx] += 1
            diff -= 1
        elif counts[idx] > 0:
            counts[idx] -= 1
            diff += 1
        i += 1
        if i > len(order) * (abs(total) + 2):
            break
    return counts


# --- Generator initial pass --------------------------------------------------

async def _generate_initial_for_concept(
    alloc: ConceptAllocation, start_index: int, step_log: list[str], agent: Agent, model_label: str
) -> dict[int, Question]:
    snippets = [(s.quote, s.page_number) for s in alloc.snippets]
    questions: list[Question] | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        prompt = build_generator_initial_prompt(alloc.concept, alloc.question_count, snippets)
        raw = await call_agent_async(
            agent,
            prompt,
            f"generator-initial-{alloc.concept}-{model_label}-attempt{attempt}",
            max_tokens=GENERATOR_BASE_TOKENS + alloc.question_count * GENERATOR_PER_QUESTION_TOKENS,
        )
        try:
            candidate = parse_generator_initial_output(raw, alloc.concept)
        except (ParseError, ValidationError) as e:
            log(step_log, f"Generator-initial [{alloc.concept}] ({model_label}) attempt {attempt}: parse failure ({e}), retrying")
            continue
        if len(candidate) != alloc.question_count:
            log(
                step_log,
                f"Generator-initial [{alloc.concept}] ({model_label}) attempt {attempt}: got {len(candidate)}, "
                f"expected {alloc.question_count}, retrying",
            )
            continue
        snippet_texts = [s[0] for s in snippets]
        bad = next((q for q in candidate if not any(is_exact_substring(q.source_quote, s) for s in snippet_texts)), None)
        if bad is not None:
            log(step_log, f"Generator-initial [{alloc.concept}] ({model_label}) attempt {attempt}: ungrounded source_quote, retrying")
            continue
        questions = candidate
        break

    if questions is None:
        raise PipelineError(
            f"Generator-initial failed for concept {alloc.concept!r} on model {model_label!r} after {MAX_RETRIES} attempts"
        )

    indexed = {start_index + i: q for i, q in enumerate(questions)}
    log(step_log, f"Generator-initial [{alloc.concept}] ({model_label}): {len(questions)} Questions, indices {sorted(indexed.keys())}")
    return indexed


async def run_generator_initial(
    allocations: list[ConceptAllocation],
    step_log: list[str],
    on_event: Callable[[dict], None] | None = None,
) -> dict[str, dict[int, Question]]:
    # Index offsets computed upfront (concept order, cumulative question_count)
    # so global indices stay correct regardless of which concurrent call
    # finishes first — per DESIGN.md: "each Question gets its permanent
    # global index ... the moment it's produced".
    offsets = {}
    next_index = 1
    for alloc in allocations:
        offsets[alloc.concept] = next_index
        next_index += alloc.question_count

    def on_result(concept: str, _result: dict[int, Question]) -> None:
        if on_event is not None:
            on_event({"stage": "generator_initial", "concept": concept})

    # Dual-model pool (see _run_generator_pool below) — its own two-worker
    # structure governs Generator concurrency, independent of the pipeline's
    # `concurrent` flag (which still governs Verifier dispatch in run_verify_loop).
    jobs = [_make_initial_job(a, offsets[a.concept], step_log) for a in allocations]
    return await _run_generator_pool(jobs, step_log, "Generator-initial-pool", on_result=on_result)


# --- Verify loop --------------------------------------------------------------

def _fmt_question_for_verifier(idx: int, q: Question) -> str:
    return (
        f"index: {idx}\n"
        f'question_text: "{q.question_text}"\n'
        f"options: {q.options}\n"
        f"correct_answers: {q.correct_answers}\n"
        f"is_select_all: {'true' if q.is_select_all else 'false'}\n"
        f'explanation: "{q.explanation}"\n'
        f"page_number: {q.page_number}\n"
        f'source_quote: "{q.source_quote}"'
    )


_PAGE_HEADING_RE = re.compile(r"(\[Page \d+\])")
_PAGE_NUMBER_RE = re.compile(r"\[Page (\d+)\]")


def _extract_pages(note_text: str, page_numbers: set[int]) -> str:
    """Return only the requested [Page N] sections of note_text (heading
    included), in ascending page order — not the whole Note. Splits on the
    same [Page N] heading format the Extraction/Analyzer pipeline already
    relies on (see DESIGN.md's Extraction section)."""
    parts = _PAGE_HEADING_RE.split(note_text)
    pages: dict[int, str] = {}
    i = 1
    while i < len(parts) - 1:
        m = _PAGE_NUMBER_RE.match(parts[i])
        if m:
            pages[int(m.group(1))] = parts[i] + parts[i + 1]
        i += 2
    selected = [pages[n] for n in sorted(page_numbers) if n in pages]
    return "\n".join(selected) if selected else note_text


async def _verify_concept(
    concept: str,
    indexed: dict[int, Question],
    note_text: str,
    round_num: int,
    step_log: list[str],
    on_event: Callable[[dict], None] | None = None,
) -> tuple[str, list[VerifierIssue], bool]:
    referenced_pages = {q.page_number for q in indexed.values()}
    # Include each referenced page's immediate neighbors (N-1, N+1) too — a
    # fix snippet often needs a caveat/detail stated just before or after the
    # page a Question was drawn from, not only on that exact page. See
    # DESIGN.md's Snippet grounding. _extract_pages silently drops any
    # requested page number that doesn't exist (e.g. page 0, or one past the
    # Note's last page), so no bounds-checking is needed here.
    relevant_pages = {p + delta for p in referenced_pages for delta in (-1, 0, 1)}
    scoped_note = _extract_pages(note_text, relevant_pages)
    questions_text = "\n\n".join(_fmt_question_for_verifier(idx, q) for idx, q in indexed.items())
    prompt = build_verifier_prompt(scoped_note, concept, questions_text)
    raw = await call_agent_async(
        verifier_agent,
        prompt,
        f"verifier-round{round_num}-{concept}",
        max_tokens=VERIFIER_BASE_TOKENS + len(indexed) * VERIFIER_PER_QUESTION_TOKENS,
    )
    issues, satisfactory = parse_verifier_output(raw)

    for issue in issues:
        if issue.action == "patch":
            for snip in issue.snippets:
                if not is_exact_substring(snip.quote, note_text):
                    log(step_log, f"Verifier round {round_num} [{concept}]: fabricated fix snippet on index {issue.index}, dropping that flag")
                    issue.snippets = [s for s in issue.snippets if is_exact_substring(s.quote, note_text)]

    log(step_log, f"Verifier round {round_num} [{concept}]: satisfactory={satisfactory}, flagged={[i.index for i in issues if i.action == 'patch']}")
    if on_event is not None:
        on_event({"stage": "verify_round", "round": round_num, "concept": concept})
    return concept, issues, satisfactory


async def _patch_concept(
    concept: str,
    flagged: list[VerifierIssue],
    concept_lists: dict[str, dict[int, Question]],
    round_num: int,
    step_log: list[str],
    agent: Agent,
    model_label: str,
) -> dict[int, Question]:
    flagged_text = "\n\n".join(
        _fmt_question_for_verifier(i.index, concept_lists[concept][i.index])
        + f'\ncritique: "{i.critique}"'
        + f"\nfix_snippets: {format_snippets([(s.quote, s.page_number) for s in i.snippets])}"
        for i in flagged
    )
    prompt = build_generator_patch_prompt(concept, flagged_text)
    flagged_indices = {i.index for i in flagged}
    patched: dict[int, Question] | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        raw = await call_agent_async(
            agent,
            prompt,
            f"generator-patch-round{round_num}-{concept}-{model_label}-attempt{attempt}",
            max_tokens=GENERATOR_BASE_TOKENS + len(flagged) * GENERATOR_PER_QUESTION_TOKENS,
        )
        try:
            candidate = parse_generator_patch_output(raw, concept)
        except (ParseError, ValidationError) as e:
            log(step_log, f"Patch [{concept}] round {round_num} ({model_label}) attempt {attempt}: parse failure ({e}), retrying")
            continue
        if set(candidate.keys()) != flagged_indices:
            log(step_log, f"Patch [{concept}] round {round_num} ({model_label}) attempt {attempt}: index mismatch, retrying")
            continue
        patched = candidate
        break
    if patched is None:
        raise PipelineError(
            f"Generator-patch failed for concept {concept!r} on model {model_label!r} round {round_num} after {MAX_RETRIES} attempts"
        )
    log(step_log, f"Patch [{concept}] round {round_num} ({model_label}): updated indices {sorted(patched.keys())}")
    return patched


# --- Dual-model Generator pool dispatch ---------------------------------------
# Generator work (initial pass + patch rounds) is dispatched through
# generator_pool's two-worker queue-drain instead of a single model's direct
# dispatch — see DESIGN.md's Concurrent generation: Dual-model Generator pool.

def _make_initial_job(alloc: ConceptAllocation, start_index: int, step_log: list[str]) -> generator_pool.Job:
    async def attempt(model_name: str) -> dict[int, Question]:
        agent = call_agent.generator_initial_agents[model_name]
        return await _generate_initial_for_concept(alloc, start_index, step_log, agent, model_name)

    return generator_pool.Job(key=alloc.concept, attempt=attempt)


def _make_patch_job(
    concept: str,
    flagged: list[VerifierIssue],
    concept_lists: dict[str, dict[int, Question]],
    round_num: int,
    step_log: list[str],
) -> generator_pool.Job:
    async def attempt(model_name: str) -> dict[int, Question]:
        agent = call_agent.generator_patch_agents[model_name]
        return await _patch_concept(concept, flagged, concept_lists, round_num, step_log, agent, model_name)

    return generator_pool.Job(key=concept, attempt=attempt)


async def _run_generator_pool(
    jobs: list[generator_pool.Job],
    step_log: list[str],
    stage_label: str,
    on_result: Callable[[str, dict[int, Question]], None] | None = None,
) -> dict[str, dict[int, Question]]:
    try:
        return await generator_pool.drain_pool(
            jobs, call_agent.GENERATOR_MODEL_NAMES, lambda msg: log(step_log, msg), stage_label, on_result=on_result
        )
    except generator_pool.GeneratorPoolError as e:
        raise PipelineError(str(e)) from e


async def run_verify_loop(
    concept_lists: dict[str, dict[int, Question]],
    note_text: str,
    step_log: list[str],
    concurrent: bool = False,
    on_event: Callable[[dict], None] | None = None,
) -> tuple[dict[str, dict[int, Question]], bool, int]:
    # Only concepts still in `pending` get a Verifier call this round — a concept
    # cleared (satisfactory) in an earlier round can't have changed since (nothing
    # touches its Questions unless it's patched), so re-sending it every round
    # would just re-buy the same "keep" for a full Note + questions Verifier call.
    pending = set(concept_lists.keys())
    for round_num in range(1, VERIFY_LOOP_CAP + 1):
        round_issues: dict[str, list[VerifierIssue]] = {}

        verify_coros = [
            _verify_concept(concept, concept_lists[concept], note_text, round_num, step_log, on_event)
            for concept in pending
        ]
        verify_results = await asyncio.gather(*verify_coros) if concurrent else [await c for c in verify_coros]
        for concept, issues, satisfactory in verify_results:
            round_issues[concept] = [i for i in issues if i.action == "patch"]
            if satisfactory:
                pending.discard(concept)

        if not pending:
            log(step_log, f"Verify loop: satisfactory after round {round_num}, exiting early")
            return concept_lists, True, round_num

        flagged_concepts = {c: f for c, f in round_issues.items() if f}

        def patch_on_result(concept: str, _result: dict[int, Question]) -> None:
            if on_event is not None:
                on_event({"stage": "patch", "round": round_num, "concept": concept})

        # Dual-model pool (see _run_generator_pool above) — same as the
        # initial pass, independent of the `concurrent` flag.
        jobs = [
            _make_patch_job(concept, flagged, concept_lists, round_num, step_log)
            for concept, flagged in flagged_concepts.items()
        ]
        patch_results = await _run_generator_pool(
            jobs, step_log, f"Generator-patch-pool-round{round_num}", on_result=patch_on_result
        )
        for concept, patched in patch_results.items():
            concept_lists[concept].update(patched)

    log(step_log, f"Verify loop: reached {VERIFY_LOOP_CAP}-round cap without satisfactory — shipping as-is (non-blocking)")
    return concept_lists, False, VERIFY_LOOP_CAP


# --- Freeze -------------------------------------------------------------------

def freeze(concept_lists: dict[str, dict[int, Question]]) -> QuestionSet:
    all_indexed: dict[int, Question] = {}
    for indexed in concept_lists.values():
        all_indexed.update(indexed)
    ordered = [all_indexed[i] for i in sorted(all_indexed.keys())]
    return QuestionSet(questions=ordered)
