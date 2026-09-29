"""The Runner's evaluators port: each turn is handed over as it ends, and never failed by it."""

from collections.abc import Iterator

import pytest
from pydantic_ai import DeferredToolRequests, FunctionToolset, ModelMessage, ModelResponse

from artifactr.agent import EndedTurn, Runner, Session
from artifactr.core import Thread
from artifactr.workspace import InMemoryStorage, Workspace, Workspaces
from tests.agent.conftest import ALICE, Gate, Script, call, make_agent, say, started
from tests.telemetry.conftest import Recorder, recording, trace_id


class Collected:
    """A TurnEvaluator that keeps the turns it is given."""

    def __init__(self) -> None:
        self.turns: list[EndedTurn] = []

    def submit(self, turn: EndedTurn) -> None:
        self.turns.append(turn)


class Broken:
    """A TurnEvaluator that fails as it is given a turn."""

    def submit(self, turn: EndedTurn) -> None:
        raise RuntimeError("the judge is down")


@pytest.fixture
def recorder() -> Iterator[Recorder]:
    yield from recording()


@pytest.fixture
async def traced_ws(recorder: Recorder) -> Workspace:
    return await Workspaces(InMemoryStorage(), **recorder.providers).open("t", "w", actor=ALICE)


async def test_each_turn_is_handed_to_the_evaluators_as_it_ends(
    traced_ws: Workspace, recorder: Recorder, gate: Gate
) -> None:
    thread = await traced_ws.create_thread("Launch")
    collected = Collected()
    agent = make_agent(
        Script(call("ask_user", question="Which date?"), say("Monday it is.")),
        ask=True,
        output_type=[str, DeferredToolRequests],
    )
    runner = Runner(agent, app=gate, evaluators=[collected], **recorder.providers)
    first = started(await runner.send(traced_ws, thread.id, "Plan the launch"))
    await first.wait()
    await started(await runner.send(traced_ws, thread.id, "Monday")).wait()
    assert [turn.outcome for turn in collected.turns] == ["paused", "completed"]
    assert {turn.session.run_id for turn in collected.turns} == {first.run_id}
    turns = recorder.spans("invoke_workflow turn")
    assert [f"{t.span.trace_id:032x}" for t in collected.turns] == [trace_id(s) for s in turns]


async def test_a_failing_evaluator_is_recorded_on_the_turn_and_never_raised(
    traced_ws: Workspace, recorder: Recorder, gate: Gate
) -> None:
    thread = await traced_ws.create_thread("Launch")
    collected = Collected()
    runner = Runner(
        make_agent(Script(say("Done."))),
        app=gate,
        evaluators=[Broken(), collected],
        **recorder.providers,
    )
    await started(await runner.send(traced_ws, thread.id, "Draft")).wait()
    [turn] = collected.turns
    assert turn.outcome == "completed"
    span = recorder.span("invoke_workflow turn")
    [event] = span.events
    assert event.name == "exception"
    assert (event.attributes or {})["exception.message"] == "the judge is down"


async def test_failed_and_stopped_turns_are_handed_over_too(
    ws: Workspace, thread: Thread, gate: Gate, app_tools: FunctionToolset[Session[Gate]]
) -> None:
    def fail(messages: list[ModelMessage]) -> ModelResponse:
        raise RuntimeError("the model is down")

    collected = Collected()
    failing = Runner(make_agent(Script(fail)), app=gate, evaluators=[collected])
    with pytest.raises(RuntimeError, match="the model is down"):
        await started(await failing.send(ws, thread.id, "Draft")).wait()
    stopping = Runner(
        make_agent(Script(call("hold")), tools=[app_tools]), app=gate, evaluators=[collected]
    )
    handle = started(await stopping.send(ws, thread.id, "Hold on"))
    await gate.entered.wait()
    assert await stopping.stop(handle.run_id)
    assert [turn.outcome for turn in collected.turns] == ["failed", "stopped"]
