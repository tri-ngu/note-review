"""One-off runner: full pipeline against french_revolution_note.txt, plus a
full per-call transcript dump (input/output/tokens/time) for Tri's manual
review — pipeline.py's own log only writes a summary table, not full text.
"""
import asyncio
import datetime
from pathlib import Path

import call_agent
import pipeline

NOTE_PATH = Path(__file__).parent / "french_revolution_note.txt"
TRANSCRIPT_PATH = Path(__file__).parent / "french-revolution-transcript.md"


def dump_transcript(run_start: datetime.datetime, concurrent: bool) -> None:
    mode = "concurrent" if concurrent else "sequential"
    lines = [f"# French Revolution note — full call transcript ({run_start.isoformat(timespec='seconds')}, {mode})\n"]
    lines.append(f"Total calls: {len(call_agent.CALL_LOG)}\n")

    for i, e in enumerate(call_agent.CALL_LOG, start=1):
        lines.append(f"## Call {i}: `{e.label}`\n")
        lines.append(f"- Time: {e.elapsed_seconds:.1f}s | Tokens: {e.total_tokens} ({e.input_tokens} in / {e.output_tokens} out)\n")
        lines.append("**Input:**")
        lines.append("```")
        lines.append(e.input_text)
        lines.append("```\n")
        lines.append("**Actual output:**")
        lines.append("```")
        lines.append(e.output_text)
        lines.append("```\n")
        lines.append("**Expected output:** per `DESIGN.md`'s Expected behavior / Agent prompts contract for this agent+call-type (Analyzer / Generator initial / Generator patch / Verifier) — see that section for the general-contract checklist.\n")
        lines.append("**Notes:** _(Tri to fill in — pass/fail + comments)_\n")
        lines.append("---\n")

    TRANSCRIPT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote full call transcript to {TRANSCRIPT_PATH}")


async def run() -> None:
    concurrent = False
    run_start = datetime.datetime.now()
    await pipeline.main(NOTE_PATH, concurrent=concurrent)
    dump_transcript(run_start, concurrent)


if __name__ == "__main__":
    asyncio.run(run())
