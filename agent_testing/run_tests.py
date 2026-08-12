"""Runs every handwritten test case in test_inputs.py against the live
Groq-backed agents (call_agent.py), parses each response (parsers.py),
validates it against models.py + DESIGN.md's Expected behavior contracts,
and appends a dated run section to agent-test-log.md.

Calls run sequentially (not concurrent) — this is isolated per-call tuning,
not the pipeline's fan-out, so there's no need to fight rate limits here.
"""

import asyncio
import datetime
import sys
from pathlib import Path

from pydantic import ValidationError

import test_inputs as ti
from call_agent import (
    CALL_LOG,
    analyzer_agent,
    build_generator_initial_prompt,
    build_generator_patch_prompt,
    build_verifier_prompt,
    call_agent_async,
    format_snippets,
    generator_initial_agent,
    generator_patch_agent,
    verifier_agent,
)
from models import Question
from pipeline import ANALYZER_MAX_TOKENS
from parsers import (
    ParseError,
    is_exact_substring,
    parse_analyzer_output,
    parse_generator_initial_output,
    parse_generator_patch_output,
    parse_verifier_output,
)

LOG_PATH = Path(__file__).parent / "agent-test-log.md"


def fmt_question_block(idx: int, q: Question, extra: dict[str, str] | None = None) -> str:
    lines = [
        f"index: {idx}",
        f'question_text: "{q.question_text}"',
        f"options: {q.options}",
        f"correct_answers: {q.correct_answers}",
        f"is_select_all: {'true' if q.is_select_all else 'false'}",
        f'explanation: "{q.explanation}"',
        f"page_number: {q.page_number}",
        f'source_quote: "{q.source_quote}"',
    ]
    if extra:
        for k, v in extra.items():
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


def md_escape(s: str) -> str:
    return s.replace("|", "\\|")


def tokens_line() -> str:
    e = CALL_LOG[-1]
    return f"- **Tokens**: {e.total_tokens} ({e.input_tokens} input, {e.output_tokens} output)\n"


async def run_analyzer_cases(sections: list[str]) -> None:
    for case in ti.ANALYZER_CASES:
        start = datetime.datetime.now()
        raw = await call_agent_async(analyzer_agent, case["note_text"], case["label"], max_tokens=ANALYZER_MAX_TOKENS)
        elapsed = (datetime.datetime.now() - start).total_seconds()

        notes = []
        try:
            parsed = parse_analyzer_output(raw)
            weight_sum = sum(c["weight_percentage"] for c in parsed)
            notes.append(f"Parsed OK: {len(parsed)} concepts, weight sum = {weight_sum:.2f}")
            if abs(weight_sum - 100) > 10:
                notes.append(f"CONTRACT VIOLATION: weight sum drift {weight_sum - 100:+.2f} exceeds ±10")
            for c in parsed:
                for snip in c["snippets"]:
                    if not is_exact_substring(snip.quote, case["note_text"]):
                        notes.append(f"CONTRACT VIOLATION: snippet not an exact substring of Note — {snip.quote[:80]!r}")
            concepts_str = ", ".join(c["concept"] for c in parsed)
            notes.append(f"Concepts: {concepts_str}")
        except (ParseError, ValidationError) as e:
            notes.append(f"PARSE/VALIDATION FAILURE: {e}")

        sections.append(
            f"### Analyzer — `{case['label']}`\n\n"
            f"- **Time**: {start.isoformat(timespec='seconds')} ({elapsed:.1f}s)\n"
            f"{tokens_line()}"
            f"- **Input**: note_text ({len(case['note_text'])} chars)\n"
            f"- **Expected**: weights sum to ~100 (±10), non-overlapping Concepts, all snippets verbatim substrings — see DESIGN.md Expected behavior\n"
            f"- **Actual output**:\n```\n{raw}\n```\n"
            f"- **Notes**: {'; '.join(notes)}\n"
        )


async def run_generator_initial_cases(sections: list[str]) -> None:
    for case in ti.GENERATOR_INITIAL_CASES:
        prompt = build_generator_initial_prompt(case["concept"], case["question_count"], case["snippets"])
        start = datetime.datetime.now()
        raw = await call_agent_async(generator_initial_agent, prompt, case["label"])
        elapsed = (datetime.datetime.now() - start).total_seconds()

        notes = []
        try:
            questions = parse_generator_initial_output(raw, case["concept"])
            notes.append(f"Parsed OK: {len(questions)} Questions (requested {case['question_count']})")
            if len(questions) != case["question_count"]:
                notes.append("CONTRACT VIOLATION: Question count mismatch")
            snippet_texts = [s[0] for s in case["snippets"]]
            for q in questions:
                if not any(is_exact_substring(q.source_quote, s) for s in snippet_texts):
                    notes.append(f"CONTRACT VIOLATION: source_quote not a substring of any given snippet — {q.source_quote[:80]!r}")
        except (ParseError, ValidationError) as e:
            notes.append(f"PARSE/VALIDATION FAILURE: {e}")

        sections.append(
            f"### Generator (initial pass) — `{case['label']}`\n\n"
            f"- **Time**: {start.isoformat(timespec='seconds')} ({elapsed:.1f}s)\n"
            f"{tokens_line()}"
            f"- **Input**: concept={case['concept']!r}, question_count={case['question_count']}, snippets={[s[0][:60] + '...' for s in case['snippets']]}\n"
            f"- **Expected**: exactly {case['question_count']} Questions, each with source_quote an exact substring of a given snippet — see DESIGN.md Expected behavior\n"
            f"- **Actual output**:\n```\n{raw}\n```\n"
            f"- **Notes**: {'; '.join(notes)}\n"
        )


