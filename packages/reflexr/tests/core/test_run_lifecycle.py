"""The run lifecycle as a state machine: random transitions against its table of legal ones.

The machine drives the pure transitions of one rule's scope, and after every step checks what
ADR-0005, ADR-0041 and the lifecycle's diagram (``reflexr.core.runs``) claim of them: a
transition from a status outside its table is refused, attempts only grow except when a retry
gives a finished run a fresh budget, and ``runnable`` starts a run only if no earlier run of
its scope holds it. The table and the scope rule are written out again here rather than
imported, so that a change to either shows up.

It also keeps every attempt ever started, by the epoch it started at (ADR-0066), and completes
any of them at random, as a stale executor would after a cancel, a retry, a skip or a lapsed
lease: only the attempt the machine itself knows to be the run's current one may record.
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any, Literal

import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    precondition,
    rule,
)

from reflexr.core import (
    InvalidState,
    Rule,
    Run,
    RunCancelled,
    RunDeadLettered,
    RunRequeued,
    RunRetrying,
    RunSkipped,
    RunStarted,
    RunSucceeded,
    cancel,
    checkpoint,
    fail,
    holds,
    on,
    retry,
    runnable,
    skip,
    start,
    succeed,
)
from reflexr.core.runs import RunStatus
from reflexr.workspace import RunPolicy
from tests.clock import START
from tests.workspace.helpers import fired

LEGAL: dict[str, dict[RunStatus, RunStatus | tuple[RunStatus, ...]]] = {
    "start": {"pending": "running", "retrying": "running"},
    "succeed": {"running": "succeeded"},
    "fail": {"running": ("retrying", "dead")},
    "checkpoint": {"running": "running"},
    "cancel": {
        "pending": "cancelled",
        "running": "cancelled",
        "retrying": "cancelled",
        "dead": "cancelled",
    },
    "skip": {"pending": "skipped", "retrying": "skipped", "dead": "skipped"},
    "retry": {
        "pending": "pending",
        "retrying": "pending",
        "dead": "pending",
        "cancelled": "pending",
        "skipped": "pending",
    },
}
"""Each transition, the statuses it may begin in, and where it ends: the lifecycle's diagram, and
a retry of a run that is already pending."""

FACTS = {
    "start": RunStarted,
    "succeed": RunSucceeded,
    "cancel": RunCancelled,
    "skip": RunSkipped,
    "retry": RunRequeued,
}
"""The fact each transition appends, except ``fail``'s, which says which way it went."""

FINISHED: frozenset[RunStatus] = frozenset({"succeeded", "dead", "cancelled", "skipped"})
"""The statuses a retry gives a fresh budget to."""

MAX_RUNS = 4


