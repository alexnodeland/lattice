"""What storage finds due and what the claim accepts are one predicate, on every storage.

``Storage.due_runs`` selects the runs to attempt in one query, and the executor's claim checks
each again in its transaction with :func:`~reflexr.core.runnable`. ADR-0041 has the claim
remain the authority, so storage may return too much but must never leave out a run the claim
would start, and it returns nothing the claim would refuse for the policy's reasons. This
property generates scopes of runs in every status, with leases and rules of every ordering, and
holds storage's answer to the claim's.
"""

import asyncio
import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Literal

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from reflexr import Rule
from reflexr.core import FINISHED, WAITING, Run, runnable
from reflexr.core.runs import RunStatus
from reflexr.sql import SqlStorage, create_schema
from reflexr.workspace import InMemoryStorage, RunPolicy, Storage, WorkspaceRef, run_lease
from tests.clock import START, FakeClock
from tests.core.test_runs import rule as make_rule
from tests.databases import SQL_BACKENDS, empty_database
from tests.workspace.helpers import fired

ACME = WorkspaceRef("acme", "prod")
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
    storage: Storage, rules: list[Rule], runs: list[Run], draws: list[Draw]
) -> set[str]:
    """The runs a claim would accept at ``NOW``, as the executor's claim decides."""
    found: set[str] = set()
    async with storage.transaction(ACME) as transaction:
        for run, draw in zip(runs, draws, strict=True):
            rule = rules[draw.rule]
            if not rule.enabled or run.status in FINISHED:
                continue
            if run.status == "running":
                if draw.lease is None or START + draw.lease <= NOW:
                    found.add(run.id)  # abandoned: its claim fails the attempt
            elif run.status in WAITING and run.next_attempt_at <= NOW:
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


async def agree(backend: str, directory: Path, specs: list[Spec], draws: list[Draw]) -> None:
    rules = [
        make_rule(
            name=f"app:r{i}",
            ordering=spec.ordering,
            on_dead_letter=spec.on_dead_letter,
            enabled=spec.enabled,
        )
        for i, spec in enumerate(specs)
    ]
    runs = build(rules, draws)
    async with storage_on(backend, directory) as storage:
        async with storage.transaction(ACME) as transaction:
            await transaction.save_runs(runs)
        for run, draw in zip(runs, draws, strict=True):
            if draw.lease is not None:
                assert await storage.acquire_lease(ACME, run_lease(run.id), "executor", draw.lease)
        due = await storage.due_runs(now=NOW, limit=len(runs), policy=RunPolicy.of(rules))
        assert {run.id for _, run in due} == await claimable(storage, rules, runs, draws)


@pytest.mark.parametrize("backend", ["memory", *SQL_BACKENDS])
@settings(max_examples=200, deadline=None)
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
    backend: str, specs: list[Spec], draws: list[Draw]
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        asyncio.run(agree(backend, Path(directory), specs, draws))