async def run_generator_patch_cases(sections: list[str]) -> None:
    for case in ti.GENERATOR_PATCH_CASES:
        flagged_text = "\n\n".join(
            fmt_question_block(
                idx,
                flag["question"],
                extra={"critique": f'"{flag["critique"]}"', "fix_snippets": format_snippets(flag["snippets"])},
            )
            for idx, flag in case["flags"].items()
        )
        prompt = build_generator_patch_prompt(case["concept"], flagged_text)
        start = datetime.datetime.now()
        raw = await call_agent_async(generator_patch_agent, prompt, case["label"])
        elapsed = (datetime.datetime.now() - start).total_seconds()

        notes = []
        expected_indices = set(case["flags"].keys())
        try:
            patched = parse_generator_patch_output(raw, case["concept"])
            notes.append(f"Parsed OK: returned indices {sorted(patched.keys())} (expected {sorted(expected_indices)})")
            if set(patched.keys()) != expected_indices:
                notes.append("CONTRACT VIOLATION: returned index set doesn't match flagged index set")
            for idx, flag in case["flags"].items():
                if idx not in patched:
                    continue
                fix_snippet_texts = [s[0] for s in flag["snippets"]]
                q = patched[idx]
                if not any(is_exact_substring(q.source_quote, s) for s in fix_snippet_texts):
                    notes.append(f"CONTRACT VIOLATION (index {idx}): source_quote not a substring of the new fix snippets — {q.source_quote[:80]!r}")
        except (ParseError, ValidationError) as e:
            notes.append(f"PARSE/VALIDATION FAILURE: {e}")

        sections.append(
            f"### Generator (patch pass) — `{case['label']}`\n\n"
            f"- **Time**: {start.isoformat(timespec='seconds')} ({elapsed:.1f}s)\n"
            f"{tokens_line()}"
            f"- **Input**: concept={case['concept']!r}, flagged indices={sorted(case['flags'].keys())}\n"
            f"- **Expected**: output contains exactly the flagged indices, each once; new source_quote grounded in the *fix* snippets, not the original — see DESIGN.md Expected behavior\n"
            f"- **Actual output**:\n```\n{raw}\n```\n"
            f"- **Notes**: {'; '.join(notes)}\n"
        )


async def run_verifier_cases(sections: list[str]) -> None:
    for case in ti.VERIFIER_CASES:
        questions_text = "\n\n".join(fmt_question_block(idx, q) for idx, q in case["questions"].items())
        prompt = build_verifier_prompt(case["note_text"], case["concept"], questions_text)
        start = datetime.datetime.now()
        raw = await call_agent_async(verifier_agent, prompt, case["label"])
        elapsed = (datetime.datetime.now() - start).total_seconds()

        notes = []
        try:
            issues, satisfactory = parse_verifier_output(raw)
            got_actions = {i.index: i.action for i in issues}
            notes.append(f"Parsed OK: {len(issues)} verdicts, satisfactory={satisfactory}")
            missing = set(case["questions"].keys()) - set(got_actions.keys())
            if missing:
                notes.append(f"CONTRACT VIOLATION: missing verdicts for indices {sorted(missing)}")
            mismatches = []
            for idx, expected_action in case["expected_actions"].items():
                got = got_actions.get(idx)
                mark = "OK" if got == expected_action else "MISMATCH"
                if got != expected_action:
                    mismatches.append(f"index {idx}: expected {expected_action}, got {got}")
                notes.append(f"idx {idx}: expected={expected_action} actual={got} [{mark}]")
            for i in issues:
                if i.action == "patch":
                    for snip in i.snippets:
                        if not is_exact_substring(snip.quote, case["note_text"]):
                            notes.append(f"CONTRACT VIOLATION: fix snippet for index {i.index} not an exact substring of Note — {snip.quote[:80]!r}")
        except (ParseError, ValidationError) as e:
            notes.append(f"PARSE/VALIDATION FAILURE: {e}")

        sections.append(
            f"### Verifier — `{case['label']}`\n\n"
            f"- **Time**: {start.isoformat(timespec='seconds')} ({elapsed:.1f}s)\n"
            f"{tokens_line()}"
            f"- **Input**: concept={case['concept']!r}, indices={sorted(case['questions'].keys())} "
            f"(expected actions: {case['expected_actions']})\n"
            f"- **Expected**: happy-path indices -> keep, adversarial indices -> patch — see DESIGN.md Expected behavior\n"
            f"- **Actual output**:\n```\n{raw}\n```\n"
            f"- **Notes**: {'; '.join(notes)}\n"
        )


async def main() -> None:
    sections: list[str] = []
    run_start = datetime.datetime.now()

    await run_analyzer_cases(sections)
    await run_generator_initial_cases(sections)
    await run_generator_patch_cases(sections)
    await run_verifier_cases(sections)

    total_input = sum(e.input_tokens for e in CALL_LOG)
    total_output = sum(e.output_tokens for e in CALL_LOG)
    total = sum(e.total_tokens for e in CALL_LOG)
    header = (
        f"\n## Run {run_start.isoformat(timespec='seconds')}\n\n"
        f"**Total agent calls this run**: {len(CALL_LOG)}. "
        f"**Total tokens**: {total} ({total_input} input, {total_output} output).\n\n"
    )
    body = header + "\n".join(sections)

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(body)
        f.write("\n---\n")

    print(f"Appended {len(sections)} test entries to {LOG_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
