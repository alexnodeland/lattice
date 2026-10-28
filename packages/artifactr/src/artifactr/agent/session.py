"""The agent's dependencies for one run, and its thread history."""

from dataclasses import dataclass, field
from typing import Literal

from pydantic_ai import ModelMessage, ModelMessagesTypeAdapter

from artifactr.core import (
    AgentActor,
    ArtifactId,
    ExternalAgentActor,
    MessageId,
    RunId,
    StepUsage,
    ThreadId,
    UserActor,
    acting_for,
    new_run_id,
)
from artifactr.workspace import Workspace

Trigger = Literal["message", "resume", "api"]
"""What started a run: a posted message, answers to a pause, or a direct call."""


@dataclass
class Delivered:
    """How far a run has taken the log: a handoff between the capability and the Runner.

    The Runner names a cursor for it. The capability then saves it with the run's start, as its
    input, and with the run's end, as far as its watcher delivered: in the same transaction as
    each record, so a message is taken exactly when the write that consumes it is made. The
    Runner names its claim too, which fences the run's start (ADR-0069).
    """

    seq: int = 0
    """Every envelope up to this ``seq`` was delivered, or was not for the agent."""

    cursor: str | None = None
    """The cursor that records ``seq``, when the Runner keeps one."""

    claim: tuple[ThreadId, str] | None = None
    """The thread's claim the run holds, ``(thread_id, holder)``, when the Runner holds one: the
    run's start is recorded only while its holder has the thread."""

    def at(self, seq: int) -> tuple[str, int] | None:
        """The cursor to save as taken through ``seq``, with a record, if there is one."""
        return None if self.cursor is None else (self.cursor, seq)


@dataclass(frozen=True)
class Session[AppDepsT]:
    """The pydantic-ai ``deps`` of one agent run.

    Tools receive it as ``ctx.deps``. Its workspace handle acts as the thread's agent, for
    whoever started the run segment, so everything a tool commits is attributed to the agent
    and this run, and checked as done for them.

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

    message_ids: tuple[MessageId, ...] = ()
    """The messages the run segment's start carries out, which its ``run_started`` names."""

    model: str | None = None
    """The model the run segment asked for, by the host's name for it, which its
    ``run_started`` names; ``None`` for the agent's own (ADR-0097)."""

    delivered: Delivered = field(default_factory=Delivered, init=False, repr=False, compare=False)
    """How far the run has taken the log: to ``watch_after`` once it has started, then as far as
    its watcher delivers. The capability records it with the run's start and its end."""

    steps: list[StepUsage] = field(
        default_factory=list[StepUsage], init=False, repr=False, compare=False
    )
    """What each of the run segment's model requests used, oldest first, as the capability
    counts them: recorded with the segment's end, however it ends (ADR-0096)."""

    made: set[ArtifactId] = field(
        default_factory=set[ArtifactId], init=False, repr=False, compare=False
    )
    """The artifacts the run segment's tools made as the person it acts for, which its watcher
    doesn't tell it of as the person's: a tool adds an id before it commits."""

    @property
    def on_behalf_of(self) -> UserActor | ExternalAgentActor | None:
        """Whom the run segment acts for: its agent's ``on_behalf_of``.

        Spans record a person here as the user.
        """
        return acting_for(self.workspace.actor)

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
        on_behalf_of: UserActor | ExternalAgentActor | None = None,
        message_ids: tuple[MessageId, ...] = (),
        model: str | None = None,
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
            on_behalf_of: Whom the run segment acts for: the person, or the person's client,
                whose message or answer started it.
            message_ids: The messages its start carries out.
            model: The model it asks for, by the host's name for it; ``None`` for the agent's.
        """
        run_id = run_id or new_run_id()
        actor = AgentActor(
            thread_id=thread_id, run_id=run_id, name=agent_name, on_behalf_of=on_behalf_of
        )
        return cls(
            workspace=workspace.as_actor(actor),
            thread_id=thread_id,
            run_id=run_id,
            app=app,
            trigger=trigger,
            watch_after=watch_after,
            message_ids=message_ids,
            model=model,
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
