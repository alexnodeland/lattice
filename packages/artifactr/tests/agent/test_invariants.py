"""ADR-0055's invariants, each tested in memory and on PostgreSQL, in busy workspaces.

- I1: every message in a thread's log, notices aside, is consumed exactly once.
- I2: its consumption is recorded in the transaction of the write that consumes it.
- I3: a claim is never held without a task, nor released, while more was asked than taken,
  without a hand-over that reads the asks after the release.
- I4: a turn that fails or is stopped before it starts consumes nothing, and hands over if
  more was asked meanwhile.
- I5: a message committed directly starts no turn, and the next turn consumes it, as does one
  asked for with ``Runner.ask``. A notice is never a prompt or a reply.
- I6: a message is a message: in a paused thread, the oldest message not consumed is the reply,
  however it was committed.
- I7, the upgrade point, is in ``test_upgrade.py``.

Each test holds one storage call at a :class:`Gate`, patched onto the storage it runs on. The
last section is what the TLA+ spec in docs/artifactr/spec found, each trace run against the code:
#249's tests and #252's run in memory alone, with a storage clock moved on; #252's fails, a strict
``xfail``, until it is decided.
"""

import asyncio
import contextlib
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic_ai import Agent, DeferredToolRequests, FunctionToolset, ModelResponse, RunContext

from artifactr.agent import ArtifactWorkspace, Session, function_model
from artifactr.agent.runner import _reply
from artifactr.core import (
    AgentActor,
    AnswerDeferred,
    DeferredAnswered,
    DeferredRequest,
    PostMessage,
    RunPaused,
    RunStarted,
    Thread,
    UserActor,
)
from artifactr.sql import SqlStorage, create_schema
from artifactr.workspace import (
    InMemoryStorage,
    Scope,
    Storage,
    ThreadBusy,
    Workspace,
    Workspaces,
)
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


@pytest.mark.parametrize("ends", ["its send is cancelled", "its run is stopped before it starts"])
async def test_i3_a_command_that_asked_before_its_holder_read_is_handed_over(
    storages: tuple[Storage, Storage],
    ws: Workspace,
    there: Workspace,
    thread: Thread,
    runners: MakeRunner,
    ends: str,
) -> None:
    here_storage, there_storage = storages
    beginning = Gate()

    @contextlib.asynccontextmanager
    async def begins(session: Session[Any]) -> AsyncGenerator[None]:
        if not beginning.release.is_set():
            await beginning.wait()
        yield

    script = Script(*[say("ok")] * 4)
    runner = runners(make_agent(script), turn_context=begins)
    other = runners(make_agent(script))
    stalled = hold(there_storage, "acquire_lease")  # Bob asked, and stalls before he claims
    bystander = asyncio.create_task(other.send(there.as_actor(BOB), thread.id, "Also book"))
    await _entered(stalled)
    planning = hold(here_storage, "runs", status="paused")
    sending = asyncio.create_task(runner.send(ws, thread.id, "Plan"))
    await _entered(planning)  # its holder read Bob's ask, and holds the thread
    if ends == "its run is stopped before it starts":
        planning.release.set()
        started(await sending)
        await _entered(beginning)
    stalled.release.set()
    assert (await bystander).run is None, "refused: its holder hands the thread over"
    if ends == "its send is cancelled":
        sending.cancel()
        planning.release.set()
        with contextlib.suppress(asyncio.CancelledError):
            await sending
    else:
        assert await runner.stop(started(await sending).run_id)
    beginning.release.set()
    await settled(thread.id, runner, other)
    assert script.conversation() == ["Also book", "Plan"], "handed over, not left for a command"


@pytest.mark.parametrize("ends", ["fails", "is stopped"])
async def test_i3_a_message_left_to_a_holder_that_never_starts_is_handed_over(
    ws: Workspace, there: Workspace, thread: Thread, runners: MakeRunner, ends: str
) -> None:
    held = Gate()

    @contextlib.asynccontextmanager
    async def begins(session: Session[Any]) -> AsyncGenerator[None]:
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
    async def broken(session: Session[Any]) -> AsyncGenerator[None]:
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


async def test_i4_a_claimant_that_fails_after_a_command_asked_leaves_it_to_the_next_command(
    storages: tuple[Storage, Storage],
    ws: Workspace,
    there: Workspace,
    thread: Thread,
    runners: MakeRunner,
) -> None:
    storage, there_storage = storages
    script = Script(*[say("ok")] * 4)
    runner, other = runners(make_agent(script)), runners(make_agent(script))
    stalled = hold(there_storage, "acquire_lease")  # Bob asked, and stalls before he claims
    bystander = asyncio.create_task(other.send(there.as_actor(BOB), thread.id, "Also book"))
    await _entered(stalled)
    planning = hold(storage, "runs", status="paused", raises=ConnectionError("it blinked"))
    sending = asyncio.create_task(runner.send(ws, thread.id, "Plan"))
    await _entered(planning)
    stalled.release.set()
    assert (await bystander).run is None
    planning.release.set()
    with pytest.raises(ConnectionError):
        await sending
    await settled(thread.id, runner, other)
    assert runner.running(thread.id) is None, "a failure hands over only what was asked after"
    started(await runner.send(ws, thread.id, "Hello?"))
    await settled(thread.id, runner, other)
    assert script.conversation() == ["Also book", "Plan", "Hello?"]


