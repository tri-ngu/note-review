"""Two-worker Generator pool — dispatches Generator jobs (one per Concept for
the initial pass, one per flagged Concept per patch round) across a fixed set
of workers, each bound to its own model, per
docs/superpowers/specs/2026-08-12-dual-model-generator-design.md.

Fully generic: knows nothing about Concepts, Questions, or prompts — callers
(pipeline.py) supply a `Job` per unit of work, each carrying its own
`attempt(model_name) -> result` coroutine (built from pipeline.py's existing
per-concept generation/patch logic, parameterized by which model's Agent to
call). This module owns only the dispatch/failover mechanics.

Failover: a job that fails on one model (after that model's own standard
per-call retry/backoff, inside `attempt` itself) is requeued for the other
worker to try fresh, on its own model, with its own full retry/backoff. A job
that fails on every model in `model_names` is recorded as a failure; if any
job fails on every model, `drain_pool` raises `GeneratorPoolError` only after
every job has been resolved one way or another (never gives up early leaving
other jobs unattempted) — the caller (pipeline.py) is expected to translate
that into its own `PipelineError`.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Sequence


class GeneratorPoolError(Exception):
    """Raised by drain_pool when one or more jobs failed on every model."""


@dataclass
class Job:
    key: str  # unique per drain_pool call (e.g. Concept name) — identifies this job in the result dict
    attempt: Callable[[str], Awaitable[Any]]  # attempt(model_name) -> result; raises on failure for that model
    tried_models: set[str] = field(default_factory=set)


async def drain_pool(
    jobs: list[Job],
    model_names: Sequence[str],
    log_fn: Callable[[str], None],
    stage_label: str,
    on_result: Callable[[str, Any], None] | None = None,
) -> dict[str, Any]:
    """Runs exactly one worker per entry in `model_names`, all draining the
    same shared `jobs` list concurrently, until every job has either
    succeeded or failed on every model. Returns {job.key: result} for every
    job that succeeded on some model.

    `on_result`, when given, is called synchronously (job.key, result) the
    moment each job succeeds — lets a caller stream per-job progress (e.g.
    an SSE event per Concept) without waiting for every job in the pool to
    finish first. Must not block/await; a queue.put_nowait-style call is
    the intended use."""
    pending = list(jobs)
    lock = asyncio.Lock()
    cond = asyncio.Condition(lock)
    in_flight = 0
    results: dict[str, Any] = {}
    failures: dict[str, Exception] = {}

    async def worker(model_name: str) -> None:
        nonlocal in_flight
        while True:
            async with cond:
                job = None
                while job is None:
                    for i, candidate in enumerate(pending):
                        if model_name not in candidate.tried_models:
                            job = pending.pop(i)
                            break
                    if job is not None:
                        in_flight += 1
                        break
                    if not pending and in_flight == 0:
                        return
                    await cond.wait()

            try:
                result = await job.attempt(model_name)
            except Exception as e:
                async with cond:
                    in_flight -= 1
                    job.tried_models.add(model_name)
                    if len(job.tried_models) >= len(model_names):
                        failures[job.key] = e
                        log_fn(
                            f"{stage_label} [{job.key}]: failed on every model "
                            f"({sorted(job.tried_models)}) — {e}"
                        )
                    else:
                        pending.append(job)
                        log_fn(
                            f"{stage_label} [{job.key}]: failed on {model_name} "
                            f"({e}), requeued for the other worker"
                        )
                    cond.notify_all()
                continue

            async with cond:
                in_flight -= 1
                results[job.key] = result
                if on_result is not None:
                    on_result(job.key, result)
                cond.notify_all()

    await asyncio.gather(*(worker(m) for m in model_names))

    if failures:
        detail = "; ".join(f"{k}: {v}" for k, v in failures.items())
        raise GeneratorPoolError(f"{stage_label}: job(s) failed on every model — {detail}")

    return results
