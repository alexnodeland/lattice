"""Approvals lattice's enforcer asks (lattice RFC-0011, ADR-0101), through lattice's own bridge.

A call the enforcer defers pauses its run naming its approval. An answer sent with the Runner
is the store's, given by the person who sends it, and the store's refusal is the answer's. The
Runner follows the approval, so one answered anywhere else, or that closes unanswered, reaches
the thread as the store settled it and resumes the run. The resumed call is given the
approval's id back, and goes ahead on it: never asked again.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic_ai import (
    Agent,
    ApprovalRequired,
    DeferredToolRequests,
    FunctionToolset,
    ModelResponse,
    RunContext,
)
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.toolsets import AbstractToolset

from artifactr.agent import ArtifactWorkspace, Session
from artifactr.core import (
    Actor,
    AnswerDeferred,
    DeferredAnswered,
    ExternalAgentActor,
    Forbidden,
    InvalidState,
    NotFound,
    Recorded,
    RunId,
    SystemActor,
    Thread,
    UserActor,
    acting_for,
)
from artifactr.workspace import Access, Authorize, InMemoryStorage, Workspace, Workspaces
from lattice_core.agents import toolset
from lattice_core.approvals import (
    Answer,
    Answerers,
    Approval,
    ApprovalId,
    ApprovalRequest,
    FakeApprovals,
    NoCoverage,
    NotPending,
    Subject,
    arguments_digest,
)
from lattice_core.capabilities import (
    CallContext,
    Capability,
    FakeProvider,
    JsonObject,
    Registry,
    RunCaller,
    Scope,
    ToolResult,
)
from lattice_core.capabilities import Gate as ActionGate
from lattice_core.enforcement import Enforcer, FakeAudit, FakeCounter, FixedCeilings, FixedTaint
from lattice_core.integrations import Defaults
from lattice_core.settings import SettingsDefaults
from lattice_core.taint import Clean, Taint
from tests.agent.conftest import ALICE, Gate, MakeRunner, Script, ask, call, in_words, say
from tests.artifact_types import Checklist, Note

TOOL = "notes__publish"
"""The tool of the capability ``notes.publish``, as lattice's bridge names it."""

ARGS: JsonObject = {"text": "Weekly update"}
NOW = datetime(2026, 11, 1, 12, tzinfo=UTC)
HOLDERS = frozenset({"alice", "bob", "svc"})
"""Who holds the action the policy asks of an approval's answerers."""


def _capability() -> Capability:
    return Capability.model_validate(
        {
            "name": "notes.publish",
            "version": "1.0.0",
            "description": "Publish a note.",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            "output_schema": None,
            "provider": "builtin",
            "tier": "write",
            "effects": frozenset[str](),
            "reversibility": "none",
            "gate": ActionGate(integration=None, action="notes:publish"),
        }
    )


class _Policy:
    """Every call asks a holder of grantr's action."""

    async def needed(self, _capability: Capability, _context: CallContext, /) -> Answerers:
        return Answerers(action="grantr:answer_approval")


class Store(FakeApprovals):
    """A store whose clock the test moves, and whose answerers hold the action in HOLDERS."""

    def __init__(self) -> None:
        self.now = NOW
        super().__init__(holds=lambda subject, _action: subject.id in HOLDERS, clock=self._clock_)

    def _clock_(self) -> datetime:
        return self.now


class Held(Store):
    """A store whose watch waits until the test releases it, so no follower runs before then."""

    def __init__(self) -> None:
        super().__init__()
        self.released = asyncio.Event()

    async def watch(self, id: ApprovalId, /) -> AsyncIterator[Approval]:
        await self.released.wait()
        async for seen in super().watch(id):
            yield seen


