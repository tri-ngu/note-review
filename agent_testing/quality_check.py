"""Final quality-check pass over a completed pipeline run's frozen
QuestionSet, checked against requirements.md's acceptance criteria — turns
the structural checks pipeline.py already retries on inline into an
explicit pass/fail report for the run log. Same logic works for both the
split and big-call variants; it only looks at the final QuestionSet shape,
not how it was produced.
"""

import re

from models import ConceptAllocation, QuestionSet
from parsers import is_exact_substring


def run_quality_check(
    question_set: QuestionSet,
    allocations: list[ConceptAllocation],
    note_text: str,
    satisfactory: bool,
    rounds_used: int,
    locked_total: int,
) -> list[str]:
    lines: list[str] = []
    passed = 0
    failed = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal passed, failed
        mark = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        lines.append(f"- [{mark}] {label}" + (f" — {detail}" if detail else ""))

    # requirements.md Generation & verify loop: "resulting Question Set has
    # exactly the locked total question_count, indexed 1..N, unchanged in
    # length from Generator's initial pass through the verify loop"
    check(
        "Total question_count matches locked checkpoint total",
        len(question_set.questions) == locked_total,
        f"got {len(question_set.questions)}, expected {locked_total}",
    )

    valid_concepts = {a.concept for a in allocations}
    note_pages = {int(n) for n in re.findall(r"\[Page (\d+)\]", note_text)}

    for i, q in enumerate(question_set.questions, start=1):
        check(f"Q{i}: exactly 4 options", len(q.options) == 4, f"got {len(q.options)}")
        if q.is_select_all:
            check(
                f"Q{i}: Select-All (is_select_all=true) has 1-4 correct_answers",
                1 <= len(q.correct_answers) <= 4,
                f"got {len(q.correct_answers)}",
            )
        else:
            check(
                f"Q{i}: Multiple-Choice (is_select_all=false) has exactly 1 correct_answers",
                len(q.correct_answers) == 1,
                f"got {len(q.correct_answers)}",
            )
        check(f"Q{i}: explanation non-empty", bool(q.explanation.strip()))
        check(
            f"Q{i}: concept matches a confirmed checkpoint allocation",
            q.concept in valid_concepts,
            f"{q.concept!r} not in {sorted(valid_concepts)}" if q.concept not in valid_concepts else "",
        )
        check(
            f"Q{i}: page_number is a real page in the Note",
            q.page_number in note_pages,
            f"page {q.page_number}, Note has pages {sorted(note_pages)}" if q.page_number not in note_pages else "",
        )
        check(
            f"Q{i}: source_quote is a real (whitespace-normalized) substring of the Note",
            is_exact_substring(q.source_quote, note_text),
            f"{q.source_quote[:70]!r} not found in Note text" if not is_exact_substring(q.source_quote, note_text) else "",
        )

    header = f"**Quality check: {passed} passed, {failed} failed** (out of {passed + failed} structural checks against requirements.md)"

    # Verify-loop non-satisfaction is an explicitly allowed fallback per
    # requirements.md ("ships as-is with a non-blocking notice, not an
    # error") — informational, not counted in pass/fail.
    verify_note = (
        f"Verify loop reached satisfactory=true after {rounds_used} round(s)."
        if satisfactory
        else f"Verify loop hit the {rounds_used}-round cap without satisfactory=true — shipped best-effort per requirements.md's non-blocking rule (not a quality-check failure, but worth noting)."
    )

    return [header, f"- Verify loop: {verify_note}", *lines]
