# ADR-0028: A stuck test fails by a signal, and its worker carries on

**Status:** Accepted
**Date:** 2026-10-21
**Deciders:** Alex Nodeland
**Amends:** [ADR-0007](0007-a-timeout-on-every-test-and-every-job.md), whose timeout printed every thread's stack

## Context

[ADR-0007](0007-a-timeout-on-every-test-and-every-job.md) fails a test that runs for a minute, with pytest-timeout's `thread` method, which prints every thread's stack and then ends the process. Since artifactr's, relayr's and grantr's tests run in pytest-xdist's workers ([ADR-0010](0010-every-projects-tests-run-in-a-random-order.md)'s note of 2026-10-21), ending the process ends a worker: xdist says only "worker crashed", the stack goes to the worker's stderr, which xdist doesn't show, and the worker's coverage is lost, so the 100% gate fails too. On CI's four cores, several projects' workers and PostgreSQL share the runner, and a slow test, relayr's thousand installs, crossed the minute and failed three merge-queue drafts this way (#503).

## Decision

- **Every Python project's pytest configuration but stackr's, which has none, and the root's, sets `timeout_method = "signal"`.** A test past its timeout gets `SIGALRM`, which pytest-timeout turns into a failure of that test, with its traceback, in the process that ran it; the worker carries on, and its coverage is kept. The minute stays.
- **It holds where lattice's tests run:** xdist runs each test on its worker's main thread, where the signal is delivered, and an asynchronous test's event loop is interrupted the same way. Checked with a test that hangs in `asyncio.sleep`, in `time.sleep`, joining a thread, and awaiting `asyncio.to_thread`: under `-n 2` each failed as `Timeout (>1.0s)`, where the thread method crashed every worker. Where a test runs off the main thread, pytest-timeout uses the thread method itself. No test or library of lattice's uses `SIGALRM`.
- **Each run lists its ten slowest tests:** every moon task that runs pytest passes `--durations=10`, so how near any comes to the minute is in every CI log, not found after a crash. A test that needs longer says so with its own `pytest.mark.timeout`, and why.
- **A Hypothesis test that needs longer keeps the thread method,** `pytest.mark.timeout(N, method="thread")`. The signal's timer fires once; Hypothesis takes the timeout for a failure, then replays and shrinks it with no timer running. Checked: two `@given` tests that hang, with a timeout of 2 s, under `-n 2`, failed as Hypothesis's `FlakyFailure`, the timeout inside it, after 93 s between them; one that hangs for good would wait for its job's `timeout-minutes`. With the thread method a hang ends its worker at the timeout, which bounds it; with a timeout of minutes, that is only ever a hang, never a slow run.
- **macOS and Linux only:** Windows has no `SIGALRM`, and pytest-timeout fails there with the signal method. lattice's tests run on macOS and Linux, in the dev container, or through uv and moon, as CI's runners do.

## Options considered

| Option | A test past its minute | What CI says |
|---|---|---|
| **`signal` (chosen)** | Fails alone; its worker carries on | The test, its traceback, the rest of the run's results and coverage |
| `thread`, as before | Ends its worker | "worker crashed", and coverage short of the gate |
| `thread`, and fewer workers | As before, less often | As before |

## Trade-off analysis

The thread method's strength was every thread's stack: it found the first hang ADR-0007 records. Under xdist that stack goes to the worker's stderr, which xdist doesn't show, and the worker is lost with it. The signal method's failure carries the stuck test's own traceback, which for an asynchronous test is the await it is stuck on; it writes the other threads' stacks too (pytest-timeout's `dump_stacks`, to the worker's terminal), where xdist doesn't show them either.

## Consequences

- Easier: a slow or stuck test is a failure that names itself, and a run never loses a worker's coverage to it.
- Harder: another thread's stack is written where xdist doesn't show it; a hang there is found by running the test alone with `-o timeout_method=thread`, or with `-n0`.
- Harder: a hung `@given` test without a mark of its own is replayed past its timeout, and fails late, as `FlakyFailure`.
- A test stuck in an executor thread fails at its minute, and its run waits for that thread as its event loop closes.
