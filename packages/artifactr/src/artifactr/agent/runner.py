"""The Runner: starts, steers, pauses, resumes and stops agent runs in threads.

Surfaces (WebSocket, REST, MCP) share one Runner, so a message behaves the same wherever it
comes from:

- In an idle thread, a message starts a run.
- In a busy thread, it steers the running agent: the run's watcher delivers it.
- In a thread whose run is paused on questions, it is the reply: questions are answered with
  it, approvals are declined with it as the reason, and the run resumes.

Runs are asyncio tasks in this process. Their live frames go to :attr:`Runner.live`, where any
connection can :meth:`Runner.watch` them.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from pydantic_ai import Agent, AgentRunResult, DeferredToolResults, ToolDenied

from artifactr.agent.live import FanoutChannel, forward_live
from artifactr.agent.session import Session, Trigger, load_history
from artifactr.core import (
    AnswerDeferred,
    Command,
    LiveFrame,
    MessageId,
    NotFound,
    Outcome,
    PostMessage,
    Recorded,
    Run,
    RunId,
    StopRun,
    ThreadId,
    new_message_id,
    new_run_id,
)
from artifactr.workspace import ThreadBusy, Workspace


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
    """The recorded message or answer."""

    run: RunHandle | None
    """The run it started or resumed; None if it steered a running run or awaits more answers."""


class Runner[AppDepsT]:
    """Runs an agent in workspace threads.

    Args:
        agent: The agent, whose ``deps_type`` is ``Session[AppDepsT]`` and which has the
            :class:`~artifactr.agent.ArtifactWorkspace` capability.
        app: The application's dependencies, passed to every run as ``ctx.deps.app``.
        live: Where runs' live frames go. Defaults to an in-process fan-out.
        agent_name: How the agent is named in the workspace.
        claim_ttl: How long a thread claim lasts without renewal, should this process die.
    """

    def __init__(
        self,
        agent: Agent[Session[AppDepsT], Any],
        *,
        app: AppDepsT,
        live: FanoutChannel | None = None,
        agent_name: str = "assistant",
        claim_ttl: timedelta = timedelta(seconds=30),
    ) -> None:
        self._agent = agent
        self._app = app
        self.live = live or FanoutChannel()
        self._agent_name = agent_name
        self._claim_ttl = claim_ttl
        self._runs: dict[RunId, RunHandle] = {}

    async def execute(self, workspace: Workspace, command: Command | StopRun) -> Outcome:
        """Carry out any command the way every surface should.

        Messages and answers go through :meth:`send` and :meth:`answer`, so they start, steer
        and resume runs; ``stop_run`` stops a run of this workspace; everything else is
        committed as-is.

        Raises:
            Rejection: If the command is rejected, or the run to stop is not in this workspace
                or not running in this process.
        """
        match command:
            case PostMessage():
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

    async def send(
        self,
        workspace: Workspace,
        thread_id: ThreadId,
        content: str,
        *,
        message_id: MessageId | None = None,
    ) -> Sent:
        """Post a message as the workspace handle's actor, and act on it."""
        message = PostMessage(
            thread_id=thread_id, content=content, message_id=message_id or new_message_id()
        )
        posted = await workspace.commit(message)
        paused = await workspace.runs(thread_id=thread_id, status="paused")
        if paused:
            return Sent(posted, await self._reply(workspace, paused[-1], content))
        run = await self._start(
            workspace,
            thread_id,
            new_run_id(),
            prompt=content,
            trigger="message",
            watch_after=posted.seq,
        )
        return Sent(posted, run)

    async def answer(self, workspace: Workspace, command: AnswerDeferred) -> Sent:
        """Answer one of a paused run's requests, resuming the run once all are answered."""
        answered = await workspace.commit(command)
        return Sent(answered, await self.resume(workspace, command.run_id))

    async def resume(self, workspace: Workspace, run_id: RunId) -> RunHandle | None:
        """Resume a paused run whose requests are all answered; otherwise do nothing."""
        run = await workspace.run(run_id)
        if not run.all_answered:
            return None
        results = DeferredToolResults(
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
        return await self._start(
            workspace,
            run.thread_id,
            run.id,
            prompt=None,
            trigger="resume",
            watch_after=await workspace.head_seq(),
            deferred=results,
        )

    async def stop(self, run_id: RunId) -> bool:
        """Cancel a run of this process. Returns whether there was one to stop."""
        handle = self._runs.get(run_id)
        if handle is None:
            return False
        handle.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await handle.task
        return True

    def watch(self, run_id: RunId) -> AsyncIterator[LiveFrame]:
        """Yield a run's live frames from now until it ends."""
        return self.live.watch(run_id)

    def running(self, thread_id: ThreadId) -> RunHandle | None:
        """Return this process's run in a thread, if there is one."""
        return next((h for h in self._runs.values() if h.thread_id == thread_id), None)

    async def _reply(self, workspace: Workspace, run: Run, content: str) -> RunHandle | None:
        for request in run.pending:
            if request.tool_call_id in run.answers:
                continue
            if request.kind == "question":
                command = AnswerDeferred(
                    run_id=run.id, tool_call_id=request.tool_call_id, answer=content
                )
            else:
                command = AnswerDeferred(
                    run_id=run.id, tool_call_id=request.tool_call_id, answer=content, approved=False
                )
            await workspace.commit(command)
        return await self.resume(workspace, run.id)

    async def _start(
        self,
        workspace: Workspace,
        thread_id: ThreadId,
        run_id: RunId,
        *,
        prompt: str | None,
        trigger: Trigger,
        watch_after: int | None,
        deferred: DeferredToolResults | None = None,
    ) -> RunHandle | None:
        claim = contextlib.AsyncExitStack()
        try:
            await claim.enter_async_context(
                workspace.claim_thread(thread_id, holder=run_id, ttl=self._claim_ttl)
            )
        except ThreadBusy:
            return None
        session = Session[AppDepsT].start(
            workspace,
            thread_id,
            app=self._app,
            run_id=run_id,
            agent_name=self._agent_name,
            trigger=trigger,
            watch_after=watch_after,
        )
        task = asyncio.create_task(self._run(claim, session, prompt, deferred))
        handle = RunHandle(run_id=run_id, thread_id=thread_id, task=task)
        self._runs[run_id] = handle
        task.add_done_callback(lambda done: self._finished(run_id, done))
        return handle

    async def _run(
        self,
        claim: contextlib.AsyncExitStack,
        session: Session[AppDepsT],
        prompt: str | None,
        deferred: DeferredToolResults | None,
    ) -> AgentRunResult[Any]:
        async with claim:
            try:
                return await self._agent.run(
                    prompt,
                    deps=session,
                    message_history=await load_history(session.workspace, session.thread_id),
                    deferred_tool_results=deferred,
                    event_stream_handler=forward_live(self.live),
                )
            finally:
                self.live.close(session.run_id)

    def _finished(self, run_id: RunId, task: "asyncio.Task[AgentRunResult[Any]]") -> None:
        self._runs.pop(run_id, None)
        if not task.cancelled():
            task.exception()  # the capability recorded any failure; mark it retrieved


def _approval(run: Run, tool_call_id: str) -> bool | ToolDenied:
    answer = run.answers[tool_call_id]
    if answer.approved:
        return True
    return ToolDenied(message=str(answer.answer)) if answer.answer else False