async def test_i4_two_processes_whose_plans_fail_now_and_then_consume_each_message_once(
    storages: tuple[Storage, Storage],
    ws: Workspace,
    there: Workspace,
    thread: Thread,
    runners: MakeRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    here_storage = storages[0]
    reads, runs = [0], here_storage.runs

    async def blinks(*args: Any, **kwargs: Any) -> Any:
        found = await runs(*args, **kwargs)
        if kwargs.get("status") == "paused":
            reads[0] += 1
            if reads[0] % 3 == 1:
                raise ConnectionError("it blinked")
        return found

    monkeypatch.setattr(here_storage, "runs", blinks)
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
        with contextlib.suppress(ConnectionError):
            await runner.send(handle, thread.id, f"m{index}")

    await asyncio.gather(*(send(index) for index in range(12)))
    await settled(thread.id, here_runner, there_runner)
    monkeypatch.setattr(here_storage, "runs", runs)
    await there_runner.send(there, thread.id, "last")
    await settled(thread.id, here_runner, there_runner)
    assert sorted(recorder.prompts) == sorted([*(f"m{index}" for index in range(12)), "last"])


async def test_i4_a_send_that_fails_before_it_reads_hands_nothing_over(
    storage: Storage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(say("ok"))
    runner = runners(make_agent(script))
    hold(storage, "save_cursor", raises=RuntimeError("storage is down")).release.set()
    with pytest.raises(RuntimeError, match="storage is down"):
        await runner.send(ws, thread.id, "Plan the launch")
    assert not runner._handovers, "a failure that read nothing hands nothing over"
    await settled(thread.id, runner)
    assert not script.requests, "its message waits for the thread's next command, as I4 says"


async def test_i4_a_cancelled_error_no_one_asked_for_is_a_failure_and_never_spins(
    storage: Storage,
    ws: Workspace,
    thread: Thread,
    runners: MakeRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans, runs = [0], storage.runs

    async def interrupted(*args: Any, **kwargs: Any) -> Any:
        found = await runs(*args, **kwargs)
        if kwargs.get("status") == "paused":
            plans[0] += 1
            if plans[0] <= 10:  # as a storage call's own cancellation surfaces; a spin ends
                raise asyncio.CancelledError
        return found

    monkeypatch.setattr(storage, "runs", interrupted)
    script = Script(*[say("ok")] * 3)
    runner = runners(make_agent(script))
    with pytest.raises(asyncio.CancelledError):
        await runner.send(ws, thread.id, "Plan the launch")
    await runner.drain()
    assert plans[0] == 1, "no one cancelled it: it hands over only what was asked after"
    monkeypatch.setattr(storage, "runs", runs)
    started(await runner.send(ws, thread.id, "Hello?"))
    await settled(thread.id, runner)
    assert script.conversation() == ["Plan the launch", "Hello?"]


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


async def test_i5_a_message_whose_ask_was_lost_is_consumed_once_its_thread_is_asked(
    ws: Workspace, there: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(say("Noted."), *[say("ok")] * 3)
    runner = runners(make_agent(script))
    await ws.post_message(thread.id, "CI is green", kind="notice")
    assert await runner.ask(there, thread.id) is None, "a notice asks for nothing"
    await ws.post_message(thread.id, "The venue changed")  # the send stopped before it asked
    handle = await runner.ask(there, thread.id)
    assert handle is not None
    await handle.wait()
    await settled(thread.id, runner)
    assert await runner.ask(ws, thread.id) is None, "consumed, so asking again starts nothing"
    assert script.conversation() == ["The venue changed"]


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


# ─── found by the TLA+ spec (docs/artifactr/spec), not yet fixed ─────────────
#
# Each test is the spec's trace for one issue, against the code, and fails until the issue is
# fixed: strict, so a fix that makes it pass removes its mark.


class _Clock:
    """The storage's clock, which a test moves on, as another process's clock may be."""

    def __init__(self) -> None:
        self.now = datetime(2026, 10, 16, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def _held_at_its_start(gate: Gate) -> Any:
    """A turn context that holds each turn at ``gate`` as it begins, before run_started."""

    @contextlib.asynccontextmanager
    async def begins(session: Session[Any]) -> AsyncGenerator[None]:
        await gate.wait()
        yield

    return begins


async def _two_holders_after_a_lapse(runners: MakeRunner) -> tuple[list[str], int]:
    """The prompts two processes' runs were given, and the runs started, after a lapse (#249).

    The first process plans a run for the message, and is held before its run records its
    start. The storage's clock passes the claim's TTL, as across a stall or a skewed clock, so
    the second process's claim is granted, and it plans from the same `taken`. The first run's
    start is fenced by its claim, which it no longer has, so it fails before it starts.
    """
    clock = _Clock()
    storage = InMemoryStorage(clock=clock)
    ws = await Workspaces(storage).open(SCOPE.tenant_id, SCOPE.workspace_id, actor=ALICE)
    thread = await ws.create_thread("Launch")
    recorder = Recorder()

    def agent() -> Agent[Session[Any], str]:
        return Agent(
            function_model(recorder.respond),
            deps_type=Session[Any],
            capabilities=[ArtifactWorkspace(types=[Note, Checklist])],
        )

    starting = Gate()
    here = runners(agent(), turn_context=_held_at_its_start(starting))
    there = runners(agent())
    first = started(await here.send(ws, thread.id, "Plan the launch"))
    await _entered(starting)
    clock.now += timedelta(minutes=1)
    second = await there.ask(ws, thread.id)
    assert second is not None, "the lapsed claim was granted again"
    await second.wait()
    starting.release.set()
    with pytest.raises(ThreadBusy):
        await first.wait()
    await settled(thread.id, here, there)
    return recorder.prompts, len(await ws.runs(thread_id=thread.id))


async def test_i1_a_claim_that_lapses_as_its_run_starts_lets_no_second_run_take_its_prompt(
    runners: MakeRunner,
) -> None:
    prompts, _ = await _two_holders_after_a_lapse(runners)
    assert prompts == ["Plan the launch"]


async def test_i3_a_claim_that_lapses_as_its_run_starts_leaves_one_run(
    runners: MakeRunner,
) -> None:
    _, runs = await _two_holders_after_a_lapse(runners)
    assert runs == 1


async def test_i1_a_reply_whose_claim_another_holder_took_answers_nothing(
    ws: Workspace, thread: Thread
) -> None:
    agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_1"))
    await agent.record(RunStarted(run_id="run_1", thread_id=thread.id))
    question = DeferredRequest(tool_call_id="q1", tool_name="ask_user", kind="question")
    await agent.record(RunPaused(run_id="run_1", thread_id=thread.id, requests=(question,)))
    await ws.post_message(thread.id, "Tuesday")
    [reply] = await ws.read(threads={thread.id}, last=1)
    run = await ws.run("run_1")
    async with ws.claim_thread(thread.id, holder="claim_2"):
        with pytest.raises(ThreadBusy):  # not refused as answered, which would plan again
            await _reply(
                ws,
                run,
                reply,
                cursor=(f"artifactr.runner/{thread.id}/taken", reply.seq),
                claim=(thread.id, "claim_1"),
            )
    assert not (await ws.run("run_1")).answers, "the request is left to the new holder"


async def test_i3_a_claim_granted_as_its_send_is_cancelled_is_released(
    storage: Storage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(*[say("ok")] * 2)
    runner = runners(make_agent(script))
    # The lease is taken, and the call cancelled after, as SQL storage runs its calls to the end.
    claiming = hold(storage, "acquire_lease", after=True)
    sending = asyncio.create_task(runner.send(ws, thread.id, "Plan the launch"))
    await _entered(claiming)
    sending.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await sending
    await settled(thread.id, runner)
    assert script.requests, "its hand-over took the message"


async def test_i3_a_send_cancelled_between_its_ask_and_its_claim_is_handed_over(
    storage: Storage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(*[say("ok")] * 2)
    runner = runners(make_agent(script))
    reading = hold(storage, "cursor")  # _take's first read, once the ask is saved
    sending = asyncio.create_task(runner.send(ws, thread.id, "Plan the launch"))
    await _entered(reading)
    sending.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await sending
    await settled(thread.id, runner)
    assert script.requests, "handed over, not left for the next command"


async def test_i3_a_send_cancelled_as_its_ask_is_saved_is_handed_over(
    storage: Storage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(*[say("ok")] * 2)
    runner = runners(make_agent(script))
    # The ask is saved, and the call cancelled after, as storage runs its calls to the end.
    asking = hold(storage, "save_cursor", after=True)
    sending = asyncio.create_task(runner.send(ws, thread.id, "Plan the launch"))
    await _entered(asking)
    sending.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await sending
    await settled(thread.id, runner)
    assert script.requests, "handed over, not left for the next command"


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="#252: what a dead holder was asked waits for a command",
)
async def test_i3_a_message_asked_while_its_holder_dies_is_taken_once_its_claim_lapses(
    runners: MakeRunner,
) -> None:
    clock = _Clock()
    storage = InMemoryStorage(clock=clock)
    ws = await Workspaces(storage).open(SCOPE.tenant_id, SCOPE.workspace_id, actor=ALICE)
    thread = await ws.create_thread("Launch")
    script = Script(*[say("ok")] * 3)
    # The first process holds the thread, and stops for good: it stands for one that died.
    dead = Gate()
    dying = runners(make_agent(script), turn_context=_held_at_its_start(dead))
    living = runners(make_agent(script))
    started(await dying.send(ws, thread.id, "Plan the launch"))
    await _entered(dead)
    sent = await living.send(ws.as_actor(BOB), thread.id, "Also book the big room")
    if sent.run is not None:  # not the failure the mark expects
        pytest.fail("the dead process's claim did not refuse the message")
    clock.now += timedelta(minutes=1)  # the dead claim lapses
    await settled(thread.id, living)
    assert script.requests, "the message is taken once the dead claim lapses"
