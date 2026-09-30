"""The Runner: starts, steers, pauses, resumes and stops agent runs in threads.

Surfaces (WebSocket, REST, MCP) share one Runner, so a message behaves the same wherever it
comes from:

- In an idle thread, a message starts a run.
- In a busy thread, it steers the running agent: the run's watcher delivers it.
- In a thread whose run is paused on questions, it is the reply: questions are answered with
  it, approvals are declined with it as the reason, and the run resumes.

The log decides what each turn carries out (ADR-0055). A thread's messages are taken in order,
each by one turn: as the prompt of a run, the reply to a paused one, or through the watcher of
the run that holds the thread. A message or an answer sent with the runner asks for a turn;
whoever holds the thread next, in any process, starts it with the oldest message not yet
taken, and a run that ends hands its thread over the same way. A message committed directly,
without the runner, asks for nothing, so it starts no turn, but the thread's next turn takes it.

A notice, a ``post_message`` of kind ``notice``, is for people: it is committed as it is, so it
starts no run, and the thread's agent is not told unless its capability asks for notices
(ADR-0051).

Runs are asyncio tasks in this process. Their live frames go to :attr:`Runner.live`, where any
connection can :meth:`Runner.watch` them. An application stops them with :meth:`Runner.aclose`
as it shuts down, before its storage closes. A run whose process dies instead stays ``running``
until its thread is next claimed, and is then recorded as failed, with the reason ``abandoned``.
A run whose claim lapses while its process lives on is cancelled then; if the thread's next run
records it as abandoned first, the capability drops what it records afterwards.

Surfaces send each command with the id its client chose to :meth:`Runner.execute`, which
remembers results in :class:`~artifactr.agent.CommandResults`, so a retried command is carried
out once (ADR-0048).

Each turn (a run started by a message, or resumed by answers) is traced as its own trace, an
``invoke_workflow turn`` span linked to the span that started it (ADR-0035). The thread is the
session: it is the turn's ``session.id`` and pydantic-ai's ``conversation_id``, and it is placed
in OpenTelemetry baggage for the turn's duration.

When a turn ends, the Runner hands it to its evaluators, which judge it in the background
(ADR-0044), so evaluation never slows or fails the turn.
"""

import asyncio
import contextlib
import contextvars
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal, Protocol

from opentelemetry import baggage, trace
from opentelemetry import context as otel_context
from opentelemetry.metrics import MeterProvider
from opentelemetry.trace import (
    INVALID_SPAN_CONTEXT,
    Link,
    Span,
    SpanContext,
    StatusCode,
    TracerProvider,
)
from pydantic_ai import Agent, AgentRunResult, DeferredToolRequests, DeferredToolResults, ToolDenied

from artifactr.agent.live import FanoutChannel, forward_live
from artifactr.agent.results import CommandKey, CommandResults, InMemoryCommandResults
from artifactr.agent.session import Session, Trigger, last_seen, load_history
from artifactr.core import (
    Actor,
    AgentActor,
    AnswerDeferred,
    Command,
    CommandResult,
    DeferredAnswered,
    Envelope,
    InvalidState,
    LiveFrame,
    MessageId,
    MessagePosted,
    NotFound,
    Outcome,
    PostMessage,
    Recorded,
    Rejection,
    Run,
    RunEnded,
    RunId,
    StopRun,
    SystemActor,
    ThreadId,
    new_id,
    new_message_id,
    new_run_id,
)
from artifactr.telemetry import Telemetry, attribution, parse_traceparent
from artifactr.telemetry.attributes import (
    ERROR_TYPE,
    GEN_AI_OPERATION_NAME,
    GEN_AI_WORKFLOW_NAME,
    LANGFUSE_OBSERVATION_TYPE,
    SESSION_ID,
    TENANT_ID,
    TURN_OUTCOME,
    TURN_TRIGGER,
    WORKSPACE_ID,
)
from artifactr.telemetry.metrics import TURN_DURATION, TURNS
from artifactr.workspace import ThreadBusy, Workspace

logger = logging.getLogger("artifactr.agent")

