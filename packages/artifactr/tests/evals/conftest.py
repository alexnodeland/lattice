"""A traced workspace in which a person and a scripted agent have worked: no model, no network."""

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from artifactr.agent import Runner
from artifactr.core import Envelope, MessagePosted, Run, Thread
from artifactr.workspace import InMemoryStorage, Workspace, Workspaces
from tests.agent.conftest import ALICE, Gate, Script, call, make_agent, say, started
from tests.telemetry.conftest import Recorder, recording


@pytest.fixture
def recorder() -> Iterator[Recorder]:
    yield from recording()


@pytest.fixture
async def traced(recorder: Recorder) -> Workspace:
    """Alice's handle on a workspace whose commits and turns are traced."""
    return await Workspaces(InMemoryStorage(), **recorder.providers).open("t", "w", actor=ALICE)


@dataclass(frozen=True)
class Chat:
    """Two turns in one thread: the agent drafts a note, then answers a follow-up."""

    workspace: Workspace
    thread: Thread
    drafted: Run
    answered: Run


async def chat(workspace: Workspace, recorder: Recorder) -> Chat:
    thread = await workspace.create_thread("Launch")
    script = Script(
        call("create_artifact", kind="note", data={"text": "Ship Monday"}),
        say("Drafted."),
        say("No, that's all."),
    )
    runner = Runner(make_agent(script), app=Gate(), **recorder.providers)
    first = started(await runner.send(workspace, thread.id, "Draft a launch note"))
    await first.wait()
    second = started(await runner.send(workspace, thread.id, "Thanks, anything else?"))
    await second.wait()
    return Chat(
        workspace, thread, await workspace.run(first.run_id), await workspace.run(second.run_id)
    )


class Said(BaseModel):
    """An evaluator's input in the tests: who said what, and what the thread followed."""

    said: list[str]
    followed: list[str] = []


def said(transcript: tuple[Envelope, ...]) -> list[str]:
    return [
        f"{envelope.actor.kind}: {envelope.event.content}"
        for envelope in transcript
        if isinstance(envelope.event, MessagePosted)
    ]
