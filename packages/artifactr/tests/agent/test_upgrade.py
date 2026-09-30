"""A thread from before turns from the log starts where it stood at the upgrade (ADR-0055).

Each test builds a workspace at SQL migration 0004: a thread whose agent has run, then a
message lost to #29. It then migrates, as a deploy does, and touches the thread.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from pydantic_ai import DeferredToolRequests
from sqlalchemy.ext.asyncio import AsyncEngine

from artifactr.agent import Session
from artifactr.core import AnswerDeferred, RunId, Thread
from artifactr.sql import SqlStorage, migrate
from artifactr.sql.schema import _alembic_config
from artifactr.workspace import Workspace, Workspaces
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
from tests.databases import SQL_BACKENDS, Database, empty_database

ASKING = [str, DeferredToolRequests]

LOST = "Lost before the upgrade"


@pytest.fixture(params=SQL_BACKENDS)
async def database(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[Database]:
    async with empty_database(request.param, tmp_path) as database:
        yield database


@dataclass
class Before:
    """A workspace handle, its thread from before the upgrade, and the run that thread had."""

    ws: Workspace
    thread: Thread
    run_id: RunId


async def _before_the_upgrade(engine: AsyncEngine, gate: Gate, *, pauses: bool = False) -> Before:
    """Build a thread as artifactr left it before ADR-0055, then migrate, as a deploy does."""
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: command.upgrade(_alembic_config(c), "0004"))
    ws = await Workspaces(SqlStorage(engine)).open("t", "w", actor=ALICE)
    thread = await ws.create_thread("Launch")
    await ws.post_message(thread.id, "Plan the launch")
    session = Session.start(ws, thread.id, app=gate)
    if pauses:
        asking = Script(call("ask_user", call_id="q1", question="Which day?"))
        await make_agent(asking, ask=True, output_type=ASKING).run("Plan the launch", deps=session)
    else:
        await make_agent(Script(say("Drafted."))).run("Plan the launch", deps=session)
    await ws.post_message(thread.id, LOST)
    await migrate(engine)
    elsewhere = await ws.create_thread("Elsewhere")  # the workspace goes on in other threads
    await ws.post_message(elsewhere.id, "Over there")
    return Before(ws, thread, session.run_id)


async def test_a_thread_from_before_the_upgrade_takes_only_what_is_sent_after_it(
    database: Database, gate: Gate, runners: MakeRunner
) -> None:
    before = await _before_the_upgrade(database.engine(), gate)
    script = Script(say("Hello again."))
    runner = runners(make_agent(script))
    await started(await runner.send(before.ws, before.thread.id, "Anything new?")).wait()
    await settled(before.thread.id, runner)
    assert script.conversation() == ["Plan the launch", "Anything new?"], "not the lost one"


async def test_two_processes_that_touch_it_first_at_once_take_only_what_is_new(
    database: Database, gate: Gate, runners: MakeRunner
) -> None:
    before = await _before_the_upgrade(database.engine(), gate)
    there = await Workspaces(SqlStorage(database.engine())).open("t", "w", actor=ALICE)
    script = Script(*[say("ok")] * 4)
    here_runner, there_runner = runners(make_agent(script)), runners(make_agent(script))
    thread_id = before.thread.id
    sent = await asyncio.gather(
        here_runner.send(before.ws, thread_id, "From here"),
        there_runner.send(there, thread_id, "From there"),
    )
    await settled(thread_id, here_runner, there_runner)
    in_order = sorted(
        zip((s.outcome.seq or 0 for s in sent), ["From here", "From there"], strict=True)
    )
    assert script.conversation() == ["Plan the launch", *(content for _, content in in_order)]


async def test_a_paused_run_from_before_the_upgrade_resumes_on_its_answer(
    database: Database, gate: Gate, runners: MakeRunner
) -> None:
    before = await _before_the_upgrade(database.engine(), gate, pauses=True)
    script = Script(say("Monday it is."))
    runner = runners(make_agent(script, ask=True, output_type=ASKING))
    answer = AnswerDeferred(run_id=before.run_id, tool_call_id="q1", answer="Monday")
    resumed = started(await runner.answer(before.ws, answer))
    assert resumed.run_id == before.run_id
    assert (await resumed.wait()).output == "Monday it is."
    await settled(before.thread.id, runner)
    assert script.answers() == ["Monday"]
    assert LOST not in script.conversation()


async def test_a_message_posted_directly_after_the_upgrade_is_taken_by_the_next_turn(
    database: Database, gate: Gate, runners: MakeRunner
) -> None:
    before = await _before_the_upgrade(database.engine(), gate)
    await before.ws.post_message(before.thread.id, "Posted after the upgrade")
    script = Script(*[say("ok")] * 3)
    runner = runners(make_agent(script))
    started(await runner.send(before.ws, before.thread.id, "Anything new?"))
    await settled(before.thread.id, runner)
    assert script.conversation() == ["Plan the launch", "Posted after the upgrade", "Anything new?"]
