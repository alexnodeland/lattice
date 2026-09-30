"""The second review's PostgreSQL probes of PR #35: two processes, two engines.

Left out: S1, which held a save of the taken position that a turn's start no longer makes; and
S2, which asserted the spin it found (``tests/agent/test_run_ends_across_processes.py`` asserts
that resuming ends instead).
"""

import asyncio
import random
from collections import Counter
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import DeferredToolRequests, ModelMessage, ModelRequest, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo

from artifactr.agent import function_model
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
from tests.databases import empty_database

pytestmark = pytest.mark.postgres

ASKING = [str, DeferredToolRequests]


class Held(SqlStorage):
    held: Gate | None = None

    async def release_lease(self, scope: Scope, key: str, holder: str) -> None:
        if self.held is not None:
            await self.held.wait()
        await super().release_lease(scope, key, holder)


@pytest.fixture
async def two(tmp_path: Path) -> AsyncIterator[tuple[Held, Workspace, Workspace]]:
    async with empty_database("postgres", tmp_path) as database:
        engine = database.engine()
        await create_schema(engine)
        a = Held(engine)
        b = SqlStorage(database.engine())
        yield (
            a,
            await Workspaces(a).open("t", "w", actor=ALICE),
            await Workspaces(b).open("t", "w", actor=ALICE),
        )


def _seen(script: Script) -> list[str]:
    return [t for r in range(len(script.requests)) for t in script.prompt_texts(r)]


@pytest.mark.parametrize("round_", range(10))
async def test_s3_answer_then_message_from_another_process_in_the_pausing_window(
    two: tuple[Held, Workspace, Workspace], runners: MakeRunner, round_: int
) -> None:
    a, here, there = two
    thread = await here.create_thread("Launch")
    releasing = a.held = Gate()
    script = Script(call("ask_user", call_id="q1", question="Which day?"), *[say("ok")] * 4)
    runner = runners(make_agent(script, ask=True, output_type=ASKING))
    other = runners(make_agent(Script(), ask=True, output_type=ASKING))
    first = started(await runner.send(here, thread.id, "Plan the launch"))
    await asyncio.wait_for(releasing.entered.wait(), timeout=5)
    answer = AnswerDeferred(run_id=first.run_id, tool_call_id="q1", answer="Monday")
    assert (await other.answer(there, answer)).run is None
    assert (await other.send(there, thread.id, "And book the big room")).run is None
    a.held = None
    releasing.release.set()
    await first.wait()
    await settled(thread.id, runner)
    await settled(thread.id, other)
    assert "And book the big room" in _seen(script), f"lost: {_seen(script)}"


class Recorder:
    """A model shared by two processes' agents: replies at once, recording each new input."""

    def __init__(self) -> None:
        self.inputs: list[str] = []

    def respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        last_response = max(
            (i for i, m in enumerate(messages) if isinstance(m, ModelResponse)), default=-1
        )
        for message in messages[last_response + 1 :]:
            if isinstance(message, ModelRequest):
                for part in message.parts:
                    if part.part_kind == "user-prompt":
                        self.inputs.append(str(part.content))
        return ModelResponse(parts=[TextPart("ok")])


@pytest.mark.parametrize("seed", range(8))
async def test_s4_two_processes_sending_concurrently_carry_each_message_out_once(
    two: tuple[Held, Workspace, Workspace], runners: MakeRunner, seed: int
) -> None:
    from pydantic_ai import Agent

    from artifactr.agent import ArtifactWorkspace, Session
    from tests.artifact_types import Checklist, Note

    _, here, there = two
    thread = await here.create_thread("Launch")
    recorder = Recorder()

    def agent() -> Any:
        return Agent(
            function_model(recorder.respond),
            deps_type=Session[Gate],
            capabilities=[ArtifactWorkspace(types=[Note, Checklist])],
        )

    one, two_ = runners(agent()), runners(agent())
    rng = random.Random(seed)
    sent: list[str] = []

    async def send(index: int) -> None:
        for _ in range(rng.randrange(4)):
            await asyncio.sleep(0)
        text = f"m{index}"
        sent.append(text)
        if index % 2:
            await one.send(here, thread.id, text)
        else:
            await two_.send(there, thread.id, text)

    await asyncio.gather(*(send(i) for i in range(12)))
    await settled(thread.id, one, two_)
    counts = Counter(i for i in recorder.inputs if i.startswith("m"))
    missing = [m for m in sent if counts[m] == 0]
    twice = {m: c for m, c in counts.items() if c > 1}
    assert not missing, f"missing {missing}"
    assert not twice, f"more than once {twice}"
