"""Full live pipeline: Analyzer -> checkpoint (auto-confirmed, headless) ->
Generator initial pass -> verify loop (up to 5 rounds) -> Freeze, per
DESIGN.md's Pipeline section.

Two things DESIGN.md leaves as open decisions, resolved with Tri on
2026-08-10 for this first live run:
- Concurrency: sequential, not the documented per-concept asyncio.gather
  fan-out — safer for a first full live run against Groq's 8K TPM cap.
  Follow-up: switch to concurrent (with a tuned semaphore cap) later.
- Default total question count (used only when no target is given):
  3 questions per concept, no forced minimum — DESIGN.md only ever says
  "Python decides a default total itself" without a formula.

Retries: DESIGN.md says "any [snippet-validation] failure retries the call
that produced it" — implemented here as a bounded per-call retry, same
philosophy as the weight-drift correction (small drift auto-fixed, large
drift or repeated bad output retries the underlying call).
"""

import asyncio
import datetime
import math
import re
from pathlib import Path

from pydantic import ValidationError

import call_agent
import generator_pool
from agents import Agent
from call_agent import (
    CALL_LOG,
    analyzer_agent,
    build_generator_initial_prompt,
    build_generator_patch_prompt,
    build_verifier_prompt,
    call_agent_async,
    format_snippets,
    verifier_agent,
)
from models import ConceptAllocation, ConceptSnippet, Question, QuestionSet, VerifierIssue
from parsers import (
    ParseError,
    is_exact_substring,
    parse_analyzer_output,
    parse_generator_initial_output,
    parse_generator_patch_output,
    parse_verifier_output,
)
from quality_check import run_quality_check

MAX_RETRIES = 3
VERIFY_LOOP_CAP = 5
DEFAULT_QUESTIONS_PER_CONCEPT = 3

# Explicit completion-token caps, sized per call rather than one fixed value —
# base overhead (reasoning + formatting) plus a generous per-question/per-concept
# margin. Deliberately generous relative to observed live-run output (e.g. test-1's
# largest Generator-initial call used 1904 output tokens for 6 questions; this
# formula budgets 5700 for the same) — the goal is bounding runaway/pathological
# output, not shaving normal calls close to the edge (that's what broke big-call's
# single all-concepts-at-once call). Without any cap, a truncated response just
# parse-fails and blind-retries at full price instead of failing fast.
ANALYZER_MAX_TOKENS = 6000  # no per-call count available upfront (concept count is the Analyzer's own output)
GENERATOR_BASE_TOKENS = 1500
GENERATOR_PER_QUESTION_TOKENS = 700
VERIFIER_BASE_TOKENS = 1000
VERIFIER_PER_QUESTION_TOKENS = 400

NOTE_PATH = Path(__file__).parent / "water_cycle_note.txt"
LOG_PATH = Path(__file__).parent / "pipeline-run-log.md"


class PipelineError(Exception):
    pass


def log(step_log: list[str], msg: str) -> None:
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    print(line)
    step_log.append(line)


# --- Analyzer + question_count derivation -----------------------------------

async def run_analyzer(note_text: str, target_total: int | None, step_log: list[str]) -> list[ConceptAllocation]:
    parsed = None
    for attempt in range(1, MAX_RETRIES + 1):
        raw = await call_agent_async(
            analyzer_agent, note_text, f"analyzer-live-attempt{attempt}", max_tokens=ANALYZER_MAX_TOKENS
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
    log(step_log, f"Target total question_count: {total} ({'user-specified' if target_total is not None else f'default = {DEFAULT_QUESTIONS_PER_CONCEPT} x {num_concepts} concepts'})")

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
            f"generator-initial-live-{alloc.concept}-{model_label}-attempt{attempt}",
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
    allocations: list[ConceptAllocation], step_log: list[str]
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

    # Dual-model pool (see _run_generator_pool above) — its own two-worker
    # structure governs Generator concurrency, independent of the pipeline's
    # `concurrent` flag (which still governs Verifier dispatch in run_verify_loop).
    jobs = [_make_initial_job(a, offsets[a.concept], step_log) for a in allocations]
    return await _run_generator_pool(jobs, step_log, "Generator-initial-pool")


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
    concept: str, indexed: dict[int, Question], note_text: str, round_num: int, step_log: list[str]
) -> tuple[str, list[VerifierIssue], bool]:
    relevant_pages = {q.page_number for q in indexed.values()}
    scoped_note = _extract_pages(note_text, relevant_pages)
    questions_text = "\n\n".join(_fmt_question_for_verifier(idx, q) for idx, q in indexed.items())
    prompt = build_verifier_prompt(scoped_note, concept, questions_text)
    raw = await call_agent_async(
        verifier_agent,
        prompt,
        f"verifier-live-round{round_num}-{concept}",
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
            f"generator-patch-live-round{round_num}-{concept}-{model_label}-attempt{attempt}",
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
# dispatch — see docs/superpowers/specs/2026-08-12-dual-model-generator-design.md.

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
    jobs: list[generator_pool.Job], step_log: list[str], stage_label: str
) -> dict[str, dict[int, Question]]:
    try:
        return await generator_pool.drain_pool(
            jobs, call_agent.GENERATOR_MODEL_NAMES, lambda msg: log(step_log, msg), stage_label
        )
    except generator_pool.GeneratorPoolError as e:
        raise PipelineError(str(e)) from e


