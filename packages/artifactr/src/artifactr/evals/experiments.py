"""Experiment tasks: replay a thread's turn against a candidate agent, in isolation.

An experiment asks how a new agent, prompt or model would have handled a turn. A
:func:`replay_task` is an evalr ``Task`` that, for each example, seeds a fresh in-memory
workspace with the thread as it was (its messages and the artifacts it followed), sends the
message that started the turn, lets the candidate run, and hands what the turn did to the
experiment's evaluators. Nothing touches the real workspaces.
"""

from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from inspect import isawaitable
from itertools import groupby
from typing import Any

from pydantic import BaseModel
from pydantic_ai import (
    Agent,
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from artifactr.agent import Runner, Session
from artifactr.core import (
    AgentActor,
    AppEvent,
    Artifact,
    ArtifactArchived,
    ArtifactChanged,
    ArtifactCreated,
    ArtifactId,
    Envelope,
    MessagePosted,
    Revision,
    Run,
    SetFocus,
    SetThreadMode,
    SystemActor,
    ThreadMode,
    UserActor,
)
from artifactr.workspace import InMemoryStorage, Workspace, Workspaces
from evalr.core import Example, Task
from evalr.measures import Turn

REPLAYER = UserActor(id="replay", name="replay")
"""The person who sends a replayed turn's message, unless another is given."""


@dataclass(frozen=True)
class Seed:
    """What a replayed turn starts from: the thread as it was, and the message that starts it.

    Attributes:
        prompt: The person's message that starts the turn.
        messages: The thread's earlier messages, oldest first. The agent sees them as its
            conversation so far, and they are posted in the replay's log.
        artifacts: The artifacts the thread followed, by id, as they were.
        title: The thread's title.
        mode: The thread's mode: whether the agent edits, or proposes.
    """

    prompt: str
    messages: Sequence[Turn] = ()
    artifacts: Mapping[ArtifactId, Artifact] = field(default_factory=dict[ArtifactId, Artifact])
    title: str = ""
    mode: ThreadMode = "edit"


@dataclass(frozen=True)
class Replay:
    """What a replayed turn did.

    Attributes:
        workspace: The isolated workspace, as the person who sent the message.
        run: The turn's run.
        events: The turn's envelopes, in order: its tool calls, changes, proposals and messages.
        revisions: The artifact versions the turn wrote, in order.
        message: The agent's last message in the turn, if it posted one.
    """

    workspace: Workspace
    run: Run
    events: tuple[Envelope, ...]
    revisions: tuple[Revision, ...]
    message: str | None


def replay_task[AppDepsT, InputT: BaseModel, VerdictT: BaseModel, OutputT: BaseModel](
    agent: Agent[Session[AppDepsT], Any],
    *,
    app: AppDepsT,
    seed: Callable[[Example[InputT, VerdictT]], Seed],
    output: Callable[[Replay], OutputT | Awaitable[OutputT]],
    types: Iterable[type[Artifact]] | None = None,
    agent_name: str = "assistant",
    person: UserActor = REPLAYER,
) -> Task[InputT, VerdictT, OutputT]:
    """Build an evalr task that replays each example's turn against a candidate agent.

    Args:
        agent: The candidate: a new agent, or the same one with a new prompt or model. It has
            the :class:`~artifactr.agent.ArtifactWorkspace` capability, as in production.
        app: The candidate's application dependencies, such as fakes of the services it calls.
        seed: The thread as it was when the turn started, from an example.
        output: What the experiment's evaluators judge, from the replay; sync or async.
        types: The artifact types the isolated workspace accepts; every registered type by
            default.
        agent_name: How the agent is named in the workspace.
        person: Who sends the turn's message and the seeded messages of people.
    """

    async def task(example: Example[InputT, VerdictT]) -> OutputT:
        workspaces = Workspaces(InMemoryStorage(), types=types)
        workspace = await workspaces.open(f"replay:{example.id}", "replay", actor=person)
        runner = Runner(agent, app=app, agent_name=agent_name)
        built = output(await _replay(runner, workspace, seed(example), agent_name=agent_name))
        return await built if isawaitable(built) else built

    return task


async def _replay(
    runner: Runner[Any], workspace: Workspace, seed: Seed, *, agent_name: str
) -> Replay:
    """Seed a new thread in a workspace, and run one turn in it, to its end or first pause.

    The thread's artifacts and focus come first, then its messages, posted and stored as the
    agent's history in one step, so the agent is not told of the seeding as changes.
    """
    thread = await workspace.create_thread(seed.title)
    await workspace.commit(SetThreadMode(thread_id=thread.id, mode=seed.mode))
    for artifact_id, artifact in seed.artifacts.items():
        await workspace.create(artifact, artifact_id=artifact_id, thread_id=thread.id)
    await workspace.commit(SetFocus(thread_id=thread.id, artifact_ids=tuple(seed.artifacts)))
    speakers = {
        "person": workspace,
        "agent": workspace.as_actor(AgentActor(thread_id=thread.id, name=agent_name)),
        "system": workspace.as_actor(SystemActor()),
    }
    for turn in seed.messages:
        await speakers[turn.role].post_message(thread.id, turn.text)
    history = ModelMessagesTypeAdapter.dump_json(_history(seed.messages))
    await workspace.record(AppEvent(name="replay_seeded", thread_id=thread.id), history=history)
    sent = await runner.send(workspace, thread.id, seed.prompt)
    assert sent.run is not None, "a new thread is never busy"
    await sent.run.wait()
    run = await workspace.run(sent.run.run_id)
    events = tuple(e for e in await workspace.read() if e.run_id == run.id)
    written = dict.fromkeys(
        e.event.artifact_id
        for e in events
        if isinstance(e.event, ArtifactCreated | ArtifactChanged | ArtifactArchived)
    )
    revisions = [
        revision
        for artifact_id in written
        for revision in await workspace.revisions(artifact_id)
        if isinstance(revision.actor, AgentActor) and revision.actor.run_id == run.id
    ]
    messages = [e.event.content for e in events if isinstance(e.event, MessagePosted)]
    return Replay(
        workspace=workspace,
        run=run,
        events=events,
        revisions=tuple(revisions),
        message=messages[-1] if messages else None,
    )


def _history(turns: Sequence[Turn]) -> list[ModelMessage]:
    """Messages as a model history, grouping consecutive messages from one side.

    People's messages, and the system's, are requests; the agent's are responses.
    """
    history: list[ModelMessage] = []
    for agent, group in groupby(turns, key=lambda turn: turn.role == "agent"):
        texts = [turn.text for turn in group]
        history.append(
            ModelResponse(parts=[TextPart(text) for text in texts])
            if agent
            else ModelRequest(parts=[UserPromptPart(text) for text in texts])
        )
    return history