type TurnContext = Callable[[Session[Any]], AbstractAsyncContextManager[object]]
"""A context entered around each turn, inside the turn's span, given the run's session.

It is a port (ADR-0034): a backend that attributes a turn in its own way, such as Langfuse's
propagated trace attributes, implements it, and the Runner stays free of the backend.
"""

type TurnOutcome = Literal["completed", "paused", "failed", "stopped"]
"""How a turn ended: the agent finished, paused on questions, raised, or was stopped."""

_ABANDONED = "the run was abandoned: its claim lapsed"
"""The error recorded for a run whose claim lapsed before it ended, whether its process stopped
or lived on."""


@dataclass(frozen=True)
class EndedTurn:
    """A turn that has ended, as the Runner hands it to its evaluators."""

    session: Session[Any]
    """The turn's session: its workspace handle (acting as the agent), thread and run."""

    outcome: TurnOutcome
    """How the turn ended."""

    span: SpanContext
    """The turn's ``invoke_workflow turn`` span, on whose trace evaluations are recorded."""


class TurnEvaluator(Protocol):
    """Judges turns after they end: a port (ADR-0034, ADR-0044).

    ``artifactr.evals.OnlineEvaluator`` adapts evalr's online evaluation to it; the Runner
    knows nothing of evalr.
    """

    def submit(self, turn: EndedTurn) -> object:
        """Start judging a turn that ended, in the background, and return at once.

        It must not wait for the evaluation: the Runner calls it as the turn ends. A failure
        it raises is recorded on the turn's span, never raised to the turn.
        """
        ...


@dataclass(frozen=True)
class RunHandle:
    """A run started by a :class:`Runner`."""

    run_id: RunId
    thread_id: ThreadId
    task: "asyncio.Task[AgentRunResult[Any]]"

    async def wait(self) -> AgentRunResult[Any]:
        """Wait for the run to finish (or pause) and return its result."""
        return await self.task


@dataclass(frozen=True)
class Sent:
    """What posting a message, or an answer, did."""

    outcome: Recorded
    """The recorded message or answer, with the ``run_id`` of :attr:`run`, if there is one."""

    run: RunHandle | None
    """The run it started or resumed, or ``None`` when it started none, which is not a failure:

    - The thread's run is active, in this process or another, so the message steers it. If
      that run is ending or pausing and takes no more messages, it hands the thread over as it
      releases it, and the next turn takes the message.
    - Another message or answer took the thread first, and its turn takes this one too.
    - An answer leaves some of the paused run's requests unanswered, so the run waits for them.
    - The runner is closed (:meth:`Runner.aclose`), as the application shuts down. The thread's
      next claimant, in any process, carries the message or answer out.

    The run it started may take an older message first: the thread's oldest message that no
    turn has taken. A message in an idle thread, such as one just created, starts a run unless
    another starts one first, so code that owns its thread can assert that ``run`` is set.
    """


