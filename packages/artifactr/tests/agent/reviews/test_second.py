"""The second review's probes of PR #35, kept as regression tests of ADR-0055.

Left out: B1 and B2, which held a save of the taken position that a turn's start no longer
makes (``tests/agent/test_claimants.py`` and ``test_invariants.py`` cancel and close at each
step instead); and D1 and D2, which asserted what the maintainer decided against: a message is a
message, so a direct post in a paused thread is its reply.
"""

import asyncio
import contextlib
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import pytest
from pydantic_ai import (
    DeferredToolRequests,
    FunctionToolset,
    ModelResponse,
    RunContext,
    ToolCallPart,
)

from artifactr.agent import Runner, Session
from artifactr.core import AnswerDeferred, Envelope, RunStatus, Thread, UserActor
from artifactr.workspace import Scope, Workspace
from tests.agent.conftest import (
    Gate,
    HeldStorage,
    MakeRunner,
    Script,
    call,
    make_agent,
    say,
    settled,
    started,
)

ASKING = [str, DeferredToolRequests]
BOB = UserActor(id="bob", name="Bob")


class Probe(HeldStorage):
    """Adds gates: after a ``taken`` save, on a paused-runs read, on head_seq, on subscribe."""

    def __init__(self) -> None:
        super().__init__()
        self.held_taken: Gate | None = None
        self.held_runs: Gate | None = None
        self.held_head: Gate | None = None
        self.held_subscribe: Gate | None = None

    async def save_cursor(self, scope: Scope, name: str, seq: int) -> None:
        await super().save_cursor(scope, name, seq)
        # SqlStorage's save is awaited to its end, and a cancellation that came meanwhile is
        # raised after it: this gate models that, the save done and then a cancellation point.
        if name.endswith("/taken") and (gate := self.held_taken) is not None:
            self.held_taken = None
            await gate.wait()

    async def runs(
        self, scope: Scope, *, thread_id: Any = None, status: RunStatus | None = None
    ) -> Any:
        if status == "paused" and (gate := self.held_runs) is not None:
            self.held_runs = None
            await gate.wait()
        return await super().runs(scope, thread_id=thread_id, status=status)

    async def head_seq(self, scope: Scope) -> int:
        if (gate := self.held_head) is not None:
            self.held_head = None
            await gate.wait()
        return await super().head_seq(scope)

    async def subscribe(self, scope: Scope, *, after_seq: int = 0) -> AsyncGenerator[Envelope]:
        gate, self.held_subscribe = self.held_subscribe, None
        if gate is not None:
            await gate.wait()  # a watcher whose first read is slow, as SQL's can be
        async for envelope in super().subscribe(scope, after_seq=after_seq):
            yield envelope


@pytest.fixture
def storage() -> Probe:
    return Probe()


async def _entered(gate: Gate) -> None:
    await asyncio.wait_for(gate.entered.wait(), timeout=2)


def _seen(script: Script) -> list[str]:
    return [t for r in range(len(script.requests)) for t in script.prompt_texts(r)]


def _spin_guard(monkeypatch: pytest.MonkeyPatch, limit: int = 50) -> list[int]:
    plans = [0]
    original = Runner._plan

    async def counting(self: Runner[Any], workspace: Workspace, thread_id: str) -> Any:
        plans[0] += 1
        if plans[0] > limit:
            raise RuntimeError(f"planned {plans[0]} times without end")
        return await original(self, workspace, thread_id)

    monkeypatch.setattr(Runner, "_plan", counting)
    return plans


# ─── A. asked = the workspace's head, taken = the thread's last seq ───────────


