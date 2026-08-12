"""Phase 1 (Generator-only) live test for the dual-model Generator pool —
runs pipeline.py's real _make_initial_job/_make_patch_job through
generator_pool.drain_pool against the two real models
(llama-3.3-70b-versatile, openai/gpt-oss-20b), WITHOUT wiring into a full
pipeline run. Confirms: (1) jobs actually get dispatched across both models,
(2) output parses correctly (Fix A/Fix B changes in place), (3) the code
path is exercised live end-to-end at least once per model. The failover
path itself is unit-tested offline (test_generator_pool_unit.py) — not
force-triggered here, per the design doc's Testing plan ("exercised
opportunistically if it triggers naturally... not a required,
deterministically-forced test case").

Uses the same 3 Generator-initial + 2 Generator-patch cases as
test_inputs.py, run through the REAL pipeline.py functions + generator_pool
(not a reimplementation), so a pass here is a direct confirmation the ported
Fix A/Fix B changes work against live output from both models.

Usage: python test_generator_pool_live.py
"""

import asyncio
import datetime
from pathlib import Path

import call_agent
import generator_pool
import pipeline
import test_inputs as ti
from models import ConceptAllocation, ConceptSnippet, VerifierIssue
from parsers import is_exact_substring

LOG_PATH = Path(__file__).parent / "generator-pool-test-log.md"


def _build_allocation(case: dict) -> ConceptAllocation:
    return ConceptAllocation(
        concept=case["concept"],
        weight_percentage=100.0 / len(ti.GENERATOR_INITIAL_CASES),
        question_count=case["question_count"],
        snippets=[ConceptSnippet(quote=q, page_number=p) for q, p in case["snippets"]],
    )


def _model_dispatch_from_call_log(label_prefix: str) -> dict[str, str]:
    """Reads CALL_LOG for entries whose label starts with label_prefix and
    returns {concept: model_name} for whichever attempt actually produced a
    result. Label shape (built by pipeline.py): "<prefix>-<concept>-<model>-attemptN"."""
    handled: dict[str, str] = {}
    for entry in call_agent.CALL_LOG:
        if not entry.label.startswith(label_prefix):
            continue
        for model_name in call_agent.GENERATOR_MODEL_NAMES:
            marker = f"-{model_name}-attempt"
            if marker in entry.label:
                concept = entry.label[len(label_prefix) + 1 : entry.label.index(marker)]
                handled[concept] = model_name
    return handled


async def run_initial_phase(sections: list[str]) -> dict[str, str]:
    allocations = [_build_allocation(c) for c in ti.GENERATOR_INITIAL_CASES]
    offsets = {}
    next_index = 1
    for a in allocations:
        offsets[a.concept] = next_index
        next_index += a.question_count

    step_log: list[str] = []
    jobs = [pipeline._make_initial_job(a, offsets[a.concept], step_log) for a in allocations]
    start = datetime.datetime.now()
    try:
        results = await generator_pool.drain_pool(
            jobs, call_agent.GENERATOR_MODEL_NAMES, step_log.append, "phase1-initial-pool"
        )
    except generator_pool.GeneratorPoolError as e:
        sections.append(
            f"### Phase 1 — Generator-initial pool\n\n- **POOL FAILED**: {e}\n\n"
            + "Step log:\n```\n" + "\n".join(step_log) + "\n```\n"
        )
        raise
    elapsed = (datetime.datetime.now() - start).total_seconds()

    handled_by = _model_dispatch_from_call_log("generator-initial-live")

    notes = []
    for a in allocations:
        indexed = results.get(a.concept)
        if indexed is None:
            notes.append(f"MISSING: no result for concept {a.concept!r}")
            continue
        if len(indexed) != a.question_count:
            notes.append(f"CONTRACT VIOLATION [{a.concept}]: got {len(indexed)}, expected {a.question_count}")
        snippet_texts = [s.quote for s in a.snippets]
        for q in indexed.values():
            if not any(is_exact_substring(q.source_quote, s) for s in snippet_texts):
                notes.append(f"CONTRACT VIOLATION [{a.concept}]: ungrounded source_quote {q.source_quote[:80]!r}")

    sections.append(
        f"### Phase 1 — Generator-initial pool\n\n"
        f"- **Time**: {start.isoformat(timespec='seconds')} ({elapsed:.1f}s)\n"
        f"- **Concepts**: {[a.concept for a in allocations]}\n"
        f"- **Model dispatch (by concept)**: {handled_by}\n"
        f"- **Models actually used**: {sorted(set(handled_by.values()))} "
        f"(expect both of {list(call_agent.GENERATOR_MODEL_NAMES)})\n"
        f"- **Notes**: {'; '.join(notes) if notes else 'all contracts held'}\n\n"
        f"Step log:\n```\n" + "\n".join(step_log) + "\n```\n"
    )
    return handled_by