class World:
    """An enforcer of fakes, whose policy asks every call, and an agent offered its tools."""

    def __init__(self, store: FakeApprovals, *, on_behalf_of: str | None = "alice") -> None:
        self.store = store
        self.on_behalf_of = on_behalf_of
        self.provider = FakeProvider(
            "builtin", _capability(), results={"notes.publish": ToolResult(output="published")}
        )

        async def authorize(_context: CallContext, _action: str) -> bool:
            return True

        self.enforcer = Enforcer(
            Registry(self.provider),
            integrations=Defaults({}),
            authorize=authorize,
            ceilings=FixedCeilings(),
            settings=SettingsDefaults({}),
            counter=FakeCounter(),
            taint=FixedTaint(),
            approvals=_Policy(),
            coverage=NoCoverage(),
            store=store,
            audit=FakeAudit(),
            clock=lambda: NOW,
        )

    async def context(self, ctx: RunContext[Session[Gate]]) -> CallContext:
        return CallContext(
            scope=Scope(tenant_id="tenant", workspace_id="ws"),
            caller=RunCaller(id=ctx.deps.run_id, agent="assistant", on_behalf_of=self.on_behalf_of),
            taint=Clean(),
            correlation_id=ctx.deps.run_id,
            surface="portalr",
        )

    async def marked(self, _ctx: RunContext[Session[Gate]], _taint: Taint) -> None:
        return None

    def agent(
        self,
        script: Script,
        *,
        ask: bool = False,
        tools: FunctionToolset[Session[Gate]] | None = None,
    ) -> Agent[Session[Gate], Any]:
        offered: list[AbstractToolset[Session[Gate]]] = [
            toolset(self.enforcer, self.context, self.marked)
        ]
        return Agent(
            script.model,
            deps_type=Session[Gate],
            output_type=[str, DeferredToolRequests],
            toolsets=offered if tools is None else [*offered, tools],
            capabilities=[ArtifactWorkspace(types=[Note, Checklist], ask=ask)],
        )


def _publishing(*after: str) -> Script:
    return Script(call(TOOL, call_id="a1", **ARGS), *(say(text) for text in after or ("Done.",)))


async def _paused(runner: Any, ws: Workspace, thread: Thread) -> RunId:
    """Send a message whose run asks to publish, wait until it pauses, and let it hand over."""
    handle = (await runner.send(ws, thread.id, "Publish the weekly note")).run
    assert handle is not None
    assert isinstance((await handle.wait()).output, DeferredToolRequests)
    await runner.drain()  # its hand-over follows the approval it paused on
    return handle.run_id


async def _until(done: Callable[[], Awaitable[bool]]) -> None:
    """Wait until ``done``, as a follower in the background brings it about, for up to 5s."""
    for _ in range(500):
        if await done():
            return
        await asyncio.sleep(0.01)
    pytest.fail("it never came about")


async def _completed(ws: Workspace, run_id: RunId) -> None:
    async def done() -> bool:
        return (await ws.run(run_id)).status == "completed"

    await _until(done)


async def _answers(ws: Workspace) -> list[tuple[Actor, DeferredAnswered]]:
    return [(e.actor, e.event) for e in await ws.read() if isinstance(e.event, DeferredAnswered)]


def _who(actor: Actor) -> str | None:
    behalf = acting_for(actor)
    return behalf.participant if behalf is not None else actor.participant


def _answer(approved: bool, *, reason: str | None = None) -> Answer:
    return Answer(
        approved=approved,
        arguments_digest=arguments_digest(ARGS),
        surface="portalr",
        reason=reason,
    )


def _refusing(participant: str, action: str) -> Authorize:
    async def authorize(_tenant: str, _workspace: str | None, actor: Actor, access: Access) -> bool:
        return (_who(actor), access.action) != (participant, action)

    return authorize


