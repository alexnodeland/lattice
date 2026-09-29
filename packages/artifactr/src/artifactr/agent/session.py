"""The agent's dependencies for one run, and its thread history."""

from dataclasses import dataclass
from typing import Literal

from pydantic_ai import ModelMessage, ModelMessagesTypeAdapter

from artifactr.core import Actor, AgentActor, RunId, ThreadId, new_run_id
from artifactr.workspace import Workspace

Trigger = Literal["message", "resume", "api"]
"""What started a run: a posted message, answers to a pause, or a direct call."""


@dataclass(frozen=True)
class Session[AppDepsT]:
    """The pydantic-ai ``deps`` of one agent run.

    Tools receive it as ``ctx.deps``. Its workspace handle acts as the thread's agent, so
    everything a tool commits is attributed to the agent and this run.

    Create it with :meth:`start` rather than directly.
    """

    workspace: Workspace
    thread_id: ThreadId
    run_id: RunId
    app: AppDepsT
    """The application's own dependencies."""

    trigger: Trigger = "api"
    watch_after: int | None = None
    """Watch the log for others' changes after this ``seq``; None means from the run's start."""

    requested_by: Actor | None = None
    """Whose message or answer started this run segment, if anyone's. Spans record a person
    here as the user."""

    @classmethod
    def start(
        cls,
        workspace: Workspace,
        thread_id: ThreadId,
        *,
        app: AppDepsT,
        run_id: RunId | None = None,
        agent_name: str = "assistant",
        trigger: Trigger = "api",
        watch_after: int | None = None,
        requested_by: Actor | None = None,
    ) -> "Session[AppDepsT]":
        """Return a session for a new (or resuming) run of the thread's agent.

        Args:
            workspace: A handle on the workspace; the session derives the agent's handle.
            thread_id: The thread the agent runs in.
            app: The application's own dependencies, available to tools as ``ctx.deps.app``.
            run_id: The run's id; a new one is generated when omitted.
            agent_name: How the agent is named in change notes and messages.
            trigger: What started the run.
            watch_after: The ``seq`` after which others' changes are delivered into the run.
            requested_by: Whose message or answer started the run segment.
        """
        run_id = run_id or new_run_id()
        actor = AgentActor(thread_id=thread_id, run_id=run_id, name=agent_name)
        return cls(
            workspace=workspace.as_actor(actor),
            thread_id=thread_id,
            run_id=run_id,
            app=app,
            trigger=trigger,
            watch_after=watch_after,
            requested_by=requested_by,
        )


async def load_history(workspace: Workspace, thread_id: ThreadId) -> list[ModelMessage]:
    """Return a thread's model history, to pass as ``message_history``."""
    return [
        message
        for chunk in await workspace.history(thread_id)
        for message in ModelMessagesTypeAdapter.validate_json(chunk.messages)
    ]


async def last_seen(workspace: Workspace, thread_id: ThreadId) -> int:
    """Return the ``seq`` up to which the thread's agent has been told what happened."""
    chunks = await workspace.history(thread_id)
    return chunks[-1].seq if chunks else 0