class Runner[AppDepsT]:
    """Runs an agent in workspace threads.

    Args:
        agent: The agent, whose ``deps_type`` is ``Session[AppDepsT]`` and which has the
            :class:`~artifactr.agent.ArtifactWorkspace` capability.
        app: The application's dependencies, passed to every run as ``ctx.deps.app``.
        live: Where runs' live frames go. Defaults to an in-process fan-out.
        agent_name: How the agent is named in the workspace.
        claim_ttl: How long a thread claim lasts without renewal, should this process die. Once
            it lapses, the thread's next run records the run left behind as abandoned, and a run
            of this process whose claim lapsed is cancelled. A claim is renewed every third of
            it, so a run survives one failed renewal, or storage that stalls for about two thirds
            of it. It must exceed the clock skew between replicas.
        tracer_provider: Where turn spans go. Defaults to the global tracer provider.
        meter_provider: Where turn metrics go. Defaults to the global meter provider.
        turn_context: Entered around each turn, inside its span.
        evaluators: Given each turn as it ends, to judge it in the background, such as
            ``artifactr.evals.OnlineEvaluator``s.
        results: Where :meth:`execute` remembers commands' results. Defaults to the 10,000
            most recent, in this process.
    """

    def __init__(
        self,
        agent: Agent[Session[AppDepsT], Any],
        *,
        app: AppDepsT,
        live: FanoutChannel | None = None,
        agent_name: str = "assistant",
        claim_ttl: timedelta = timedelta(seconds=30),
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
        turn_context: TurnContext | None = None,
        evaluators: Sequence[TurnEvaluator] = (),
        results: CommandResults | None = None,
    ) -> None:
        self._agent = agent
        self._results = results or InMemoryCommandResults()
        self._turn_context = turn_context
        self._evaluators = tuple(evaluators)
        self._app = app
        self.live = live or FanoutChannel()
        self._agent_name = agent_name
        self._claim_ttl = claim_ttl
        self._runs: dict[RunId, RunHandle] = {}
        self._handovers: set[asyncio.Task[None]] = set()
        self._closed = False
        self._telemetry = Telemetry(tracer_provider=tracer_provider, meter_provider=meter_provider)

    async def execute(
        self, workspace: Workspace, command: Command | StopRun, *, command_id: str
    ) -> CommandResult:
        """Carry out a command the way every surface should, once per ``command_id``.

        Messages and answers go through :meth:`send` and :meth:`answer`, so they start, steer
        and resume runs; ``stop_run`` stops a run of this workspace that runs in this process;
        everything else, notices included, is committed as-is. A rejection is the result, not
        raised.

        A command is known by its tenant, workspace, sender (the handle's actor, as a
        participant) and ``command_id``. The first time, it is carried out and its result is
        remembered. A repeated id returns the remembered result and carries nothing out,
        whatever command it comes with, so a retry is safe on every surface.
        """
        key = CommandKey(
            tenant_id=workspace.tenant_id,
            workspace_id=workspace.workspace_id,
            participant=workspace.actor.participant,
            command_id=command_id,
        )
        if (remembered := await self._results.get(key)) is not None:
            return remembered
        try:
            outcome = await self._carry_out(workspace, command)
        except Rejection as rejection:
            result = CommandResult(command_id=command_id, ok=False, rejection=rejection.payload())
        else:
            result = CommandResult(command_id=command_id, ok=True, outcome=outcome)
        await self._results.put(key, result)
        return result

    async def send(
        self,
        workspace: Workspace,
        thread_id: ThreadId,
        content: str,
        *,
        message_id: MessageId | None = None,
    ) -> Sent:
        """Post a message as the workspace handle's actor, and ask for the thread's next turn.

        Raises:
            InvalidState: If ``message_id`` is already used in the workspace; nothing is done.
        """
        message = PostMessage(
            thread_id=thread_id, content=content, message_id=message_id or new_message_id()
        )
        posted = await workspace.commit(message)
        return _sent(posted, await self._ask(workspace, thread_id, posted.seq))

    async def answer(self, workspace: Workspace, command: AnswerDeferred) -> Sent:
        """Answer one of a paused run's requests, resuming the run once all are answered."""
        answered = await workspace.commit(command)
        return _sent(answered, await self.resume(workspace, command.run_id))

    async def resume(self, workspace: Workspace, run_id: RunId) -> RunHandle | None:
        """Resume a paused run whose requests are all answered; otherwise do nothing.

        Like a message, it asks for the thread's next turn, so the messages no turn has taken
        reach the run as it resumes.
        """
        run = await workspace.run(run_id)
        return await self._ask(workspace, run.thread_id, await workspace.head_seq())

    async def stop(self, run_id: RunId) -> bool:
        """Cancel a run of this process. Returns whether there was one to stop."""
        handle = self._runs.get(run_id)
        if handle is None:
            return False
        handle.task.cancel()
        await asyncio.gather(handle.task, return_exceptions=True)
        return True

    async def drain(self) -> None:
        """Wait until each run of this process that has released its thread has handed it over.

        A run that ends hands its thread over in the background (ADR-0055): it starts the
        thread's next turn if a message or an answer asked for one meanwhile, and otherwise
        does nothing. This waits for those in progress, not for the turns they start.
        """
        await asyncio.gather(*self._handovers)

    async def aclose(self) -> None:
        """Stop every run of this process, wait for them to end, and start no more."""
        self._closed = True
        tasks: list[asyncio.Task[Any]] = [handle.task for handle in self._runs.values()]
        tasks += self._handovers
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def watch(self, run_id: RunId) -> AsyncIterator[LiveFrame]:
        """Yield a run's live frames from now until it ends."""
        return self.live.watch(run_id)

    def running(self, thread_id: ThreadId) -> RunHandle | None:
        """Return this process's run in a thread, if there is one."""
        return next((h for h in self._runs.values() if h.thread_id == thread_id), None)

    async def _carry_out(self, workspace: Workspace, command: Command | StopRun) -> Outcome:
        match command:
            case PostMessage(kind="message"):
                sent = await self.send(
                    workspace, command.thread_id, command.content, message_id=command.message_id
                )
                return sent.outcome
            case AnswerDeferred():
                return (await self.answer(workspace, command)).outcome
            case StopRun():
                await workspace.run(command.run_id)  # the run must belong to this workspace
                if not await self.stop(command.run_id):
                    raise NotFound("running run", command.run_id)
                return Recorded()
            case _:
                return await workspace.commit(command)

    # ─── turns, from the log (ADR-0055) ───────────────────────────────────────

    async def _ask(
        self, workspace: Workspace, thread_id: ThreadId, seq: int | None
    ) -> RunHandle | None:
        """Ask for a turn for what is committed up to ``seq``, and take it if the thread is free.

        The ask is saved before the thread is claimed, so a run that holds the thread and
        refuses this claim sees it when it releases the thread, and hands the thread over.
        """
        await workspace.save_cursor(_asked(thread_id), seq or 0)
        return await self._take(workspace, thread_id, trace.get_current_span().get_span_context())

    async def _take(
        self, workspace: Workspace, thread_id: ThreadId, caller: SpanContext | None
    ) -> RunHandle | None:
        """Start the turn the thread was asked for and no run has taken, if it is free.

        A claimant that starts nothing looks again once it has released the thread, since a
        command it refused meanwhile relies on it. Each round starts a turn, finds nothing
        asked, finds the thread busy, or records what it found as taken, so it ends. The turn
        links to ``caller``, or else to where the message or answer it carries out was
        committed.
        """
        while not self._closed and await _asked_for(workspace, thread_id):
            try:
                handle = await self._start(workspace, thread_id, caller)
            except ThreadBusy:
                return None  # its holder hands the thread over as it releases it
            if handle is not None:
                return handle
        return None

    async def _start(
        self, workspace: Workspace, thread_id: ThreadId, caller: SpanContext | None
    ) -> RunHandle | None:
        """Claim the thread and start the turn the log calls for, if any.

        Raises:
            ThreadBusy: If another holder has the thread.
        """
        # Each claim has a holder of its own, so a run resuming cannot renew the claim its
        # pausing segment still holds.
        async with contextlib.AsyncExitStack() as stack:
            lost = await stack.enter_async_context(
                workspace.claim_thread(thread_id, holder=new_id("claim"), ttl=self._claim_ttl)
            )
            await _abandon(workspace, thread_id)
            if self._closed:
                return None
            turn = await self._plan(workspace, thread_id)
            if turn is None:
                return None
            await workspace.save_cursor(_taken(thread_id), turn.through)
            claim = stack.pop_all()  # the run's task holds the claim from here
        session = Session[AppDepsT].start(
            workspace,
            thread_id,
            app=self._app,
            run_id=turn.run_id,
            agent_name=self._agent_name,
            trigger=turn.trigger,
            watch_after=turn.watch_after,
            requested_by=turn.requested_by,
        )
        if caller is None:  # a hand-over: the turn links to what it carries out
            caller = parse_traceparent(turn.traceparent) or INVALID_SPAN_CONTEXT
        task = asyncio.create_task(
            self._run(claim, lost, session, turn.prompt, turn.deferred, caller)
        )
        handle = RunHandle(run_id=turn.run_id, thread_id=thread_id, task=task)
        self._runs[turn.run_id] = handle
        task.add_done_callback(lambda _: self._finished(handle))
        return handle

    async def _plan(self, workspace: Workspace, thread_id: ThreadId) -> "_Turn | None":
        """Decide, holding the thread, which turn carries out the oldest message not taken.

        With a paused run, that message is its reply: it answers the questions and declines the
        approvals left, and the run resumes. A paused run whose requests are all answered
        resumes, and its watcher delivers the messages. Otherwise the message starts a run.
        Either way the turn's watcher follows from there, so the later messages reach it too.
        """
        taken = await _taken_seq(workspace, thread_id)
        if await workspace.cursor(_asked(thread_id)) <= taken:
            return None  # what was asked for is taken
        paused = await workspace.runs(thread_id=thread_id, status="paused")
        log = await workspace.read(after_seq=taken, threads={thread_id})
        through = log[-1].seq if log else taken
        untaken = [envelope for envelope in log if _from_others(envelope, thread_id)]
        if paused:
            run = paused[-1]
            if run.all_answered:
                # Resumed by its last answer, unless a resume that failed before it began took
                # the answers: then by whoever asks now.
                answered = [e for e in log if isinstance(e.event, DeferredAnswered)]
                if not answered:
                    return _resume(run, taken, through, workspace.actor, None)
                last = answered[-1]
                return _resume(run, taken, through, last.actor, last.traceparent)
            if untaken:
                reply = untaken[0]
                await _reply(workspace.as_actor(reply.actor), run, reply)
                run = await workspace.run(run.id)
                return _resume(run, reply.seq, reply.seq, reply.actor, reply.traceparent)
        elif untaken:
            first = untaken[0]
            assert isinstance(first.event, MessagePosted)
            return _Turn(
                run_id=new_run_id(),
                trigger="message",
                prompt=first.event.content,
                deferred=None,
                watch_after=first.seq,
                through=first.seq,
                requested_by=first.actor,
                traceparent=first.traceparent,
            )
        await workspace.save_cursor(_taken(thread_id), through)  # no message in it to carry out
        return None

    async def _run(
        self,
        claim: contextlib.AsyncExitStack,
        lost: asyncio.Event,
        session: Session[AppDepsT],
        prompt: str | None,
        deferred: DeferredToolResults | None,
        caller: SpanContext,
    ) -> AgentRunResult[Any]:
        run = asyncio.current_task()
        assert run is not None, "a run is a task"
        try:
            async with claim:
                stopping = asyncio.create_task(_cancel_when_lost(lost, run))
                try:
                    return await self._turn(session, prompt, deferred, caller)
                finally:
                    self.live.close(session.run_id)
                    stopping.cancel()
                    await asyncio.gather(stopping, return_exceptions=True)
                    await _record_taken(session)
        finally:
            self._hand_over(session)

    def _hand_over(self, session: Session[AppDepsT]) -> None:
        """Once a run has released its thread, take the turn it was asked for meanwhile.

        It runs in the background, in a context of its own, so the run's end does not wait for
        it and the turn it starts links to what it carries out.
        """
        if self._closed:
            return  # the thread's next claimant, in any process, carries it out
        handover = asyncio.create_task(
            self._take_over(session.workspace, session.thread_id), context=contextvars.Context()
        )
        self._handovers.add(handover)
        handover.add_done_callback(self._handovers.discard)

    async def _take_over(self, workspace: Workspace, thread_id: ThreadId) -> None:
        try:
            await self._take(workspace, thread_id, None)
        except Exception:
            logger.exception(
                "handing thread %s over failed; its next turn carries out what was sent",
                thread_id,
            )

    async def _turn(
        self,
        session: Session[AppDepsT],
        prompt: str | None,
        deferred: DeferredToolResults | None,
        caller: SpanContext,
    ) -> AgentRunResult[Any]:
        """Run the agent once, as a turn: its own trace, linked to what started it."""
        workspace = session.workspace
        tenancy = {TENANT_ID: workspace.tenant_id, WORKSPACE_ID: workspace.workspace_id}
        attributes = {
            GEN_AI_OPERATION_NAME: "invoke_workflow",
            GEN_AI_WORKFLOW_NAME: "turn",
            LANGFUSE_OBSERVATION_TYPE: "chain",
            TURN_TRIGGER: session.trigger,
            **attribution(
                tenant_id=workspace.tenant_id,
                workspace_id=workspace.workspace_id,
                thread_id=session.thread_id,
                run_id=session.run_id,
                actor=session.requested_by,
            ),
        }
        started = time.perf_counter()
        outcome: TurnOutcome = "failed"
        with self._telemetry.tracer.start_as_current_span(
            "invoke_workflow turn",
            context=otel_context.Context(),
            links=[Link(caller)] if caller.is_valid else None,
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            token = otel_context.attach(baggage.set_baggage(SESSION_ID, session.thread_id))
            try:
                async with contextlib.AsyncExitStack() as scope:
                    if self._turn_context is not None:
                        await scope.enter_async_context(self._turn_context(session))
                    result = await self._agent.run(
                        prompt,
                        deps=session,
                        message_history=await load_history(workspace, session.thread_id),
                        deferred_tool_results=deferred,
                        event_stream_handler=forward_live(self.live),
                        conversation_id=session.thread_id,
                    )
            except asyncio.CancelledError:
                outcome = "stopped"
                raise
            except Exception as error:
                span.record_exception(error)
                span.set_status(StatusCode.ERROR, str(error))
                span.set_attribute(ERROR_TYPE, type(error).__qualname__)
                raise
            else:
                paused = isinstance(result.output, DeferredToolRequests)
                outcome = "paused" if paused else "completed"
                return result
            finally:
                otel_context.detach(token)
                span.set_attribute(TURN_OUTCOME, outcome)
                counted = {**tenancy, TURN_TRIGGER: session.trigger, TURN_OUTCOME: outcome}
                self._telemetry.add(TURNS, 1, counted)
                self._telemetry.record(TURN_DURATION, time.perf_counter() - started, counted)
                self._submit(EndedTurn(session, outcome, span.get_span_context()), span)

    def _submit(self, turn: EndedTurn, span: Span) -> None:
        """Hand an ended turn to each evaluator; a failing one is recorded, never raised."""
        for evaluator in self._evaluators:
            try:
                evaluator.submit(turn)
            except Exception as error:
                span.record_exception(error)

    def _finished(self, handle: RunHandle) -> None:
        if self._runs.get(handle.run_id) is handle:  # not if the run resumed in a new task
            del self._runs[handle.run_id]
        if not handle.task.cancelled():
            handle.task.exception()  # the capability recorded any failure; mark it retrieved


async def _abandon(workspace: Workspace, thread_id: ThreadId) -> None:
    """Record each run still ``running`` in a thread just claimed as failed, ``abandoned``.

    A run the Runner starts holds its thread's claim until it records its end, so a run still
    ``running`` when the thread is claimed again was left by a process that stopped.
    """
    system = workspace.as_actor(SystemActor(name="runner"))
    for run in await workspace.runs(thread_id=thread_id, status="running"):
        abandoned = RunEnded(
            run_id=run.id,
            thread_id=thread_id,
            status="failed",
            error=_ABANDONED,
            reason="abandoned",
        )
        with contextlib.suppress(InvalidState):  # it ended meanwhile
            await system.record(abandoned)


async def _cancel_when_lost(lost: asyncio.Event, run: "asyncio.Task[Any]") -> None:
    """Cancel a run once its thread claim is lost, before the claim's next holder abandons it."""
    await lost.wait()
    run.cancel()


def _sent(recorded: Recorded, run: RunHandle | None) -> Sent:
    """What a message or an answer did, with the run it started or resumed in its outcome."""
    run_id = None if run is None else run.run_id
    return Sent(recorded.model_copy(update={"run_id": run_id}), run)


@dataclass(frozen=True)
class _Turn:
    """A turn the log calls for: what to run, and how far it carries the thread's log out."""

    run_id: RunId
    trigger: Trigger
    prompt: str | None
    deferred: DeferredToolResults | None
    watch_after: int
    """Its watcher delivers the thread's log after this ``seq``."""
    through: int
    """The ``seq`` up to which it takes the thread's messages as it starts: its prompt or its
    reply, or, resuming by its answers, what was read. The rest are taken as its watcher
    delivers them, so a message it misses is left for the next turn."""
    requested_by: Actor
    traceparent: str | None
    """Where the message or answer it carries out was committed."""


def _resume(run: Run, watch_after: int, through: int, by: Actor, traceparent: str | None) -> _Turn:
    """The turn that resumes a paused run whose requests are all answered."""
    deferred = DeferredToolResults(
        calls={
            r.tool_call_id: run.answers[r.tool_call_id].answer
            for r in run.pending
            if r.kind == "question"
        },
        approvals={
            r.tool_call_id: _approval(run, r.tool_call_id)
            for r in run.pending
            if r.kind == "approval"
        },
    )
    return _Turn(
        run_id=run.id,
        trigger="resume",
        prompt=None,
        deferred=deferred,
        watch_after=watch_after,
        through=through,
        requested_by=by,
        traceparent=traceparent,
    )


async def _reply(workspace: Workspace, run: Run, message: Envelope) -> None:
    """Answer a paused run's open questions with a message, and decline its open approvals."""
    assert isinstance(message.event, MessagePosted)
    content = message.event.content
    for request in run.pending:
        if request.tool_call_id in run.answers:
            continue
        declined = request.kind == "approval"
        await workspace.commit(
            AnswerDeferred(
                run_id=run.id,
                tool_call_id=request.tool_call_id,
                answer=content,
                approved=False if declined else None,
            )
        )


def _from_others(envelope: Envelope, thread_id: ThreadId) -> bool:
    """Whether an envelope is a message for the thread's agent: one it did not post itself."""
    event = envelope.event
    return (
        isinstance(event, MessagePosted)
        and event.kind == "message"
        and envelope.actor.participant != AgentActor(thread_id=thread_id).participant
    )


def _taken(thread_id: ThreadId) -> str:
    """The cursor up to which runs have taken a thread's messages: each is carried out."""
    return f"artifactr.runner/{thread_id}/taken"


def _asked(thread_id: ThreadId) -> str:
    """The cursor up to which messages and answers asked runners for a turn in a thread."""
    return f"artifactr.runner/{thread_id}/asked"


_UPGRADED = "artifactr.runner/upgraded"
"""The cursor at which a workspace's log stood when it was upgraded to ADR-0055's turns.

SQL migration 0005 records it, for each workspace that existed then.
"""


async def _taken_seq(workspace: Workspace, thread_id: ThreadId) -> int:
    """How far runs have taken a thread's messages.

    A thread no run has recorded it for starts from the upgrade to ADR-0055, or from what its
    agent was last told, as by a run without the runner, whichever is later. So nothing from
    before the upgrade resurfaces, and a brand-new thread starts from its beginning.
    """
    taken = await workspace.cursor(_taken(thread_id))
    if taken:
        return taken
    return max(await workspace.cursor(_UPGRADED), await last_seen(workspace, thread_id))


async def _asked_for(workspace: Workspace, thread_id: ThreadId) -> bool:
    """Whether a message or an answer asked for a turn in a thread that no run has taken."""
    return await workspace.cursor(_asked(thread_id)) > await _taken_seq(workspace, thread_id)


async def _record_taken(session: Session[Any]) -> None:
    """Record what a run's watcher delivered as taken; a failure is logged, never raised.

    If it fails, the thread's next turn is given what the watcher delivered again.
    """
    try:
        await session.workspace.save_cursor(_taken(session.thread_id), session.delivered.seq)
    except Exception:
        logger.exception("recording what run %s took failed", session.run_id)


def _approval(run: Run, tool_call_id: str) -> bool | ToolDenied:
    answer = run.answers[tool_call_id]
    if answer.approved:
        return True
    return ToolDenied(message=str(answer.answer)) if answer.answer else False