async def test_a1_resume_when_the_head_is_in_another_thread(
    ws: Workspace, thread: Thread, runners: MakeRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = runners(make_agent(Script(say("Done."))))
    first = started(await runner.send(ws, thread.id, "Go"))
    await first.wait()
    await runner.drain()
    other = await ws.create_thread("Elsewhere")
    await ws.post_message(other.id, "hello over there")
    plans = _spin_guard(monkeypatch)
    try:
        result = await runner.resume(ws, first.run_id)
    except RuntimeError as error:
        pytest.fail(f"resume of a finished run: {error}")
    assert result is None
    assert plans[0] < 5


async def test_a2_a_partial_answer_while_another_thread_commits(
    storage: Probe,
    ws: Workspace,
    thread: Thread,
    runners: MakeRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    both = ModelResponse(
        parts=[
            ToolCallPart(tool_name="ask_user", args={"question": "Day?"}, tool_call_id="q1"),
            ToolCallPart(tool_name="ask_user", args={"question": "Time?"}, tool_call_id="q2"),
        ]
    )
    runner = runners(make_agent(Script(both, say("ok")), ask=True, output_type=ASKING))
    paused = started(await runner.send(ws, thread.id, "Plan it"))
    await paused.wait()
    await runner.drain()
    other = await ws.create_thread("Elsewhere")
    head = storage.held_head = Gate()
    answering = asyncio.create_task(
        runner.answer(ws, AnswerDeferred(run_id=paused.run_id, tool_call_id="q1", answer="Monday"))
    )
    await _entered(head)
    await ws.post_message(other.id, "meanwhile, in another thread")
    plans = _spin_guard(monkeypatch)
    head.release.set()
    try:
        sent = await asyncio.wait_for(answering, timeout=5)
    except RuntimeError as error:
        pytest.fail(f"a partial answer: {error}")
    assert sent.run is None
    assert plans[0] < 5


# ─── B. taken saved before the run exists ─────────────────────────────────────


async def test_b3_aclose_while_a_send_plans(
    storage: Probe, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    runner = runners(make_agent(Script(say("ok"))))
    planning = storage.held_runs = Gate()
    sending = asyncio.create_task(runner.send(ws, thread.id, "Go"))
    await _entered(planning)
    await runner.aclose()
    planning.release.set()
    sent = await sending
    assert sent.run is None, "a run started after aclose() returned"


# ─── C. a resume by answers counts as taken what it has not delivered ─────────


async def test_c1_a_resume_that_fails_early_loses_a_message_sent_in_the_pausing_window(
    storage: Probe, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    failed: list[str] = []

    @contextlib.asynccontextmanager
    async def resume_fails_once(session: Session[Any]) -> AsyncIterator[None]:
        if session.trigger == "resume" and not failed:
            failed.append(session.run_id)
            raise RuntimeError("the tracing backend blinked")
        yield

    releasing = storage.held = Gate()
    script = Script(call("ask_user", call_id="q1", question="Which day?"), *[say("ok")] * 4)
    runner = runners(
        make_agent(script, ask=True, output_type=ASKING), turn_context=resume_fails_once
    )
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    answer = AnswerDeferred(run_id=first.run_id, tool_call_id="q1", answer="Monday")
    assert (await runner.answer(ws, answer)).run is None
    assert (await runner.send(ws, thread.id, "And book the big room")).run is None
    releasing.release.set()
    await first.wait()
    await settled(thread.id, runner)
    assert failed, "the resume failed before it started"
    started(await runner.send(ws, thread.id, "Hello?"))
    await settled(thread.id, runner)
    assert "And book the big room" in _seen(script), f"lost: the model saw only {_seen(script)}"


async def test_c2_a_resume_whose_watcher_is_slow_loses_a_message_sent_in_the_pausing_window(
    storage: Probe, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    releasing = storage.held = Gate()
    script = Script(call("ask_user", call_id="q1", question="Which day?"), *[say("ok")] * 4)
    runner = runners(make_agent(script, ask=True, output_type=ASKING))
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    answer = AnswerDeferred(run_id=first.run_id, tool_call_id="q1", answer="Monday")
    assert (await runner.answer(ws, answer)).run is None
    assert (await runner.send(ws, thread.id, "And book the big room")).run is None
    slow = storage.held_subscribe = Gate()  # the resumed run's watcher reads late
    releasing.release.set()
    await first.wait()
    await runner.drain()
    resumed = runner.running(thread.id)
    assert resumed is not None
    await resumed.wait()  # the model answered at once
    slow.release.set()
    await settled(thread.id, runner)
    assert "And book the big room" in _seen(script), f"lost: the model saw only {_seen(script)}"


async def test_c2_control_a_new_runs_slow_watcher_leaves_the_message_for_the_next_turn(
    storage: Probe, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    releasing = storage.held = Gate()
    script = Script(say("Drafted."), *[say("ok")] * 4)
    runner = runners(make_agent(script))
    held_first = storage.held_subscribe = Gate()
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    assert (await runner.send(ws, thread.id, "And book the big room")).run is None
    releasing.release.set()
    await first.wait()
    held_first.release.set()
    await settled(thread.id, runner)
    assert "And book the big room" in _seen(script)


# ─── D. direct posts become replies ───────────────────────────────────────────


def _approval_tools() -> FunctionToolset[Session[Gate]]:
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool(requires_approval=True)
    async def publish(ctx: RunContext[Session[Gate]], channel: str) -> str:
        """Publish the plan."""
        return f"published to {channel}"

    return tools


# ─── E. a process that dies after its run ends, before taken is saved ─────────


async def test_e1_a_run_whose_taken_is_not_saved_gives_its_steering_again(
    ws: Workspace,
    thread: Thread,
    gate: Gate,
    runners: MakeRunner,
    app_tools: FunctionToolset[Session[Gate]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = Script(call("hold"), say("Done, and noted the venue."), say("ok"), say("ok"))
    runner = runners(make_agent(script, tools=[app_tools]))
    handle = started(await runner.send(ws, thread.id, "Hold on"))
    await _entered(gate)
    assert (await runner.send(ws, thread.id, "The venue changed")).run is None  # it steers
    for _ in range(5):
        await asyncio.sleep(0)
    original = Workspace.save_cursor

    async def dies(self: Workspace, name: str, seq: int) -> None:
        if name.endswith("/taken"):
            raise ConnectionError("the process died")
        await original(self, name, seq)

    with monkeypatch.context() as patched:
        patched.setattr(Workspace, "save_cursor", dies)
        gate.release.set()
        await handle.wait()
        await runner.drain()
    assert script.prompt_texts(1).count("The venue changed") == 1
    started(await runner.send(ws, thread.id, "Hello?"))
    await settled(thread.id, runner)
    last = script.prompt_texts(len(script.requests) - 1)
    assert last.count("The venue changed") == 1, f"given again: {last}"
