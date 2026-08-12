"""Offline unit tests for generator_pool.py's dispatch/failover mechanics —
no live agent calls, no dependency on call_agent.py (fake model names).
Run directly: python test_generator_pool_unit.py"""

import asyncio
import time

from generator_pool import GeneratorPoolError, Job, drain_pool

MODEL_A = "fake-model-a"
MODEL_B = "fake-model-b"


def _log(msg: str) -> None:
    pass  # unit tests don't need the log output


async def _run_dynamic_dispatch_test() -> None:
    handled_by: dict[str, str] = {}

    def make_attempt(key: str):
        async def attempt(model_name: str):
            await asyncio.sleep(0.05)
            handled_by[key] = model_name
            return f"{key}-result"
        return attempt

    jobs = [Job(key=f"concept-{i}", attempt=make_attempt(f"concept-{i}")) for i in range(4)]

    start = time.monotonic()
    results = await drain_pool(jobs, (MODEL_A, MODEL_B), _log, "test-initial")
    elapsed = time.monotonic() - start

    assert set(results.keys()) == {j.key for j in jobs}, results
    assert all(v.endswith("-result") for v in results.values()), results
    # 4 jobs x 0.05s each, drained by 2 workers concurrently -> ~0.10s, not ~0.20s serial.
    assert elapsed < 0.18, f"expected concurrent drain (~0.10s), took {elapsed:.3f}s"
    assert set(handled_by.values()) == {MODEL_A, MODEL_B}, (
        f"expected both models to handle at least one job, got {handled_by}"
    )


async def _run_failover_test() -> None:
    attempts_on: dict[str, list[str]] = {"flaky": []}

    async def flaky_attempt(model_name: str):
        attempts_on["flaky"].append(model_name)
        if model_name == MODEL_A:
            raise RuntimeError("simulated failure on model A")
        return "flaky-result"

    async def normal_attempt(model_name: str):
        return "normal-result"

    jobs = [Job(key="flaky", attempt=flaky_attempt), Job(key="normal", attempt=normal_attempt)]
    results = await drain_pool(jobs, (MODEL_A, MODEL_B), _log, "test-failover")

    assert results["flaky"] == "flaky-result", results
    assert results["normal"] == "normal-result", results
    # The flaky job must have been tried on model A first (and failed) before
    # succeeding on model B -- proves the requeue-to-the-other-worker path ran.
    assert MODEL_A in attempts_on["flaky"], attempts_on
    assert MODEL_B in attempts_on["flaky"], attempts_on


async def _run_total_failure_test() -> None:
    async def always_fails(model_name: str):
        raise RuntimeError(f"simulated failure on {model_name}")

    async def ok(model_name: str):
        return "ok"

    jobs = [Job(key="doomed", attempt=always_fails), Job(key="fine", attempt=ok)]

    try:
        await drain_pool(jobs, (MODEL_A, MODEL_B), _log, "test-total-failure")
    except GeneratorPoolError as e:
        assert "doomed" in str(e), str(e)
    else:
        raise AssertionError("expected GeneratorPoolError when a job fails on every model")


def main() -> None:
    tests = [
        ("dynamic dispatch across both models", _run_dynamic_dispatch_test),
        ("failover to the other worker on failure", _run_failover_test),
        ("GeneratorPoolError when a job fails on every model", _run_total_failure_test),
    ]
    failures = []
    for name, coro_fn in tests:
        try:
            asyncio.run(coro_fn())
            print(f"PASS: {name}")
        except Exception as e:
            failures.append((name, e))
            print(f"FAIL: {name}: {e}")
    if failures:
        raise SystemExit(f"{len(failures)}/{len(tests)} tests failed")
    print(f"All {len(tests)} tests passed.")


if __name__ == "__main__":
    main()