async def run_patch_phase(sections: list[str]) -> dict[str, str]:
    step_log: list[str] = []
    all_jobs = []
    concept_lists: dict[str, dict] = {}
    flagged_by_concept: dict[str, list[VerifierIssue]] = {}
    for case in ti.GENERATOR_PATCH_CASES:
        concept = case["concept"]
        concept_lists[concept] = {idx: flag["question"] for idx, flag in case["flags"].items()}
        flagged = [
            VerifierIssue(
                index=idx,
                action="patch",
                critique=flag["critique"],
                snippets=[ConceptSnippet(quote=q, page_number=p) for q, p in flag["snippets"]],
            )
            for idx, flag in case["flags"].items()
        ]
        flagged_by_concept[concept] = flagged
        all_jobs.append(pipeline._make_patch_job(concept, flagged, concept_lists, 1, step_log))

    start = datetime.datetime.now()
    try:
        results = await generator_pool.drain_pool(
            all_jobs, call_agent.GENERATOR_MODEL_NAMES, step_log.append, "phase1-patch-pool"
        )
    except generator_pool.GeneratorPoolError as e:
        sections.append(
            f"### Phase 1 — Generator-patch pool\n\n- **POOL FAILED**: {e}\n\n"
            + "Step log:\n```\n" + "\n".join(step_log) + "\n```\n"
        )
        raise
    elapsed = (datetime.datetime.now() - start).total_seconds()

    handled_by = _model_dispatch_from_call_log("generator-patch-live-round1")

    notes = []
    for concept, flagged in flagged_by_concept.items():
        patched = results.get(concept)
        if patched is None:
            notes.append(f"MISSING: no result for concept {concept!r}")
            continue
        expected_indices = {f.index for f in flagged}
        if set(patched.keys()) != expected_indices:
            notes.append(
                f"CONTRACT VIOLATION [{concept}]: index mismatch, got {sorted(patched.keys())}, "
                f"expected {sorted(expected_indices)}"
            )
        for f in flagged:
            q = patched.get(f.index)
            if q is None:
                continue
            fix_texts = [s.quote for s in f.snippets]
            if not any(is_exact_substring(q.source_quote, s) for s in fix_texts):
                notes.append(f"CONTRACT VIOLATION [{concept}] index {f.index}: source_quote not grounded in fix snippets")

    sections.append(
        f"### Phase 1 — Generator-patch pool\n\n"
        f"- **Time**: {start.isoformat(timespec='seconds')} ({elapsed:.1f}s)\n"
        f"- **Concepts**: {list(flagged_by_concept.keys())}\n"
        f"- **Model dispatch (by concept)**: {handled_by}\n"
        f"- **Models actually used**: {sorted(set(handled_by.values()))} "
        f"(expect both of {list(call_agent.GENERATOR_MODEL_NAMES)})\n"
        f"- **Notes**: {'; '.join(notes) if notes else 'all contracts held'}\n\n"
        f"Step log:\n```\n" + "\n".join(step_log) + "\n```\n"
    )
    return handled_by


async def main() -> None:
    sections: list[str] = []
    run_start = datetime.datetime.now()

    initial_dispatch = await run_initial_phase(sections)
    patch_dispatch = await run_patch_phase(sections)

    both_models = set(call_agent.GENERATOR_MODEL_NAMES)
    all_models_seen = set(initial_dispatch.values()) | set(patch_dispatch.values())

    header = f"\n## Phase 1 live pool test — {run_start.isoformat(timespec='seconds')}\n\n"
    summary = (
        f"**Summary**: models seen across both phases: {sorted(all_models_seen)} "
        f"(both models seen: {all_models_seen == both_models})\n\n"
    )
    body = header + summary + "\n".join(sections)

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(body)
        f.write("\n---\n")

    print(f"Wrote Phase 1 pool test results to {LOG_PATH}")
    print(f"Models seen: {sorted(all_models_seen)}")


if __name__ == "__main__":
    asyncio.run(main())
