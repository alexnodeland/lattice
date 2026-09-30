"""A run's life in the workspace: what is recorded, what the agent is told, and history."""

import asyncio
import logging
from datetime import timedelta

import pytest
from pydantic import BaseModel
from pydantic_ai import FunctionToolset, ModelMessage, ModelRequest, ModelResponse

from artifactr.agent import Runner, Session, last_seen, load_history
from artifactr.core import (
    AgentActor,
    InvalidState,
    Run,
    RunEnded,
    RunStarted,
    RunStatus,
    SystemActor,
    Thread,
    ThreadId,
)
from artifactr.workspace import InMemoryStorage, Scope, Workspace, Workspaces
from tests.agent.conftest import (
    ALICE,
    Gate,
    Script,
    call,
    event_as,
    make_agent,
    make_runner,
    say,
    started,
    types,
)
from tests.artifact_types import Note
from tests.leases import Partitioned


async def test_a_message_starts_a_recorded_run(ws: Workspace, thread: Thread, gate: Gate) -> None:
    script = Script(
        call("create_artifact", kind="note", data={"title": "Plan", "text": "Ship Friday"}),
        say("I drafted the plan."),
    )
    runner = make_runner(make_agent(script), gate)
    handle = (await runner.send(ws, thread.id, "Draft a plan")).run
    assert handle is not None
    assert runner.running(thread.id) == handle
    result = await handle.wait()
    assert result.output == "I drafted the plan."
    assert runner.running(thread.id) is None
    log = await ws.read()
    assert types(log) == [
        "thread_created",
        "message_posted",
        "run_started",
        "tool_called",
        "artifact_created",
        "focus_changed",
        "tool_returned",
        "message_posted",
        "run_ended",
    ]
    agent = AgentActor(thread_id=thread.id, run_id=handle.run_id)
    assert [e.actor for e in log[2:]] == [agent] * 7
    [note] = await ws.artifacts(Note)
    assert note.updated_by == agent
    run = await ws.run(handle.run_id)
    assert run.status == "completed"
    ended = log[-1].event
    assert isinstance(ended, RunEnded)
    assert ended.usage is not None
    assert ended.usage.requests == 2
    assert "Ship Friday" in script.instructions(1), "followed artifacts are rendered"
    assert await last_seen(ws, thread.id) == log[-1].seq