class RunLifecycle(RuleBasedStateMachine):
    """Runs of one rule and scope, in firing order, and the transitions applied to them."""

    def __init__(self) -> None:
        super().__init__()
        self.runs: list[Run] = []
        self.started: list[list[int]] = []
        """The epoch of every attempt each run has started, in order."""
        self.current: list[int | None] = []
        """The epoch of the attempt each run is running, if it is running one."""
        self.now = START
        self.ordering: Literal["scope", "none"] = "scope"
        self.on_dead_letter: Literal["continue", "block"] = "continue"
        self.max_attempts = 1

    @property
    def governing(self) -> Rule:
        return Rule.model_validate(
            {
                "name": "app:r",
                "when": on("app:service.error"),
                "then": {"action": "act"},
                "ordering": self.ordering,
                "on_dead_letter": self.on_dead_letter,
                "retry": {"max_attempts": self.max_attempts, "backoff": timedelta(seconds=1)},
            }
        )

    @initialize(
        ordering=st.sampled_from(["scope", "none"]),
        on_dead_letter=st.sampled_from(["continue", "block"]),
        max_attempts=st.integers(1, 3),
    )
    def configure(
        self,
        ordering: Literal["scope", "none"],
        on_dead_letter: Literal["continue", "block"],
        max_attempts: int,
    ) -> None:
        self.ordering, self.on_dead_letter, self.max_attempts = (
            ordering,
            on_dead_letter,
            max_attempts,
        )
        self.fire()

    @precondition(lambda self: len(self.runs) < MAX_RUNS)
    @rule()
    def fire(self) -> None:
        seq = len(self.runs) + 1
        self.runs.append(fired(f"run_{seq}", rule="app:r", seq=seq))
        self.started.append([])
        self.current.append(None)

    @rule(seconds=st.sampled_from([0, 1, 60]))
    def tick(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)

    @rule(index=st.integers(0))
    def start_a_run(self, index: int) -> None:
        self.step("start", index, lambda run: start(run, now=self.now))

    @rule(index=st.integers(0))
    def succeed_a_run(self, index: int) -> None:
        self.step("succeed", index, lambda run: succeed(run, now=self.now))

    @rule(index=st.integers(0), permanent=st.booleans())
    def fail_a_run(self, index: int, permanent: bool) -> None:
        def failing(run: Run) -> tuple[Run, Any]:
            return fail(run, self.governing, now=self.now, error="x", permanent=permanent)

        step = self.step("fail", index, failing)
        if step is not None:
            before, after, fact = step
            exhausted = permanent or before.attempts >= self.max_attempts
            assert after.status == ("dead" if exhausted else "retrying")
            assert isinstance(fact, RunDeadLettered if exhausted else RunRetrying)
            if not exhausted:
                assert after.next_attempt_at > self.now

    @rule(index=st.integers(0), which=st.integers(0), succeeds=st.booleans())
    def complete_an_attempt(self, index: int, which: int, succeeds: bool) -> None:
        """Complete any attempt ever started, as its executor would, fenced by its epoch."""
        position = index % len(self.runs)
        started = self.started[position]
        if not started:
            return
        epoch = started[which % len(started)]
        current = self.current[position] == epoch
        assert self.runs[position].is_running(epoch) == current
        if not current:
            return  # a stale attempt: its executor discards its outcome
        if succeeds:
            self.succeed_a_run(position)
        else:
            self.fail_a_run(position, permanent=False)

    @rule(index=st.integers(0))
    def checkpoint_a_run(self, index: int) -> None:
        self.step("checkpoint", index, lambda run: checkpoint(run, now=self.now, step="s", state=0))

    @rule(index=st.integers(0))
    def cancel_a_run(self, index: int) -> None:
        self.step("cancel", index, lambda run: cancel(run, now=self.now))

    @rule(index=st.integers(0))
    def skip_a_run(self, index: int) -> None:
        self.step("skip", index, lambda run: skip(run, now=self.now))

    @rule(index=st.integers(0))
    def retry_a_run(self, index: int) -> None:
        step = self.step("retry", index, lambda run: retry(run, now=self.now))
        if step is not None:
            assert step[1].next_attempt_at == self.now

    def step(
        self, name: str, index: int, transition: Callable[[Run], tuple[Run, Any]]
    ) -> tuple[Run, Run, Any] | None:
        """Apply a transition to a run, and check it against the table."""
        position = index % len(self.runs)
        before = self.runs[position]
        legal = LEGAL[name]
        if before.status not in legal:
            with pytest.raises(InvalidState):
                transition(before)
            return None
        after, fact = transition(before)
        expected = legal[before.status]
        assert after.status in ((expected,) if isinstance(expected, str) else expected)
        if name in FACTS:
            assert isinstance(fact, FACTS[name])
        assert fact.run_id == before.id
        # Attempts only grow, by a start; a retry gives a finished run a fresh budget.
        if name == "retry" and before.status in FINISHED:
            assert after.attempts == 0
        else:
            assert after.attempts == before.attempts + (name == "start")
        # The epoch only grows, by a start, whatever else happens.
        assert after.epoch == before.epoch + (name == "start")
        if name == "start":
            assert after.epoch not in self.started[position]
            self.started[position].append(after.epoch)
            self.current[position] = after.epoch
        elif after.status != "running":
            self.current[position] = None
        self.runs[position] = after
        return before, after, fact

    @invariant()
    def attempts_stay_within_the_retry_budget(self) -> None:
        for run in self.runs:
            assert 0 <= run.attempts <= self.max_attempts
            assert run.attempts >= 1 or run.status not in ("running", "retrying", "dead")

    @invariant()
    def the_epoch_is_the_latest_attempts(self) -> None:
        for run, started in zip(self.runs, self.started, strict=True):
            assert run.epoch == (started[-1] if started else 0)
            assert run.epoch >= run.attempts

    @invariant()
    def only_runs_with_no_earlier_holder_start(self) -> None:
        blocks = self.on_dead_letter == "block"

        def holding(run: Run) -> bool:
            return run.status in ("pending", "retrying", "running") or (
                blocks and run.status == "dead"
            )

        waiting = [r for r in self.runs if r.status != "succeeded"]
        expected = [
            run
            for i, run in enumerate(waiting)
            if run.status in ("pending", "retrying")
            and run.next_attempt_at <= self.now
            and (self.ordering == "none" or not any(holding(earlier) for earlier in waiting[:i]))
        ]
        assert runnable(waiting, self.governing, now=self.now) == expected
        policy = RunPolicy.of([self.governing])
        for run in self.runs:
            assert holds(run, blocking=blocks) == holding(run)
            assert policy.holds(run) == (self.ordering == "scope" and holding(run))

    @invariant()
    def a_blocking_dead_letter_holds_its_scope(self) -> None:
        """ADR-0041's words, stated on their own rather than through the model's ``holding``."""
        if (self.ordering, self.on_dead_letter) != ("scope", "block"):
            return
        waiting = [r for r in self.runs if r.status != "succeeded"]
        started = {run.id for run in runnable(waiting, self.governing, now=self.now)}
        for i, run in enumerate(waiting):
            if run.status == "dead":
                assert not started & {later.id for later in waiting[i:]}


RunLifecycle.TestCase.settings = settings(max_examples=100, stateful_step_count=40, deadline=None)
TestRunLifecycle = RunLifecycle.TestCase
