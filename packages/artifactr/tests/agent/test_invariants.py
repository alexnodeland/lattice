"""ADR-0055's invariants, each tested in memory and on PostgreSQL, in busy workspaces.

- I1: every message in a thread's log, notices aside, is consumed exactly once.
- I2: its consumption is recorded in the transaction of the write that consumes it.
- I3: a claim is never held without a task, nor released, while more was asked than taken,
  without a hand-over that reads the asks after the release.
- I4: a turn that fails or is stopped before it starts consumes nothing, and hands over if
  more was asked meanwhile.
- I5: a message committed directly starts no turn, and the next turn consumes it. A notice is
  never a prompt or a reply.
- I6: a message is a message: in a paused thread, the oldest message not consumed is the reply,
  however it was committed.
- I7, the upgrade point, is in ``test_upgrade.py``.

Each test holds one storage call at a :class:`Gate`, patched onto the storage it runs on.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic_ai import Agent, DeferredToolRequests, FunctionToolset, ModelResponse, RunContext

from artifactr.agent import ArtifactWorkspace, Session, function_model
from artifactr.core import (
    AnswerDeferred,
    DeferredAnswered,
    PostMessage,
    Thread,
    UserActor,
)
from artifactr.sql import SqlStorage, create_schema
from artifactr.workspace import InMemoryStorage, Scope, Storage, Workspace, Workspaces
from tests.agent.conftest import (
    ALICE,
    Gate,
    MakeRunner,
    Recorder,
    Script,
    call,
    make_agent,
    say,
    settled,
    started,
)
from tests.artifact_types import Checklist, Note
from tests.databases import empty_database

ASKING = [str, DeferredToolRequests]
BOB = UserActor(id="bob", name="Bob")
SCOPE = Scope("t", "w")


def hold(
    storage: Storage,
    method: str,
    *,
    every: bool = False,
    after: bool = False,
    status: str | None = None,
    raises: Exception | None = None,
) -> Gate:
    """Hold the storage's next call of ``method`` at a gate, or ``every`` call until released.

    With ``after``, the call is made first, and the caller held once it returns. With
    ``status``, only a read of runs with that status is held. With ``raises``, the held call
    raises it once released.
    """
    gate, original = Gate(), getattr(storage, method)
    armed = [True]

    async def held(*args: Any, **kwargs: Any) -> Any:
        if not armed[0] or (status is not None and kwargs.get("status") != status):
            return await original(*args, **kwargs)
        armed[0] = every
        if after:
            result = await original(*args, **kwargs)
            await gate.wait()
            return result
        await gate.wait()
        if raises is not None:
            raise raises
        return await original(*args, **kwargs)

    setattr(storage, method, held)
    return gate


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.postgres)])
async def storages(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[tuple[Storage, Storage]]:
    """Storage as two processes see it: the same one in memory, two engines on PostgreSQL."""
    if request.param == "memory":
        memory = InMemoryStorage()
        yield memory, memory
        return
    async with empty_database("postgres", tmp_path) as database:
        engine = database.engine()
        await create_schema(engine)
        poll = timedelta(milliseconds=50)
        yield (
            SqlStorage(engine, poll_interval=poll),
            SqlStorage(database.engine(), poll_interval=poll),
        )


@pytest.fixture
def storage(storages: tuple[Storage, Storage]) -> Storage:
    return storages[0]


@pytest.fixture
async def ws(storage: Storage) -> Workspace:
    return await Workspaces(storage).open(SCOPE.tenant_id, SCOPE.workspace_id, actor=ALICE)


@pytest.fixture
async def there(storages: tuple[Storage, Storage]) -> Workspace:
    """The workspace as another process opens it."""
    return await Workspaces(storages[1]).open(SCOPE.tenant_id, SCOPE.workspace_id, actor=ALICE)


@pytest.fixture
async def thread(ws: Workspace) -> Thread:
    """The test's thread, in a workspace whose other thread is busy."""
    elsewhere = await ws.create_thread("Elsewhere")
    await ws.post_message(elsewhere.id, "Over here")
    return await ws.create_thread("Launch")


async def _entered(gate: Gate) -> None:
    await asyncio.wait_for(gate.entered.wait(), timeout=5)