async def test_a_deferred_call_pauses_naming_its_approval_and_goes_ahead_on_it(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = Store()
    world = World(store)
    script = _publishing("Published.")
    runner = runners(world.agent(script), approvals=store)
    run_id = await _paused(runner, ws, thread)
    [request] = (await ws.run(run_id)).pending
    [asked] = store.all()
    assert (request.kind, request.approval, request.args) == ("approval", asked.id, ARGS)
    await runner.answer(ws, AnswerDeferred(run_id=run_id, tool_call_id="a1", approved=True))
    await _completed(ws, run_id)
    [approval] = store.all()  # the call resumed on its approval, not asking another
    assert approval.state == "approved"
    assert approval.taken_at is not None, "the one call it lets through went ahead"
    assert approval.answer is not None
    answered = approval.answer
    assert (answered.by.id, answered.surface, answered.reason) == ("alice", "portalr", None)
    assert answered.arguments_digest == arguments_digest(ARGS), "bound to what the thread shows"
    assert script.tool_returns(1) == ["published"]
    assert [(_who(actor), event.approved) for actor, event in await _answers(ws)] == [
        ("user:alice", True)
    ]


async def test_a_denial_in_the_thread_is_the_stores_with_its_reason(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = Store()
    world = World(store)
    script = _publishing("Not publishing.")
    runner = runners(world.agent(script), approvals=store)
    run_id = await _paused(runner, ws, thread)
    denied = AnswerDeferred(run_id=run_id, tool_call_id="a1", approved=False, answer=" Not yet. ")
    await runner.answer(ws, denied)
    await _completed(ws, run_id)
    [approval] = store.all()
    assert approval.state == "denied"
    assert approval.answer is not None
    assert approval.answer.reason == "Not yet."
    assert script.tool_returns(1) == [" Not yet. "], "the model is told the person's words"
    assert world.provider.calls == []


async def test_an_approval_answered_on_another_surface_resumes_the_run_for_who_answered(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = Store()
    script = _publishing("Published.")
    runner = runners(World(store).agent(script), approvals=store)
    run_id = await _paused(runner, ws, thread)
    [asked] = store.all()
    await store.answer(asked.id, _answer(True, reason="Looks right."), subject=Subject(id="bob"))
    await _completed(ws, run_id)
    assert [(_who(actor), event.answer) for actor, event in await _answers(ws)] == [
        ("user:bob", "Looks right.")
    ]
    assert script.tool_returns(1) == ["published"]


async def test_one_that_expires_resumes_the_run_with_why_for_whom_it_was_asked(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = Store()
    script = _publishing("It lapsed.")
    runner = runners(World(store).agent(script), approvals=store)
    run_id = await _paused(runner, ws, thread)
    store.now = NOW + timedelta(days=2)
    await store.expire_due()
    await _completed(ws, run_id)
    why = "expired: past its deadline unanswered"
    assert [(_who(a), e.approved, e.answer) for a, e in await _answers(ws)] == [
        ("user:alice", False, why)
    ]
    assert script.tool_returns(1) == [why]


async def test_a_service_principals_answer_reaches_the_thread_as_whom_it_was_asked_for(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = Store()
    runner = runners(World(store).agent(_publishing()), approvals=store)
    run_id = await _paused(runner, ws, thread)
    [asked] = store.all()
    await store.answer(asked.id, _answer(True), subject=Subject(id="svc", service=True))
    await _completed(ws, run_id)
    assert [_who(actor) for actor, _ in await _answers(ws)] == ["user:alice"]


async def test_one_asked_for_no_one_and_closed_unanswered_reaches_the_thread_as_the_runner(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = Store()
    runner = runners(World(store, on_behalf_of=None).agent(_publishing()), approvals=store)
    run_id = await _paused(runner, ws, thread)
    [asked] = store.all()
    await store.withdraw(asked.id, "its run stopped")
    await _completed(ws, run_id)
    [(actor, event)] = await _answers(ws)
    assert (actor, event.answer) == (SystemActor(name="runner"), "withdrawn: its run stopped")


async def test_one_answered_by_a_person_the_thread_refuses_reaches_it_as_the_runner(
    storage: InMemoryStorage, runners: MakeRunner
) -> None:
    workspaces = Workspaces(storage, authorize=_refusing("user:bob", "artifactr:answer_deferred"))
    ws = await workspaces.open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread("Launch")
    store = Store()
    runner = runners(World(store).agent(_publishing()), approvals=store)
    run_id = await _paused(runner, ws, thread)
    [asked] = store.all()
    await store.answer(asked.id, _answer(True), subject=Subject(id="bob"))
    await _completed(ws, run_id)
    assert [actor for actor, _ in await _answers(ws)] == [SystemActor(name="runner")]


async def test_a_message_waits_for_the_approval_and_reaches_the_run_as_it_resumes(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = Store()
    script = _publishing("Published, and the launch mentioned.")
    runner = runners(World(store).agent(script), approvals=store)
    run_id = await _paused(runner, ws, thread)
    sent = await runner.send(ws, thread.id, "Mention the launch too")
    assert sent.run is None, "a message doesn't answer an approval the store keeps"
    assert (await ws.run(run_id)).status == "paused"
    assert [a.state for a in store.all()] == ["pending"]
    await runner.answer(ws, AnswerDeferred(run_id=run_id, tool_call_id="a1", approved=True))
    await _completed(ws, run_id)
    assert "Mention the launch too" in script.prompt_texts(1)


async def test_one_answered_first_elsewhere_is_refused_and_the_thread_takes_the_first_answer(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = Held()
    script = _publishing("Not publishing.")
    runner = runners(World(store).agent(script), approvals=store)
    run_id = await _paused(runner, ws, thread)
    [asked] = store.all()
    await store.answer(asked.id, _answer(False, reason="No."), subject=Subject(id="bob"))
    approving = AnswerDeferred(run_id=run_id, tool_call_id="a1", approved=True)
    with pytest.raises(InvalidState, match=r"was denied by bob on portalr"):
        await runner.answer(ws, approving)
    await _completed(ws, run_id)
    assert [(_who(a), e.approved) for a, e in await _answers(ws)] == [("user:bob", False)]
    assert script.tool_returns(1) == ["No."]


async def test_a_follower_that_finds_the_thread_answered_leaves_it(
    ws: Workspace, thread: Thread, runners: MakeRunner, caplog: pytest.LogCaptureFixture
) -> None:
    store = Held()
    runner = runners(World(store).agent(_publishing()), approvals=store)
    run_id = await _paused(runner, ws, thread)
    await runner.answer(ws, AnswerDeferred(run_id=run_id, tool_call_id="a1", approved=True))
    await _completed(ws, run_id)
    with caplog.at_level(logging.ERROR, logger="artifactr.agent"):
        store.released.set()
        for _ in range(20):
            await asyncio.sleep(0)
    assert len(await _answers(ws)) == 1
    assert caplog.records == []


class _FollowedFirst(Held):
    """A store whose answer reaches the thread before the answer's own command does."""

    def __init__(self) -> None:
        super().__init__()
        self.thread: Workspace | None = None
        self.run_id: RunId | None = None

    async def answer(self, id: ApprovalId, answer: Answer, /, *, subject: Subject) -> Approval:
        settled = await super().answer(id, answer, subject=subject)
        assert self.thread is not None
        assert self.run_id is not None
        by = self.thread.as_actor(UserActor(id=subject.id))
        await by.commit(
            AnswerDeferred(run_id=self.run_id, tool_call_id="a1", approved=answer.approved)
        )
        return settled


async def test_the_stores_answer_reaching_the_thread_first_is_the_persons(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = _FollowedFirst()
    runner = runners(World(store).agent(_publishing()), approvals=store)
    run_id = await _paused(runner, ws, thread)
    store.thread, store.run_id = ws, run_id
    sent = await runner.answer(ws, AnswerDeferred(run_id=run_id, tool_call_id="a1", approved=True))
    assert sent.outcome == Recorded(run_id=run_id)
    await _completed(ws, run_id)


async def test_a_runner_without_the_store_refuses_an_answer_to_one(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = Store()
    runner = runners(World(store).agent(_publishing()))
    run_id = await _paused(runner, ws, thread)
    approving = AnswerDeferred(run_id=run_id, tool_call_id="a1", approved=True)
    with pytest.raises(InvalidState, match="answered where the application keeps them"):
        await runner.answer(ws, approving)
    assert [a.state for a in store.all()] == ["pending"]


@pytest.mark.parametrize(
    "actor",
    [ExternalAgentActor(client_id="claude", on_behalf_of=ALICE), SystemActor(name="ops")],
)
async def test_only_a_person_answers_one(
    ws: Workspace, thread: Thread, runners: MakeRunner, actor: Actor
) -> None:
    store = Store()
    runner = runners(World(store).agent(_publishing()), approvals=store)
    run_id = await _paused(runner, ws, thread)
    approving = AnswerDeferred(run_id=run_id, tool_call_id="a1", approved=True)
    with pytest.raises(Forbidden, match="answered by a person"):
        await runner.answer(ws.as_actor(actor), approving)
    assert [a.state for a in store.all()] == ["pending"]


async def test_artifactrs_refusal_comes_before_the_stores(
    storage: InMemoryStorage, runners: MakeRunner
) -> None:
    workspaces = Workspaces(storage, authorize=_refusing("user:carol", "artifactr:answer_deferred"))
    ws = await workspaces.open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread("Launch")
    store = Store()
    runner = runners(World(store).agent(_publishing()), approvals=store)
    run_id = await _paused(runner, ws, thread)
    approving = AnswerDeferred(run_id=run_id, tool_call_id="a1", approved=True)
    with pytest.raises(Forbidden, match="artifactr:answer_deferred"):
        await runner.answer(ws.as_actor(UserActor(id="carol")), approving)
    assert [a.state for a in store.all()] == ["pending"]


async def test_one_the_store_doesnt_let_answer_is_forbidden_and_left_waiting(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = Store()
    runner = runners(World(store).agent(_publishing()), approvals=store)
    run_id = await _paused(runner, ws, thread)
    approving = AnswerDeferred(run_id=run_id, tool_call_id="a1", approved=True)
    with pytest.raises(Forbidden, match="carol may not answer"):
        await runner.answer(ws.as_actor(UserActor(id="carol")), approving)
    assert [a.state for a in store.all()] == ["pending"]
    assert (await ws.run(run_id)).status == "paused"


async def test_one_the_store_doesnt_know_is_not_found(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    runner = runners(World(Store()).agent(_publishing()), approvals=Held())
    run_id = await _paused(runner, ws, thread)
    approving = AnswerDeferred(run_id=run_id, tool_call_id="a1", approved=True)
    with pytest.raises(NotFound, match="approval"):
        await runner.answer(ws, approving)


async def test_an_answer_to_other_arguments_than_the_stores_is_refused(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    asking, other = Store(), Held()
    runner = runners(World(asking).agent(_publishing()), approvals=other)
    run_id = await _paused(runner, ws, thread)
    [asked] = asking.all()
    fields = asked.model_dump(include=set(ApprovalRequest.model_fields))
    await other.ask(ApprovalRequest.model_validate(fields | {"arguments_digest": "b" * 64}))
    approving = AnswerDeferred(run_id=run_id, tool_call_id="a1", approved=True)
    with pytest.raises(InvalidState, match="asks about other arguments"):
        await runner.answer(ws, approving)


async def test_core_refuses_what_the_store_is_not_asked(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = Store()
    script = Script(
        lambda _: call(TOOL, call_id="a1", **ARGS).__class__(
            parts=[*ask("q1", "Which day?").parts, *call(TOOL, call_id="a1", **ARGS).parts]
        ),
        say("Done."),
    )
    runner = runners(World(store).agent(script, ask=True), approvals=store)
    run_id = await _paused(runner, ws, thread)
    with pytest.raises(InvalidState, match="an approval needs approved"):
        await runner.answer(ws, AnswerDeferred(run_id=run_id, tool_call_id="a1", answer="yes"))
    await runner.answer(ws, AnswerDeferred(run_id=run_id, tool_call_id="a1", approved=True))
    with pytest.raises(InvalidState, match="already answered"):
        await runner.answer(ws, AnswerDeferred(run_id=run_id, tool_call_id="a1", approved=False))
    question = AnswerDeferred(run_id=run_id, tool_call_id="q1", answer=in_words("Monday"))
    await runner.answer(ws, question)
    await _completed(ws, run_id)
    with pytest.raises(InvalidState, match="not paused"):
        await runner.answer(ws, AnswerDeferred(run_id=run_id, tool_call_id="a1", approved=True))
    assert [a.state for a in store.all()] == ["approved"]


async def test_recovering_follows_each_approval_a_paused_run_waits_on_once(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = Store()
    script = Script(
        lambda _: call(TOOL, call_id="a1", **ARGS).__class__(
            parts=[*ask("q1", "Which day?").parts, *call(TOOL, call_id="a1", **ARGS).parts]
        ),
        say("Done."),
    )
    first = runners(World(store).agent(script, ask=True))  # keeps no store: follows nothing
    run_id = await _paused(first, ws, thread)
    await first.recover(ws)
    await first.aclose()
    await first.recover(ws)  # a closed runner follows nothing either
    second = runners(World(store).agent(script, ask=True), approvals=store)
    await second.recover(ws)
    await second.recover(ws)  # followed already: once
    [asked] = store.all()
    await store.answer(asked.id, _answer(True), subject=Subject(id="bob"))

    async def answered() -> bool:
        return "a1" in (await ws.run(run_id)).answers

    await _until(answered)
    await second.recover(ws)  # the question, which the store doesn't keep, and the answered call
    assert (await ws.run(run_id)).status == "paused", "the question is still open"
    assert len(await _answers(ws)) == 1


async def test_a_follower_that_fails_is_logged(
    ws: Workspace, thread: Thread, runners: MakeRunner, caplog: pytest.LogCaptureFixture
) -> None:
    store = Store()
    first = runners(World(store).agent(_publishing()))
    run_id = await _paused(first, ws, thread)
    second = runners(World(store).agent(_publishing()), approvals=FakeApprovals())
    with caplog.at_level(logging.ERROR, logger="artifactr.agent"):
        await second.recover(ws)

        async def logged() -> bool:
            return any("following approval" in r.getMessage() for r in caplog.records)

        await _until(logged)
    assert (await ws.run(run_id)).status == "paused"


# ─── withdrawn when its run ends before it pauses (ADR-0102) ─────────────────────────────────


def _alongside(
    then: Callable[[RunContext[Session[Gate]]], Awaitable[str]],
) -> FunctionToolset[Session[Gate]]:
    """A tool called beside the deferred one, which waits until its approval is asked, then
    does ``then``: the window in which a run stops or fails before it pauses."""
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool
    async def beside(ctx: RunContext[Session[Gate]]) -> str:
        async def asked() -> bool:
            return bool(ctx.deps.asked)

        await _until(asked)
        return await then(ctx)

    return tools


def _both() -> Script:
    """A model that calls the deferred tool and :func:`_alongside`'s in one response."""
    return Script(
        ModelResponse(
            parts=[
                ToolCallPart(tool_name=TOOL, args=ARGS, tool_call_id="a1"),
                ToolCallPart(tool_name="beside", args={}, tool_call_id="b1"),
            ]
        ),
        say("Unreached."),
    )


async def _stopped_while_asked(
    store: FakeApprovals, ws: Workspace, thread: Thread, runners: MakeRunner, **options: Any
) -> RunId:
    """Start a run whose approval is asked, and stop it before it pauses."""
    asked = asyncio.Event()

    async def hold(_ctx: RunContext[Session[Gate]]) -> str:
        asked.set()
        await asyncio.Event().wait()
        return "never"

    runner = runners(World(store).agent(_both(), tools=_alongside(hold)), **options)
    handle = (await runner.send(ws, thread.id, "Publish the weekly note")).run
    assert handle is not None
    await asyncio.wait_for(asked.wait(), 5)
    assert await runner.stop(handle.run_id)
    return handle.run_id


async def test_a_run_stopped_before_it_pauses_withdraws_the_approval_it_asked(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = Store()
    run_id = await _stopped_while_asked(store, ws, thread, runners, approvals=store)
    assert (await ws.run(run_id)).status == "stopped"
    [approval] = store.all()
    assert (approval.state, approval.reason) == ("withdrawn", "its run was stopped")
    assert approval.answer is None, "no one answered it: nothing would have taken it"


async def test_a_run_that_fails_before_it_pauses_withdraws_the_approval_it_asked(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = Store()

    async def fail(_ctx: RunContext[Session[Gate]]) -> str:
        raise RuntimeError("the disk is full")

    runner = runners(World(store).agent(_both(), tools=_alongside(fail)), approvals=store)
    handle = (await runner.send(ws, thread.id, "Publish the weekly note")).run
    assert handle is not None
    with pytest.raises(RuntimeError, match="the disk is full"):
        await handle.wait()
    assert (await ws.run(handle.run_id)).status == "failed"
    [approval] = store.all()
    assert (approval.state, approval.reason) == ("withdrawn", "its run failed")


async def test_one_answered_before_its_run_stopped_is_left_as_it_was_answered(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    class AnsweredFirst(Store):
        """A store in which bob approves an approval just before its run withdraws it."""

        async def withdraw(self, id: ApprovalId, reason: str, /) -> Approval:
            await self.answer(id, _answer(True), subject=Subject(id="bob"))
            return await super().withdraw(id, reason)

    store = AnsweredFirst()
    await _stopped_while_asked(store, ws, thread, runners, approvals=store)
    [approval] = store.all()
    assert approval.state == "approved", "the answer came first; the withdrawal is refused"
    with pytest.raises(NotPending):
        await store.withdraw(approval.id, "again")


async def test_a_store_that_fails_to_withdraw_one_is_logged_and_it_expires_at_its_deadline(
    ws: Workspace, thread: Thread, runners: MakeRunner, caplog: pytest.LogCaptureFixture
) -> None:
    class Failing(Store):
        async def withdraw(self, id: ApprovalId, reason: str, /) -> Approval:
            raise ConnectionError("the store is down")

    store = Failing()
    with caplog.at_level(logging.ERROR, logger="artifactr.agent"):
        run_id = await _stopped_while_asked(store, ws, thread, runners, approvals=store)
    assert (await ws.run(run_id)).status == "stopped", "the run ends all the same"
    [approval] = store.all()
    assert approval.state == "pending"
    assert any(
        f"withdrawing approval {approval.id} of run {run_id} failed" in record.getMessage()
        for record in caplog.records
    )


async def test_a_runner_given_no_store_leaves_one_its_run_asked(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = Store()  # the enforcer's, which the application didn't give the Runner
    await _stopped_while_asked(store, ws, thread, runners)
    [approval] = store.all()
    assert approval.state == "pending", "it expires at its deadline"


async def test_a_tools_own_approval_names_none_and_leaves_the_store_alone(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    store = Store()
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool
    async def confirm(ctx: RunContext[Session[Gate]]) -> str:
        if not ctx.tool_call_approved:
            raise ApprovalRequired  # the application's own, which artifactr's thread answers
        return "confirmed"

    script = Script(call("confirm", call_id="c1"), say("Done."))
    runner = runners(World(store).agent(script, tools=tools), approvals=store)
    handle = (await runner.send(ws, thread.id, "Confirm it")).run
    assert handle is not None
    assert isinstance((await handle.wait()).output, DeferredToolRequests)
    [request] = (await ws.run(handle.run_id)).pending
    assert (request.kind, request.approval) == ("approval", None)
    assert store.all() == (), "nothing was asked of the store, so nothing is withdrawn"
