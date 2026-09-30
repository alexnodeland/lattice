"""The final review's probes of PR #35, kept as regression tests of ADR-0055.

They try to make a hand-over spin, repeat a message, or start a run once the runner is closed.
The probe of a bystander that asked before its holder read, where the holder fails, is in
``tests/agent/test_invariants.py`` with the expectation ADR-0055's I4 states: a failure hands
over only what was asked after it read, so the bystander's message waits for the next command.
"""

import asyncio
import contextlib
from collections import Counter

import pytest

from artifactr.core import Run, RunStatus, Thread, ThreadId, UserActor
from artifactr.workspace import Scope, Workspace
from tests.agent.conftest import (
    Gate,
    HeldStorage,
    MakeRunner,
    Script,
    make_agent,
    say,
    settled,
    started,
)

BOB = UserActor(id="bob", name="Bob")


class Failing(HeldStorage):
    """Storage whose reads of paused runs, as a claimant plans, fail while ``failing``."""

    def __init__(self) -> None:
        super().__init__()
        self.failing = False
        self.plans = 0

    async def runs(
        self, scope: Scope, *, thread_id: ThreadId | None = None, status: RunStatus | None = None
    ) -> list[Run]:
        found = await super().runs(scope, thread_id=thread_id, status=status)
        if status == "paused":
            self.plans += 1
            if self.failing:
                raise ConnectionError("the database is down")
        return found


@pytest.fixture
def storage() -> Failing:
    return Failing()


async def _entered(gate: Gate) -> None:
    await asyncio.wait_for(gate.entered.wait(), timeout=2)


async def test_a_plan_that_keeps_failing_does_not_spin(
    storage: Failing, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(*[say("ok")] * 6)
    runner, other = runners(make_agent(script)), runners(make_agent(script))
    storage.failing = True
    for index in range(4):
        with contextlib.suppress(ConnectionError):
            await (runner if index % 2 else other).send(ws, thread.id, f"m{index}")
    await settled(thread.id, runner, other)
    assert storage.plans <= 8, f"{storage.plans} plans for 4 sends"
    storage.failing = False
    started(await runner.send(ws, thread.id, "back"))
    await settled(thread.id, runner, other)
    assert script.conversation() == ["m0", "m1", "m2", "m3", "back"]


async def test_repeated_cancels_with_bystanders_carry_each_message_out_once(
    storage: Failing, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(*[say("ok")] * 12)
    runner, other = runners(make_agent(script)), runners(make_agent(script))
    for index in range(5):
        planning = storage.held_runs = Gate()
        sending = asyncio.create_task(runner.send(ws, thread.id, f"a{index}"))
        await _entered(planning)
        assert (await other.send(ws.as_actor(BOB), thread.id, f"b{index}")).run is None
        sending.cancel()
        planning.release.set()
        with contextlib.suppress(asyncio.CancelledError):
            await sending
        await settled(thread.id, runner, other)
    conversation = Counter(script.conversation())
    assert {f"b{index}" for index in range(5)} <= set(conversation)
    assert all(count == 1 for count in conversation.values()), conversation


async def test_a_runner_closed_during_the_hand_over_it_spawned_starts_nothing(
    storage: Failing, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(*[say("ok")] * 4)
    runner, other = runners(make_agent(script)), runners(make_agent(script))
    planning = storage.held_runs = Gate()
    sending = asyncio.create_task(runner.send(ws, thread.id, "a"))
    await _entered(planning)
    assert (await other.send(ws.as_actor(BOB), thread.id, "b")).run is None
    handing = storage.held_log = Gate()  # the spawned hand-over, once it has read the log
    sending.cancel()
    planning.release.set()
    with contextlib.suppress(asyncio.CancelledError):
        await sending
    await _entered(handing)
    await runner.aclose()
    handing.release.set()
    await other.aclose()
    assert runner.running(thread.id) is None
    assert other.running(thread.id) is None
    assert script.requests == [], "no run starts once closed"
    restarted = runners(make_agent(script))
    started(await restarted.send(ws, thread.id, "c"))
    await settled(thread.id, restarted)
    assert script.conversation() == ["a", "b", "c"]


async def test_a_bystander_that_asked_before_a_cancelled_claimant_read_is_handed_over(
    storage: Failing, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(*[say("ok")] * 4)
    runner, other = runners(make_agent(script)), runners(make_agent(script))
    stalled = storage.held_claim = Gate()
    bystander = asyncio.create_task(other.send(ws.as_actor(BOB), thread.id, "Also book"))
    await _entered(stalled)  # Bob asked; his claim waits
    planning = storage.held_runs = Gate()
    sending = asyncio.create_task(runner.send(ws, thread.id, "Plan"))
    await _entered(planning)  # the claimant read Bob's ask, and holds the thread
    stalled.release.set()
    assert (await bystander).run is None, "refused: the claimant hands the thread over"
    sending.cancel()
    planning.release.set()
    with contextlib.suppress(asyncio.CancelledError):
        await sending
    await settled(thread.id, runner, other)
    assert script.conversation() == ["Also book", "Plan"]
