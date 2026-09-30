"""Turns from the log across processes: two runners, each with its own engine on PostgreSQL."""

import asyncio
import random
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic_ai import (
    Agent,
    DeferredToolRequests,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo

from artifactr.agent import ArtifactWorkspace, Session, function_model
from artifactr.core import AnswerDeferred
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
from tests.artifact_types import Checklist, Note
from tests.databases import empty_database

pytestmark = pytest.mark.postgres

ASKING = [str, DeferredToolRequests]


class HeldSqlRelease(SqlStorage):
    """SQL storage that holds the release of thread claims at ``held``, once a test sets it.

    It counts claims, and refuses one past 50, so a claimant that never stops fails its test.
    """

    held: Gate | None = None
    claims = 0

    async def release_lease(self, scope: Scope, key: str, holder: str) -> None:
        if self.held is not None:
            await self.held.wait()
        await super().release_lease(scope, key, holder)

    async def acquire_lease(self, scope: Scope, key: str, holder: str, ttl: timedelta) -> bool:
        self.claims += 1
        if self.claims > 50:
            raise RuntimeError(f"claimed {self.claims} times")
        return await super().acquire_lease(scope, key, holder, ttl)


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
    await settled(thread.id, runner)
    assert script.prompt_texts(len(script.requests) - 1)[-1] == "And book the big room"
    assert (await here.run(first.run_id)).status == "completed"


async def test_resuming_while_another_process_commits_in_another_thread_ends(
    processes: tuple[HeldSqlRelease, Workspace, Workspace], runners: MakeRunner
) -> None:
    storage, here, there = processes
    thread = await here.create_thread("Launch")
    runner = runners(make_agent(Script(say("Done."))))
    first = started(await runner.send(here, thread.id, "Go"))
    await first.wait()
    await runner.drain()
    elsewhere = await there.create_thread("Elsewhere")
    await there.post_message(elsewhere.id, "Hello from another process and thread")
    claims = storage.claims
    assert await runner.resume(here, first.run_id) is None
    assert storage.claims - claims <= 2


async def test_an_answer_and_a_message_from_another_process_as_a_run_pauses_reach_it(
    processes: tuple[HeldSqlRelease, Workspace, Workspace], runners: MakeRunner
) -> None:
    storage, here, there = processes
    thread = await here.create_thread("Launch")
    releasing = storage.held = Gate()
    script = Script(call("ask_user", call_id="q1", question="Which day?"), *[say("ok")] * 3)
    runner = runners(make_agent(script, ask=True, output_type=ASKING))
    other = runners(make_agent(Script(), ask=True, output_type=ASKING))
    first = started(await runner.send(here, thread.id, "Plan the launch"))
    await asyncio.wait_for(releasing.entered.wait(), timeout=5)
    answer = AnswerDeferred(run_id=first.run_id, tool_call_id="q1", answer="Monday")
    assert (await other.answer(there, answer)).run is None
    assert (await other.send(there, thread.id, "And book the big room")).run is None
    releasing.release.set()
    await first.wait()
    await settled(thread.id, runner, other)
    assert script.answers() == ["Monday"]
    assert script.conversation() == ["Plan the launch", "And book the big room"]


class Recorder:
    """One model for two processes' agents: it replies at once, and records each new prompt."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        answered = max(
            (i for i, message in enumerate(messages) if isinstance(message, ModelResponse)),
            default=-1,
        )
        self.prompts += [
            str(part.content)
            for message in messages[answered + 1 :]
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, UserPromptPart)
        ]
        return ModelResponse(parts=[TextPart("ok")])


@pytest.mark.parametrize("seed", range(3))
async def test_two_processes_sending_at_once_carry_each_message_out_once(
    processes: tuple[HeldSqlRelease, Workspace, Workspace], runners: MakeRunner, seed: int
) -> None:
    _, here, there = processes
    thread = await here.create_thread("Launch")
    recorder = Recorder()

    def agent() -> Agent[Session[Gate], str]:
        return Agent(
            function_model(recorder.respond),
            deps_type=Session[Gate],
            capabilities=[ArtifactWorkspace(types=[Note, Checklist])],
        )

    this, that = runners(agent()), runners(agent())
    shuffle = random.Random(seed)

    async def send(index: int) -> None:
        for _ in range(shuffle.randrange(4)):
            await asyncio.sleep(0)
        runner, ws = (this, here) if index % 2 else (that, there)
        await runner.send(ws, thread.id, f"m{index}")

    await asyncio.gather(*(send(index) for index in range(12)))
    await settled(thread.id, this, that)
    await settled(thread.id, that, this)
    assert sorted(recorder.prompts) == sorted(f"m{index}" for index in range(12))