async def run_verify_loop(
    concept_lists: dict[str, dict[int, Question]],
    note_text: str,
    step_log: list[str],
    concurrent: bool = False,
) -> tuple[dict[str, dict[int, Question]], bool, int]:
    # Only concepts still in `pending` get a Verifier call this round — a concept
    # cleared (satisfactory) in an earlier round can't have changed since (nothing
    # touches its Questions unless it's patched), so re-sending it every round
    # would just re-buy the same "keep" for a full Note + questions Verifier call.
    pending = set(concept_lists.keys())
    for round_num in range(1, VERIFY_LOOP_CAP + 1):
        round_issues: dict[str, list[VerifierIssue]] = {}

        verify_coros = [
            _verify_concept(concept, concept_lists[concept], note_text, round_num, step_log)
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

        # Dual-model pool (see _run_generator_pool above) — same as the
        # initial pass, independent of the `concurrent` flag.
        jobs = [
            _make_patch_job(concept, flagged, concept_lists, round_num, step_log)
            for concept, flagged in flagged_concepts.items()
        ]
        patch_results = await _run_generator_pool(jobs, step_log, f"Generator-patch-pool-round{round_num}")
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


# --- Entry point ----------------------------------------------------------------

async def main(note_path: Path = NOTE_PATH, concurrent: bool = False) -> None:
    note_text = note_path.read_text(encoding="utf-8")
    step_log: list[str] = []
    run_start = datetime.datetime.now()

    log(step_log, f"=== Pipeline run start (concurrent={concurrent}) ===")
    try:
        allocations = await run_analyzer(note_text, target_total=None, step_log=step_log)
        for a in allocations:
            log(step_log, f"Checkpoint (auto-confirmed): {a.concept!r} weight={a.weight_percentage:.2f} count={a.question_count}")

        concept_lists = await run_generator_initial(allocations, step_log)
        concept_lists, satisfactory, rounds_used = await run_verify_loop(
            concept_lists, note_text, step_log, concurrent=concurrent
        )
        question_set = freeze(concept_lists)
    except Exception:
        total_elapsed = (datetime.datetime.now() - run_start).total_seconds()
        log(step_log, f"=== Pipeline run FAILED after {total_elapsed:.1f}s, {call_agent.RATE_LIMIT_HITS} rate-limit hits ===")
        _write_failure_log(run_start, step_log, total_elapsed, concurrent, call_agent.RATE_LIMIT_HITS)
        raise

    total_elapsed = (datetime.datetime.now() - run_start).total_seconds()
    log(step_log, f"=== Pipeline run end: {len(question_set.questions)} Questions, satisfactory={satisfactory} after {rounds_used} round(s), {total_elapsed:.1f}s total, {call_agent.RATE_LIMIT_HITS} rate-limit hits ===")

    locked_total = sum(a.question_count for a in allocations)
    quality_report = run_quality_check(question_set, allocations, note_text, satisfactory, rounds_used, locked_total)

    _write_log(
        run_start, step_log, allocations, question_set, satisfactory, rounds_used,
        total_elapsed, concurrent, call_agent.RATE_LIMIT_HITS, quality_report,
    )


def _write_failure_log(
    run_start: datetime.datetime,
    step_log: list[str],
    total_elapsed: float,
    concurrent: bool,
    rate_limit_hits: int,
) -> None:
    mode_label = "concurrent" if concurrent else "sequential"
    lines = [f"\n## Pipeline run {run_start.isoformat(timespec='seconds')} ({mode_label}) — FAILED\n"]
    total_input_tokens = sum(e.input_tokens for e in CALL_LOG)
    total_output_tokens = sum(e.output_tokens for e in CALL_LOG)
    total_tokens = sum(e.total_tokens for e in CALL_LOG)
    lines.append(f"- **Total time before failure**: {total_elapsed:.1f}s")
    lines.append(f"- **Total agent calls before failure**: {len(CALL_LOG)}")
    lines.append(f"- **Rate-limit (429) hits**: {rate_limit_hits}")
    lines.append(f"- **Total tokens before failure**: {total_tokens} ({total_input_tokens} input, {total_output_tokens} output)\n")

    lines.append("### Per-call breakdown (before failure)\n")
    lines.append("| # | Label | Time (s) | Input tokens | Output tokens | Total tokens |")
    lines.append("|---|---|---|---|---|---|")
    for i, e in enumerate(CALL_LOG, start=1):
        lines.append(f"| {i} | {e.label} | {e.elapsed_seconds:.1f} | {e.input_tokens} | {e.output_tokens} | {e.total_tokens} |")
    lines.append("")

    lines.append("### Step log (up to failure)\n```")
    lines.extend(step_log)
    lines.append("```\n")
    lines.append("\n---\n")

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nWrote FAILED pipeline run (partial token log) to {LOG_PATH}")


def _write_log(
    run_start: datetime.datetime,
    step_log: list[str],
    allocations: list[ConceptAllocation],
    question_set: QuestionSet,
    satisfactory: bool,
    rounds_used: int,
    total_elapsed: float,
    concurrent: bool,
    rate_limit_hits: int,
    quality_report: list[str],
) -> None:
    mode_label = "concurrent" if concurrent else "sequential"
    lines = [f"\n## Pipeline run {run_start.isoformat(timespec='seconds')} ({mode_label})\n"]
    mode_desc = f"concurrent (capped, semaphore={call_agent.CONCURRENCY_CAP})" if concurrent else "sequential"
    lines.append(f"- **Mode**: {mode_desc}")
    lines.append(f"- **Total time**: {total_elapsed:.1f}s")
    lines.append(f"- **Total Questions**: {len(question_set.questions)}")
    lines.append(f"- **Verify loop**: satisfactory={satisfactory} after {rounds_used} round(s)")
    total_input_tokens = sum(e.input_tokens for e in CALL_LOG)
    total_output_tokens = sum(e.output_tokens for e in CALL_LOG)
    total_tokens = sum(e.total_tokens for e in CALL_LOG)
    lines.append(f"- **Total agent calls this run**: {len(CALL_LOG)}")
    lines.append(f"- **Rate-limit (429) hits**: {rate_limit_hits}")
    lines.append(f"- **Total tokens**: {total_tokens} ({total_input_tokens} input, {total_output_tokens} output)\n")

    lines.append("### Per-call breakdown\n")
    lines.append("| # | Label | Time (s) | Input tokens | Output tokens | Total tokens |")
    lines.append("|---|---|---|---|---|---|")
    for i, e in enumerate(CALL_LOG, start=1):
        lines.append(f"| {i} | {e.label} | {e.elapsed_seconds:.1f} | {e.input_tokens} | {e.output_tokens} | {e.total_tokens} |")
    lines.append("")

    lines.append("### Checkpoint allocation\n")
    lines.append("| Concept | Weight % | Question count |")
    lines.append("|---|---|---|")
    for a in allocations:
        lines.append(f"| {a.concept} | {a.weight_percentage:.2f} | {a.question_count} |")

    lines.append("\n### Step log\n```")
    lines.extend(step_log)
    lines.append("```\n")

    lines.append("### Final QuestionSet\n")
    for i, q in enumerate(question_set.questions, start=1):
        lines.append(f"**{i}.** [{q.concept}] {q.question_text}")
        lines.append(f"- options: {q.options}, correct: {q.correct_answers}, select_all: {q.is_select_all}")
        lines.append(f"- explanation: {q.explanation}")
        lines.append(f"- page {q.page_number}, source_quote: {q.source_quote!r}\n")

    lines.append("### Quality check\n")
    lines.extend(quality_report)

    lines.append("\n---\n")

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nWrote pipeline run to {LOG_PATH}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--note-file", type=Path, default=NOTE_PATH, help="Path to a note text file (defaults to water_cycle_note.txt)")
    parser.add_argument("--concurrent", action="store_true", help="Fire per-concept calls concurrently, capped by call_agent.CONCURRENCY_CAP, instead of sequentially")
    args = parser.parse_args()
    asyncio.run(main(args.note_file, concurrent=args.concurrent))