async def _taken(storage: Storage, thread: Thread) -> int:
    """How far the thread's messages are consumed: ADR-0055's cursor."""
    return await storage.cursor(SCOPE, f"artifactr.runner/{thread.id}/taken")


def _paused_agent(script: Script, **options: Any) -> Any:
    return make_agent(script, ask=True, output_type=ASKING, **options)


def _asking() -> ModelResponse:
    return call("ask_user", call_id="q1", question="Which day?")


# ─── I1: exactly once ─────────────────────────────────────────────────────────


async def test_i1_messages_sent_at_once_from_two_processes_are_each_consumed_once(
    ws: Workspace, there: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    recorder = Recorder()

    def agent() -> Agent[Session[Any], str]:
        return Agent(
            function_model(recorder.respond),
            deps_type=Session[Any],
            capabilities=[ArtifactWorkspace(types=[Note, Checklist])],
        )

    here_runner, there_runner = runners(agent()), runners(agent())

    async def send(index: int) -> None:
        runner, handle = (here_runner, ws) if index % 2 else (there_runner, there)
        await runner.send(handle, thread.id, f"m{index}")

    await asyncio.gather(*(send(index) for index in range(12)))
    await settled(thread.id, here_runner, there_runner)
    assert sorted(recorder.prompts) == sorted(f"m{index}" for index in range(12))


async def test_i1_a_message_sent_as_a_run_releases_its_thread_is_consumed_once(
    storage: Storage, ws: Workspace, there: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(say("Drafted."), *[say("ok")] * 3)
    runner, other = runners(make_agent(script)), runners(make_agent(script))
    releasing = hold(storage, "release_lease", every=True)
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    assert (await other.send(there, thread.id, "Anything else?")).run is None
    releasing.release.set()
    await first.wait()
    await settled(thread.id, runner, other)
    assert script.conversation() == ["Plan the launch", "Anything else?"]


# ─── I2: recorded with the write that consumes ───────────────────────────────


async def test_i2_a_prompt_is_consumed_with_its_runs_start(
    storage: Storage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    runner = runners(make_agent(Script(say("Done."))))
    begun = hold(storage, "thread")  # the run reads its thread once it has recorded its start
    sent = await runner.send(ws, thread.id, "Plan the launch")
    await _entered(begun)
    assert [e.event.type for e in await ws.read(after_seq=sent.outcome.seq or 0)] == ["run_started"]
    assert await _taken(storage, thread) == sent.outcome.seq, "taken with the run's start"
    begun.release.set()
    await started(sent).wait()


async def test_i2_a_reply_is_consumed_with_its_answer_so_it_is_never_a_prompt(
    storage: Storage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(_asking(), *[say("ok")] * 3)
    runner = runners(_paused_agent(script))
    paused = started(await runner.send(ws, thread.id, "Plan the launch"))
    await paused.wait()
    await runner.drain()
    resuming = hold(storage, "history")  # the resumed turn loads its history before it starts
    replied = await runner.send(ws, thread.id, "Monday")
    await _entered(resuming)
    answered = [
        e.event.answer
        for e in await ws.read(threads={thread.id})
        if isinstance(e.event, DeferredAnswered)
    ]
    assert await _taken(storage, thread) == replied.outcome.seq, "taken with the answer"
    assert answered == ["Monday"]
    await runner.aclose()  # the resumed run never starts
    resuming.release.set()
    restarted = runners(_paused_agent(script))
    started(await restarted.send(ws, thread.id, "Hello?"))
    await settled(thread.id, restarted)
    assert script.answers() == ["Monday"]
    assert script.conversation() == ["Plan the launch", "Hello?"], "the reply is not a prompt"


@pytest.mark.parametrize("ends", ["completes", "is stopped"])
async def test_i2_steering_is_consumed_with_the_runs_end(
    storage: Storage,
    ws: Workspace,
    thread: Thread,
    gate: Gate,
    runners: MakeRunner,
    app_tools: FunctionToolset[Session[Gate]],
    monkeypatch: pytest.MonkeyPatch,
    ends: str,
) -> None:
    script = Script(call("hold"), say("Noted."), *[say("ok")] * 2)
    runner = runners(make_agent(script, tools=[app_tools]))
    enqueue, offered = RunContext.enqueue, asyncio.Event()

    def offer(ctx: RunContext[Any], *content: Any, **options: Any) -> str | None:
        queued = enqueue(ctx, *content, **options)
        offered.set()
        return queued

    monkeypatch.setattr(RunContext, "enqueue", offer)
    handle = started(await runner.send(ws, thread.id, "Hold on"))
    await _entered(gate)
    steering = await runner.send(ws, thread.id, "The venue changed")
    assert steering.run is None
    await asyncio.wait_for(offered.wait(), timeout=5)  # the watcher delivered it
    if ends == "is stopped":
        assert await runner.stop(handle.run_id)
    gate.release.set()
    await asyncio.gather(handle.task, return_exceptions=True)
    await settled(thread.id, runner)
    assert await _taken(storage, thread) >= (steering.outcome.seq or 0), "with its end record"
    started(await runner.send(ws, thread.id, "Hello?"))
    await settled(thread.id, runner)
    conversation = script.conversation()
    assert conversation[-1] == "Hello?"
    assert conversation.count("The venue changed") == (1 if ends == "completes" else 0)


# ─── I3: a claim, a task, and a hand-over ────────────────────────────────────


async def test_i3_a_claim_is_released_when_its_run_cannot_be_set_up(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    runner = runners(make_agent(Script()), agent_name=cast(str, 42))
    with pytest.raises(ValueError, match="string"):
        await runner.send(ws, thread.id, "Plan the launch")
    async with ws.claim_thread(thread.id, holder="next"):
        pass


@pytest.mark.parametrize("ends", ["is cancelled", "fails"])
async def test_i3_a_claimant_that_never_starts_a_run_hands_over_what_it_refused(
    storage: Storage,
    ws: Workspace,
    there: Workspace,
    thread: Thread,
    runners: MakeRunner,
    ends: str,
) -> None:
    script = Script(*[say("ok")] * 4)
    runner, other = runners(make_agent(script)), runners(make_agent(script))
    blinks = ConnectionError("the database blinked") if ends == "fails" else None
    planning = hold(storage, "runs", status="paused", raises=blinks)
    sending = asyncio.create_task(runner.send(ws, thread.id, "Plan the launch"))
    await _entered(planning)
    bystander = await other.send(there.as_actor(BOB), thread.id, "Also book the big room")
    assert bystander.run is None, "its holder hands the thread over"
    if ends == "is cancelled":
        sending.cancel()
    planning.release.set()
    with contextlib.suppress(asyncio.CancelledError, ConnectionError):
        await sending
    await settled(thread.id, runner, other)
    assert script.conversation() == ["Plan the launch", "Also book the big room"]


@pytest.mark.parametrize("ends", ["fails", "is stopped"])
async def test_i3_a_message_left_to_a_holder_that_never_starts_is_handed_over(
    ws: Workspace, there: Workspace, thread: Thread, runners: MakeRunner, ends: str
) -> None:
    held = Gate()

    @contextlib.asynccontextmanager
    async def begins(session: Session[Any]) -> AsyncIterator[None]:
        if not held.release.is_set():
            await held.wait()
            if ends == "fails":
                raise RuntimeError("the tracing backend blinked")
        yield

    script = Script(*[say("ok")] * 3)
    runner = runners(make_agent(script), turn_context=begins)
    other = runners(make_agent(script))
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(held)
    bystander = await other.send(there.as_actor(BOB), thread.id, "Also book the big room")
    assert bystander.run is None, "its holder hands the thread over"
    if ends == "is stopped":
        assert await runner.stop(first.run_id)
    held.release.set()
    await asyncio.gather(first.task, return_exceptions=True)
    await settled(thread.id, runner, other)
    assert script.conversation() == ["Plan the launch", "Also book the big room"]


# ─── I4: nothing consumed before a turn starts ───────────────────────────────


async def test_i4_a_turn_that_keeps_failing_before_it_starts_consumes_nothing(
    storage: Storage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    turns = 0

    @contextlib.asynccontextmanager
    async def broken(session: Session[Any]) -> AsyncIterator[None]:
        nonlocal turns
        turns += 1
        raise RuntimeError("the tracing backend is down")
        yield

    runner = runners(make_agent(Script()), turn_context=broken)
    for sent, content in enumerate(["Plan the launch", "Anything else?"], start=1):
        handle = started(await runner.send(ws, thread.id, content))
        with pytest.raises(RuntimeError, match="down"):
            await handle.wait()
        await runner.drain()
        assert (turns, runner.running(thread.id)) == (sent, None), "one turn per command"
        assert await _taken(storage, thread) == 0, "nothing consumed"


# ─── I5: a direct message, and a notice ──────────────────────────────────────


async def test_i5_a_message_committed_directly_starts_no_turn_and_the_next_consumes_it(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(say("Drafted."), *[say("ok")] * 3)
    runner = runners(make_agent(script))
    await started(await runner.send(ws, thread.id, "Plan the launch")).wait()
    await ws.as_actor(BOB).post_message(thread.id, "FYI: the venue changed")
    await ws.as_actor(BOB).post_message(thread.id, "CI is green", kind="notice")
    await settled(thread.id, runner)
    assert runner.running(thread.id) is None, "neither starts a turn"
    started(await runner.send(ws, thread.id, "Anything else?"))
    await settled(thread.id, runner)
    assert script.conversation() == ["Plan the launch", "FYI: the venue changed", "Anything else?"]


async def test_i5_a_notice_in_a_paused_thread_is_never_its_reply(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    runner = runners(_paused_agent(Script(_asking(), say("ok"))))
    paused = started(await runner.send(ws, thread.id, "Plan it"))
    await paused.wait()
    await runner.drain()
    await ws.as_actor(BOB).post_message(thread.id, "CI is green", kind="notice")
    assert await runner.resume(ws, paused.run_id) is None
    assert (await ws.run(paused.run_id)).status == "paused"


# ─── I6: a message is a message ──────────────────────────────────────────────


def _approval_tools() -> FunctionToolset[Session[Gate]]:
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool(requires_approval=True)
    async def publish(ctx: RunContext[Session[Gate]], channel: str) -> str:
        """Publish the plan."""
        return f"published to {channel}"

    return tools


async def test_i6_a_message_committed_directly_in_a_paused_thread_is_its_reply(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    both = ModelResponse(
        parts=[*_asking().parts, *call("publish", call_id="a1", channel="blog").parts]
    )
    runner = runners(_paused_agent(Script(both, say("ok")), tools=[_approval_tools()]))
    paused = started(await runner.send(ws, thread.id, "Go"))
    await paused.wait()
    await runner.drain()
    await ws.as_actor(BOB).post_message(thread.id, "Not before legal signs off")
    answer = AnswerDeferred(run_id=paused.run_id, tool_call_id="q1", answer="Monday")
    assert (await runner.answer(ws, answer)).run is not None
    await settled(thread.id, runner)
    [declined] = [
        (e.actor, e.event.approved, e.event.answer)
        for e in await ws.read(threads={thread.id})
        if isinstance(e.event, DeferredAnswered) and e.event.tool_call_id == "a1"
    ]
    assert declined == (BOB, False, "Not before legal signs off")


async def test_i6_a_reply_that_an_answer_beat_is_the_resumed_runs_prompt(
    storage: Storage, ws: Workspace, there: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(_asking(), *[say("ok")] * 3)
    runner, other = runners(_paused_agent(script)), runners(_paused_agent(script))
    paused = started(await runner.send(ws, thread.id, "Plan it"))
    await paused.wait()
    await runner.drain()
    planning = hold(storage, "runs", after=True, status="paused")  # Bob's plan read it
    message = PostMessage(thread_id=thread.id, content="Tuesday, and book the room")
    sending = asyncio.create_task(runner.execute(ws.as_actor(BOB), message, command_id="c1"))
    await _entered(planning)
    answer = AnswerDeferred(run_id=paused.run_id, tool_call_id="q1", answer="Monday")
    assert (await other.answer(there, answer)).run is None, "the thread is claimed"
    planning.release.set()
    assert (await sending).ok
    await settled(thread.id, runner, other)
    assert (await ws.run(paused.run_id)).status == "completed"
    assert script.answers() == ["Monday"]
    assert script.conversation()[-1] == "Tuesday, and book the room"
