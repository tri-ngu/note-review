"""Temporary orchestration helper (not part of the pipeline itself) — reruns
main() with backoff when Groq's daily token cap is only slowly refilling,
instead of failing after pipeline.py's internal per-call retry budget is
exhausted. Resets CALL_LOG/RATE_LIMIT_HITS between attempts so a failed
partial attempt's calls don't pollute the eventual successful run's
accounting. Prints one line per event for Monitor to pick up.
"""

import asyncio
import re
import sys
import time
from pathlib import Path

import call_agent
import pipeline

MAX_ATTEMPTS = 15
DEFAULT_WAIT = 300


def parse_wait_seconds(error_text: str) -> float | None:
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", error_text)
    if not m:
        return None
    hours, minutes, seconds = m.groups()
    return float(seconds) + int(minutes or 0) * 60 + int(hours or 0) * 3600 + 15


async def run_with_retry(concurrent: bool) -> None:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        call_agent.CALL_LOG.clear()
        call_agent.RATE_LIMIT_HITS = 0
        print(f"RETRY_RUNNER: attempt {attempt} starting (concurrent={concurrent})", flush=True)
        try:
            await pipeline.main(concurrent=concurrent)
            print(f"RETRY_RUNNER: SUCCESS on attempt {attempt}", flush=True)
            return
        except Exception as e:
            wait_s = parse_wait_seconds(str(e)) or DEFAULT_WAIT
            print(f"RETRY_RUNNER: attempt {attempt} failed ({type(e).__name__}: {str(e)[:150]}), waiting {wait_s:.0f}s", flush=True)
            time.sleep(wait_s)
    print(f"RETRY_RUNNER: GAVE UP after {MAX_ATTEMPTS} attempts", flush=True)


if __name__ == "__main__":
    concurrent = "--concurrent" in sys.argv
    asyncio.run(run_with_retry(concurrent))
