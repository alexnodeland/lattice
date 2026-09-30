"""Turns from the log across processes: two runners, each with its own engine on PostgreSQL."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from pydantic_ai import DeferredToolRequests

from artifactr.sql import SqlStorage, create_schema
from artifactr.workspace import Scope, Workspace, Workspaces
from tests.agent.conftest import (
    ALICE,
    Gate,
    MakeRunner,
    Script,
    call,
    make_agent,
    say,
    settled,
    started,
)
from tests.databases import empty_database

pytestmark = pytest.mark.postgres

ASKING = [str, DeferredToolRequests]


class HeldSqlRelease(SqlStorage):
    """SQL storage that holds the release of thread claims at ``held``, once a test sets it."""

    held: Gate | None = None

    async def release_lease(self, scope: Scope, key: str, holder: str) -> None:
        if self.held is not None:
            await self.held.wait()
        await super().release_lease(scope, key, holder)


@pytest.fixture
async def processes(tmp_path: Path) -> AsyncIterator[tuple[HeldSqlRelease, Workspace, Workspace]]:
    """One database, and a workspace handle on it from each of two processes' storage."""
    async with empty_database("postgres", tmp_path) as database:
        engine = database.engine()
        await create_schema(engine)
        first = HeldSqlRelease(engine)
        second = SqlStorage(database.engine())
        yield (
            first,
            await Workspaces(first).open("t", "w", actor=ALICE),
            await Workspaces(second).open("t", "w", actor=ALICE),
        )


async def test_a_message_sent_from_another_process_as_a_run_ends_starts_the_next(
    processes: tuple[HeldSqlRelease, Workspace, Workspace], runners: MakeRunner
) -> None:
    storage, here, there = processes
    thread = await here.create_thread("Launch")
    releasing = storage.held = Gate()
    script = Script(say("Drafted."), say("Nothing else to do."))
    runner = runners(make_agent(script))
    other = runners(make_agent(Script()))
    first = started(await runner.send(here, thread.id, "Plan the launch"))
    await asyncio.wait_for(releasing.entered.wait(), timeout=5)
    assert (await other.send(there, thread.id, "Anything else?")).run is None
    releasing.release.set()
    await first.wait()
    await runner.drain()
    following = runner.running(thread.id)
    assert following is not None, "the run hands its thread over to the next turn"
    await following.wait()
    assert script.prompt_texts(1) == ["Plan the launch", "Anything else?"]


async def test_every_reply_sent_from_another_process_as_a_run_pauses_reaches_it(
    processes: tuple[HeldSqlRelease, Workspace, Workspace], runners: MakeRunner
) -> None:
    storage, here, there = processes
    thread = await here.create_thread("Launch")
    releasing = storage.held = Gate()
    script = Script(call("ask_user", call_id="q1", question="Which day?"), *[say("Monday.")] * 3)
    runner = runners(make_agent(script, ask=True, output_type=ASKING))
    other = runners(make_agent(Script(), ask=True, output_type=ASKING))
    first = started(await runner.send(here, thread.id, "Plan the launch"))
    await asyncio.wait_for(releasing.entered.wait(), timeout=5)
    assert (await other.send(there, thread.id, "Monday")).run is None
    assert (await other.send(there, thread.id, "And book the big room")).run is None
    releasing.release.set()
    await first.wait()
    await settled(runner, thread.id)
    assert script.prompt_texts(len(script.requests) - 1)[-1] == "And book the big room"
    assert (await here.run(first.run_id)).status == "completed"
