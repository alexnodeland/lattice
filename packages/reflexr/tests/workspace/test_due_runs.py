"""What storage finds due and what the claim accepts are one predicate, on every storage.

``Storage.due_runs`` selects the runs to attempt in one query, and the executor's claim checks
each again in its transaction with :func:`~reflexr.core.runnable`, which ADR-0041 keeps the
authority. This property generates scopes of runs in every status, with leases and rules of
every ordering, and holds storage's set of due runs to exactly the set the claim would accept.
It does not test the order of the due runs, or their limit.

The examples share one database, each in a workspace of its own, since a new database for each
would cost PostgreSQL its migrations every time. Each finishes its runs once it is compared, so
the next finds only its own due.
"""

import asyncio
import itertools
from collections.abc import AsyncGenerator, Iterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Literal

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from reflexr import Rule, on
from reflexr.core import Run, runnable
from reflexr.core.runs import RunStatus
from reflexr.sql import SqlStorage, create_schema
from reflexr.workspace import InMemoryStorage, RunPolicy, Storage, WorkspaceRef, run_lease
from tests.clock import START, FakeClock
from tests.databases import SQL_BACKENDS, empty_database
from tests.workspace.helpers import fired

MINUTE = timedelta(minutes=1)
NOW = START + timedelta(minutes=5)
"""When the due runs are asked for, after the leases were taken at ``START``."""

LEASES = st.sampled_from([MINUTE, timedelta(minutes=5), timedelta(minutes=10)])
"""A lease that lapsed before ``NOW``, one that lapses at ``NOW``, and one that has not."""


@dataclass(frozen=True)
class Spec:
    """One rule, as a test draws it."""

    ordering: Literal["scope", "none"]
    on_dead_letter: Literal["continue", "block"]
    enabled: bool

    def rule(self, name: str) -> Rule:
        return Rule.model_validate(
            {
                "name": name,
                "when": on("app:service.error"),
                "then": {"action": "act"},
                "ordering": self.ordering,
                "on_dead_letter": self.on_dead_letter,
                "enabled": self.enabled,
            }
        )


@dataclass(frozen=True)
class Draw:
    """One run, as a test draws it."""

    rule: int
    scope: int
    status: RunStatus
    due_in: timedelta
    lease: timedelta | None


SPECS = st.builds(
    Spec,
    ordering=st.sampled_from(["scope", "none"]),
    on_dead_letter=st.sampled_from(["continue", "block"]),
    enabled=st.booleans(),
)
DRAWS = st.builds(
    Draw,
    rule=st.integers(0, 1),
    scope=st.integers(0, 1),
    status=st.sampled_from(
        ["pending", "running", "retrying", "succeeded", "dead", "cancelled", "skipped"]
    ),
    due_in=st.sampled_from([-MINUTE, timedelta(0), MINUTE]),
    lease=st.none() | LEASES,
)


def build(rules: list[Rule], draws: list[Draw]) -> list[Run]:
    """The drawn runs, fired in the order drawn."""
    runs: list[Run] = []
    for seq, draw in enumerate(draws, start=1):
        base = fired(f"run_{seq}", rule=rules[draw.rule].name, scope=f"s{draw.scope}", seq=seq)
        runs.append(
            base.model_copy(
                update={
                    "status": draw.status,
                    "attempts": int(draw.status != "pending"),
                    "next_attempt_at": NOW + draw.due_in,
                }
            )
        )
    return runs


async def claimable(
    storage: Storage, ref: WorkspaceRef, rules: list[Rule], runs: list[Run], draws: list[Draw]
) -> set[str]:
    """The runs a claim would accept at ``NOW``, as the executor's claim decides."""
    found: set[str] = set()
    async with storage.transaction(ref) as transaction:
        for run, draw in zip(runs, draws, strict=True):
            rule = rules[draw.rule]
            if not rule.enabled or run.status in ("succeeded", "dead", "cancelled", "skipped"):
                continue
            if run.status == "running":
                if draw.lease is None or START + draw.lease <= NOW:
                    found.add(run.id)  # abandoned: its claim fails the attempt
            elif run.next_attempt_at <= NOW:  # pending or retrying
                scope = await transaction.scope_runs(run.rule, run.scope_key)
                if run.id in {r.id for r in runnable(scope, rule, now=NOW)}:
                    found.add(run.id)
    return found


@asynccontextmanager
async def storage_on(backend: str, directory: Path) -> AsyncGenerator[Storage]:
    """Empty storage on a backend, whose clock stands at ``START``."""
    clock = FakeClock()
    if backend == "memory":
        yield InMemoryStorage(clock=clock)
        return
    async with empty_database(backend, directory) as database:
        engine = database.engine()
        await create_schema(engine)
        yield SqlStorage(engine, clock=clock)


@dataclass
class Shared:
    """One storage for every example, on one event loop, and a new workspace for each example."""

    runner: asyncio.Runner
    storage: Storage
    workspaces: Iterator[WorkspaceRef]


@pytest.fixture(params=["memory", *SQL_BACKENDS])
def shared(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Shared]:
    with asyncio.Runner() as runner:
        stack = AsyncExitStack()
        storage = runner.run(stack.enter_async_context(storage_on(request.param, tmp_path)))
        try:
            yield Shared(
                runner, storage, (WorkspaceRef(f"t{n}", "prod") for n in itertools.count())
            )
        finally:
            runner.run(stack.aclose())


async def agree(storage: Storage, ref: WorkspaceRef, specs: list[Spec], draws: list[Draw]) -> None:
    rules = [spec.rule(f"app:r{i}") for i, spec in enumerate(specs)]
    runs = build(rules, draws)
    async with storage.transaction(ref) as transaction:
        await transaction.save_runs(runs)
    try:
        for run, draw in zip(runs, draws, strict=True):
            if draw.lease is not None:
                assert await storage.acquire_lease(ref, run_lease(run.id), "executor", draw.lease)
        # One more than there are, so that a run of another workspace would show.
        due = await storage.due_runs(now=NOW, limit=len(runs) + 1, policy=RunPolicy.of(rules))
        assert {at for at, _ in due} <= {ref}
        assert {run.id for _, run in due} == await claimable(storage, ref, rules, runs, draws)
    finally:  # nothing is left due for the examples after this one
        async with storage.transaction(ref) as transaction:
            await transaction.save_runs(
                [r.model_copy(update={"status": "succeeded"}) for r in runs]
            )


@settings(
    max_examples=200,
    deadline=None,
    # The storage is shared on purpose: each example works in a workspace of its own.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@example(  # a dead letter that blocks its scope, ahead of a run that is due
    specs=[Spec("scope", "block", True), Spec("none", "continue", True)],
    draws=[Draw(0, 0, "dead", -MINUTE, None), Draw(0, 0, "pending", -MINUTE, None)],
)
@example(  # a lease that lapses at the very instant the runs are asked for
    specs=[Spec("scope", "continue", True), Spec("none", "continue", True)],
    draws=[Draw(0, 0, "running", -MINUTE, timedelta(minutes=5))],
)
@given(specs=st.lists(SPECS, min_size=2, max_size=2), draws=st.lists(DRAWS, max_size=7))
def test_storage_finds_the_runs_a_claim_would_start(
    shared: Shared, specs: list[Spec], draws: list[Draw]
) -> None:
    shared.runner.run(agree(shared.storage, next(shared.workspaces), specs, draws))
