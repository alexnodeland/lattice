# ADR-0007: A timeout on every test and every job

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

## Context

[RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md#phases) put pytest-timeout and `timeout-minutes` in phase 6, after the move. Phase 6 holds everything that can change test outcomes, so that each lands in its own pull request and is judged alone.

On the day, docplan's tests hung in CI's Check job on [#2](https://github.com/alexnodeland/lattice/pull/2) and [#3](https://github.com/alexnodeland/lattice/pull/3), for 42 and 30 minutes, until they were cancelled by hand. The same tests, with the same inputs, passed in 50 seconds on [#1](https://github.com/alexnodeland/lattice/pull/1), and locally in 5 to 19 seconds, on macOS and on Linux, alone and on half a CPU. moon shows a task's output only when the task ends, so CI never said where they stopped, and a hung job would have held its runner for GitHub's six hours.

## Decision

Phase 6's timeouts landed on the day, in their own pull request ([#4](https://github.com/alexnodeland/lattice/pull/4)):

- **A test that runs for a minute fails.** Every Python project's pytest configuration, and the root's, sets `timeout = 60` and `timeout_method = "thread"`, so the failure prints every thread's stack. The slowest test today takes a few seconds.
- **Every job that runs on a runner has `timeout-minutes`,** a few times its usual length: 20 minutes for CI's Check, Tests, Images and Template, 30 for Smoke, and a limit of its own for every other job. The OSV jobs call a reusable workflow, which takes no job-level limit.
- **A hang becomes an issue,** with the stack the timeout printed.

## Options considered

| Option | A hung test | What CI says |
|---|---|---|
| **Both timeouts now (chosen)** | Fails in a minute | The test, and every thread's stack |
| Wait for phase 6, as planned | Holds its job until someone cancels it, or for six hours | Nothing |
| `timeout-minutes` alone | Fails its job at the limit | Which job, not which test |

## Trade-off analysis

A timeout can fail a test that would have passed slowly, which is why RFC-0003 kept it for phase 6. Nothing in the family takes more than a few seconds, and a hung job already failed the pull request and everything queued behind it. Landing the timeouts alone, in their own pull request, kept phase 6's rule that each such change is judged on its own.

## Consequences

- Easier: a stuck test fails in a minute and says where it is stuck, and a stuck job frees its runner.
- It paid off at once: the next hang printed both event loops idle in `select()`, which found the cause, a message posted as a run ends that gets no reply ([#29](https://github.com/alexnodeland/lattice/issues/29)).
- Harder: a test that needs more than a minute says so with its own `pytest.mark.timeout`.
- Phase 6 still brings the rest of its list, each in its own pull request.