async def test_the_next_run_continues_the_conversation(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(say("Hello!"), say("Still here."))
    runner = make_runner(make_agent(script), gate)
    await started(await runner.send(ws, thread.id, "Hi")).wait()
    await started(await runner.send(ws, thread.id, "Are you there?")).wait()
    assert script.prompt_texts(1) == ["Hi", "Are you there?"]
    history = await load_history(ws, thread.id)
    assert len(history) == 4


async def test_the_agent_is_told_what_changed_since_it_last_looked(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(
        call("create_artifact", kind="note", data={"text": "Ship Friday"}),
        say("Drafted."),
        say("Noted."),
    )
    runner = make_runner(make_agent(script), gate)
    await started(await runner.send(ws, thread.id, "Draft")).wait()
    [note] = await ws.artifacts(Note)
    await ws.commit(note.edit_text("Friday", "Monday"))
    await started(await runner.send(ws, thread.id, "I moved the date")).wait()
    notes = [text for text in script.prompt_texts(2) if "<workspace-changes>" in text]
    assert notes == [
        f"<workspace-changes>\n- Alice changed {note.id} (note, v1 → v2): "
        "edited text (1 replacement)\n</workspace-changes>"
    ]


async def test_instructions_describe_the_workspace(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    await ws.create(Note(text="x" * 5000), artifact_id="n1")
    from artifactr.core import SetFocus, SetThreadMode

    await ws.commit(SetFocus(thread_id=thread.id, artifact_ids=("n1",)))
    await ws.commit(SetThreadMode(thread_id=thread.id, mode="suggest"))
    await ws.commit((await ws.get(Note, "n1")).archive())
    script = Script(say("ok"))
    agent = make_agent(script)
    await agent.run("hi", deps=Session.start(ws, thread.id, app=gate))
    instructions = script.instructions(0)
    assert "suggest mode" in instructions
    assert "Kinds of artifact you can create: note, checklist." in instructions
    assert '<artifact id="n1" kind="note" version="2" archived>' in instructions
    assert "x" * 3999 + "…" in instructions


async def test_a_direct_run_watches_from_its_own_start(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(say("ok"))
    session = Session.start(ws, thread.id, app=gate, agent_name="Scribe")
    await make_agent(script).run("hi", deps=session)
    [posted] = [e for e in await ws.read() if e.event.type == "message_posted"]
    assert posted.actor == AgentActor(thread_id=thread.id, run_id=session.run_id, name="Scribe")
    assert session.trigger == "api"


async def test_structured_or_empty_outputs_post_no_message(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    class Summary(BaseModel):
        points: list[str]

    script = Script(call("final_result", points=["a"]))
    agent = make_agent(script, output_type=Summary)
    result = await agent.run("summarize", deps=Session.start(ws, thread.id, app=gate))
    assert result.output == Summary(points=["a"])
    empty = Script(say("  "))
    await make_agent(empty).run("hi", deps=Session.start(ws, thread.id, app=gate))
    assert "message_posted" not in types(await ws.read())


async def test_a_failed_run_is_recorded(ws: Workspace, thread: Thread, gate: Gate) -> None:
    def fail(messages: list[ModelMessage]) -> ModelResponse:
        raise RuntimeError("model unavailable")

    runner = make_runner(make_agent(Script(fail)), gate)
    handle = (await runner.send(ws, thread.id, "hi")).run
    assert handle is not None
    with pytest.raises(RuntimeError):
        await handle.wait()
    ended = event_as((await ws.read())[-1], RunEnded)
    assert (ended.status, ended.error) == ("failed", "model unavailable")


async def test_a_run_left_running_is_abandoned_when_its_thread_is_next_claimed(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    left = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_left"))
    await left.record(RunStarted(run_id="run_left", thread_id=thread.id))  # then its process died
    runner = make_runner(make_agent(Script(say("On it."))), gate)
    handle = started(await runner.send(ws, thread.id, "Are you there?"))
    await handle.wait()
    log = await ws.read()
    assert types(log[3:5]) == ["run_ended", "run_started"], "abandoned before the next run starts"
    assert event_as(log[3], RunEnded) == RunEnded(
        run_id="run_left",
        thread_id=thread.id,
        status="failed",
        error="the run was abandoned: its claim lapsed",
        reason="abandoned",
    )
    assert log[3].actor == SystemActor(name="runner")
    assert await ws.runs(status="running") == [], "so no client is told it is active"
    assert (await ws.run(handle.run_id)).status == "completed"


async def test_a_run_whose_claim_is_held_is_not_abandoned(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    running = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_live"))
    runner = make_runner(make_agent(Script()), gate)
    async with ws.claim_thread(thread.id, holder="run_live"):
        await running.record(RunStarted(run_id="run_live", thread_id=thread.id))
        assert (await runner.send(ws, thread.id, "Also this")).run is None, "it steers the run"
    assert (await ws.run("run_live")).status == "running"


class SlowRunningReads(InMemoryStorage):
    """Storage whose reads of running runs wait until the test lets them go."""

    def __init__(self) -> None:
        super().__init__()
        self.reading = asyncio.Event()
        self.go = asyncio.Event()

    async def runs(
        self, scope: Scope, *, thread_id: ThreadId | None = None, status: RunStatus | None = None
    ) -> list[Run]:
        if status == "running":
            self.reading.set()
            await self.go.wait()
        return await super().runs(scope, thread_id=thread_id, status=status)


async def test_a_start_cancelled_while_abandoning_releases_the_claim(gate: Gate) -> None:
    storage = SlowRunningReads()
    ws = await Workspaces(storage).open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread()
    runner = make_runner(make_agent(Script()), gate)
    sending = asyncio.create_task(runner.send(ws, thread.id, "hi"))
    await asyncio.wait_for(storage.reading.wait(), timeout=2)
    sending.cancel()
    await asyncio.gather(sending, return_exceptions=True)
    await runner.aclose()  # and with it the hand-over the cancelled start spawned
    async with ws.claim_thread(thread.id, holder="next"):
        pass


async def test_a_runner_closed_while_abandoning_starts_no_run(gate: Gate) -> None:
    storage = SlowRunningReads()
    ws = await Workspaces(storage).open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread()
    runner = make_runner(make_agent(Script()), gate)
    sending = asyncio.create_task(runner.send(ws, thread.id, "hi"))
    await asyncio.wait_for(storage.reading.wait(), timeout=2)
    await runner.aclose()
    storage.go.set()
    assert (await sending).run is None
    async with ws.claim_thread(thread.id, holder="next"):
        pass


class StaleRunningReads(InMemoryStorage):
    """Storage whose reads of running runs are stale: they list runs that have since ended."""

    async def runs(
        self, scope: Scope, *, thread_id: ThreadId | None = None, status: RunStatus | None = None
    ) -> list[Run]:
        stale = status == "running"
        return await super().runs(scope, thread_id=thread_id, status=None if stale else status)


async def test_a_run_that_ended_meanwhile_is_left_as_it_ended(gate: Gate) -> None:
    ws = await Workspaces(StaleRunningReads()).open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread()
    agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_done"))
    await agent.record(RunStarted(run_id="run_done", thread_id=thread.id))
    await agent.record(RunEnded(run_id="run_done", thread_id=thread.id, status="completed"))
    runner = make_runner(make_agent(Script(say("On it."))), gate)
    await started(await runner.send(ws, thread.id, "Are you there?")).wait()
    assert (await ws.run("run_done")).status == "completed"


TTL = timedelta(milliseconds=300)
"""A claim ttl short enough for a test to outlast, renewed every 100 ms."""


async def test_a_run_whose_claim_lapses_is_stopped_at_its_deadline(
    gate: Gate, app_tools: FunctionToolset[Session[Gate]], caplog: pytest.LogCaptureFixture
) -> None:
    storage = Partitioned(in_flight=True)
    ws = await Workspaces(storage).open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread()
    runner = Runner(make_agent(Script(call("hold")), tools=[app_tools]), app=gate, claim_ttl=TTL)
    handle = started(await runner.send(ws, thread.id, "Hold on"))
    storage.cut_off.add(storage.holders[f"thread:{thread.id}"])  # its next renewal hangs
    async with asyncio.timeout(5):
        await gate.entered.wait()
        await asyncio.gather(handle.task, return_exceptions=True)
    assert handle.task.cancelled()
    assert types(await ws.read()) == [
        "thread_created",
        "message_posted",
        "run_started",
        "tool_called",
        "run_ended",
    ]
    assert (await ws.run(handle.run_id)).status == "stopped", "nothing is left to abandon"
    async with ws.claim_thread(thread.id, holder="next"):
        pass
    assert f"the claim thread:{thread.id} lapsed, so it is lost" in caplog.text


async def test_an_abandoned_run_calls_no_more_tools(
    ws: Workspace,
    thread: Thread,
    gate: Gate,
    app_tools: FunctionToolset[Session[Gate]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="artifactr")
    script = Script(call("hold"), call("create_artifact", "call_2", kind="note", data={}))
    runner = make_runner(make_agent(script, tools=[app_tools]), gate)
    handle = started(await runner.send(ws, thread.id, "Hold on, then take a note"))
    async with asyncio.timeout(5):
        await gate.entered.wait()
    abandoned = RunEnded(run_id=handle.run_id, thread_id=thread.id, status="failed")
    await ws.as_actor(SystemActor(name="runner")).record(abandoned)
    gate.release.set()  # the tool already running finishes
    with pytest.raises(InvalidState, match="is failed"):
        await handle.wait()
    assert await ws.artifacts() == [], "the next tool call is refused"
    assert types(await ws.read())[-2:] == ["tool_called", "run_ended"], "and nothing is recorded"
    for dropped in ("tool_returned", "run_ended"):
        assert f"the {dropped} of a run that has failed is dropped" in caplog.text


async def test_a_run_ended_otherwise_meanwhile_fails(
    ws: Workspace, thread: Thread, gate: Gate, app_tools: FunctionToolset[Session[Gate]]
) -> None:
    runner = make_runner(make_agent(Script(call("hold")), tools=[app_tools]), gate)
    handle = started(await runner.send(ws, thread.id, "Hold on"))
    async with asyncio.timeout(5):
        await gate.entered.wait()
    stopped = RunEnded(run_id=handle.run_id, thread_id=thread.id, status="stopped")
    await ws.as_actor(SystemActor(name="ops")).record(stopped)
    gate.release.set()
    with pytest.raises(InvalidState, match="is stopped"):
        await handle.wait()


async def test_an_unwatched_failure_does_not_warn(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    def fail(messages: list[ModelMessage]) -> ModelResponse:
        raise RuntimeError("boom")

    runner = make_runner(make_agent(Script(fail)), gate)
    handle = (await runner.send(ws, thread.id, "hi")).run
    assert handle is not None
    while not handle.task.done():
        await gate_sleep()
    assert runner.running(thread.id) is None


async def gate_sleep() -> None:
    import asyncio

    await asyncio.sleep(0.01)


def test_history_messages_are_model_requests_first() -> None:
    assert ModelRequest.kind == "request"
