"""The first review's probes of PR #35, kept as regression tests of ADR-0055.

Left out: the probe of a message carried out twice, which held a read the send no longer makes
(``tests/agent/test_run_ends.py`` stalls the send's claim instead); the probe of stopping an
ended run, which asserted the behaviour ADR-0055 removed; and a probe that only printed.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic_ai import DeferredToolRequests, ModelResponse, TextPart

from artifactr.agent import Runner, Session
from artifactr.core import AnswerDeferred, RunStatus, Thread
from artifactr.workspace import Scope, Workspace
from tests.agent.conftest import (
    Gate,
    HeldStorage,
    Script,
    call,
    make_agent,
    make_runner,
    say,
    started,
)

ASKING = [str, DeferredToolRequests]


@pytest.fixture
def storage() -> HeldStorage:
    return HeldStorage()


# ─── 1. a run that fails before wrap_run reads the thread from seq 0 ─────────────


async def test_probe_a_failure_before_wrap_run_replays_the_threads_first_message(
    storage: HeldStorage, ws: Workspace, thread: Thread, gate: Gate
) -> None:
    entered = 0

    @contextlib.asynccontextmanager
    async def flaky(session: Session[Any]) -> AsyncIterator[None]:
        nonlocal entered
        entered += 1
        if entered == 2:
            raise RuntimeError("the tracing backend blinked")
        yield

    script = Script(say("Drafted."), say("Drafted again."))
    runner = Runner(make_agent(script), app=gate, turn_context=flaky)
    await started(await runner.send(ws, thread.id, "Plan the launch")).wait()
    # A second message; its turn fails before wrap_run sets Session.delivered.
    second = started(await runner.send(ws, thread.id, "Anything else?"))
    await asyncio.gather(second.task, return_exceptions=True)
    following = runner.running(thread.id)
    assert following is None, (
        "a failed turn started a run for an old message: "
        f"{[m for r in range(len(script.requests)) for m in script.prompt_texts(r)]}"
    )


async def test_probe_a_persistent_failure_before_wrap_run_spawns_runs_forever(
    storage: HeldStorage, ws: Workspace, thread: Thread, gate: Gate
) -> None:
    entered = asyncio.Event()
    count = 0

    @contextlib.asynccontextmanager
    async def broken(session: Session[Any]) -> AsyncIterator[None]:
        nonlocal count
        count += 1
        if count >= 25:
            entered.set()
        raise RuntimeError("the tracing backend is down")
        yield

    runner = Runner(make_agent(Script()), app=gate, turn_context=broken)
    await runner.send(ws, thread.id, "Plan the launch")
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(entered.wait(), timeout=2)
    await runner.aclose()
    assert count == 1, f"one message, {count} turns"


# ─── 2. two replies in the pausing window: the second is never delivered ─────────


@pytest.mark.parametrize("first_reply", ["answer", "message"])
async def test_probe_a_second_message_in_the_pausing_window_is_lost(
    storage: HeldStorage, ws: Workspace, thread: Thread, gate: Gate, first_reply: str
) -> None:
    releasing = storage.held = Gate()
    holding = Gate()

    def slow_second(messages: Any) -> ModelResponse:
        return ModelResponse(parts=[TextPart("Monday it is.")])

    script = Script(call("ask_user", call_id="q1", question="Which day?"), slow_second)
    runner = make_runner(make_agent(script, ask=True, output_type=ASKING), gate)
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await asyncio.wait_for(releasing.entered.wait(), timeout=2)
    if first_reply == "answer":
        answer = AnswerDeferred(run_id=first.run_id, tool_call_id="q1", answer="Monday")
        assert (await runner.answer(ws, answer)).run is None
    else:
        assert (await runner.send(ws, thread.id, "Monday")).run is None
    assert (await runner.send(ws, thread.id, "And book the big room")).run is None
    del holding
    storage.held = None
    releasing.release.set()
    await first.wait()
    resumed = runner.running(thread.id)
    assert resumed is not None
    await resumed.wait()
    seen = [t for r in range(len(script.requests)) for t in script.prompt_texts(r)]
    assert "And book the big room" in seen, f"the second message never reached a run: {seen}"


# ─── 3. one message carried out twice: by the follow-up and by its own send ───────


class SlowPausedCheck(HeldStorage):
    """Holds the next ``runs(status='paused')`` read at ``held_runs``, once a test sets it."""

    def __init__(self) -> None:
        super().__init__()
        self.held_runs: Gate | None = None

    async def runs(
        self, scope: Scope, *, thread_id: Any = None, status: RunStatus | None = None
    ) -> Any:
        if status == "paused" and self.held_runs is not None:
            gate, self.held_runs = self.held_runs, None
            await gate.wait()
        return await super().runs(scope, thread_id=thread_id, status=status)


# ─── 5. a message committed directly, without Runner.send, now starts a turn ─────


async def test_probe_a_direct_message_in_the_window_starts_a_turn(
    storage: HeldStorage, ws: Workspace, thread: Thread, gate: Gate
) -> None:
    releasing = storage.held = Gate()
    script = Script(say("Drafted."), say("Replying to a direct post."))
    runner = make_runner(make_agent(script), gate)
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await asyncio.wait_for(releasing.entered.wait(), timeout=2)
    await ws.post_message(thread.id, "FYI, posted directly")  # no Runner.send
    storage.held = None
    releasing.release.set()
    await first.wait()
    assert runner.running(thread.id) is None, "a direct message started a turn"
