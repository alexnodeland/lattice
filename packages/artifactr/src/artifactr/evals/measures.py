"""End-to-end measures of chats with artifacts, over evalr's measures (RFC-0002).

- **Rewrite rate** and **drop-off** are computed exactly from the log. :func:`artifact_histories`
  and :func:`thread_sessions` put a workspace's log into evalr's inputs, for evalr's
  ``measure_rewrites`` and ``measure_drop_off`` (or their evaluators).
- **Task completion** needs judgement. :class:`TaskCompletion` is its feedback type, for people
  and evaluators alike, and :func:`completion_transcript` builds a judge's input (a DSPy judge,
  or a Jev decision model) from a thread's transcript and final artifacts.
"""

from collections.abc import Callable
from datetime import datetime

from evalr import measures
from evalr.measures import Activity, History, Role, Session, Transcript, Turn

from artifactr.core import (
    Actor,
    Artifact,
    ArtifactArchived,
    ArtifactChanged,
    ArtifactCreated,
    ArtifactId,
    CreateArtifact,
    EditArtifact,
    Event,
    Feedback,
    MessagePosted,
    ProposalCreated,
    ProposalId,
    ProposalResolved,
    Revision,
    ThreadId,
    UserActor,
    Versioned,
    apply_patch,
    is_agent,
    load_artifact,
)
from artifactr.evals.context import TargetContext
from artifactr.workspace import Workspace


# evalr's TaskCompletion as a feedback type: people give it, evaluators' verdicts are recorded as
# it, and evalr's completion_rate reads either. Its docstring is a judge's instructions.
class TaskCompletion(Feedback, measures.TaskCompletion, name="task_completion", targets={"thread"}):
    """Whether the thread achieved what the person asked for, and how well."""


def actor_role(actor: Actor) -> Role:
    """Return who an actor is to the measures: a person, an agent, or the system.

    Agents are built-in or external; the system is the application, or an evaluator.
    """
    if isinstance(actor, UserActor):
        return "person"
    return "agent" if is_agent(actor) else "system"


async def thread_sessions(workspace: Workspace) -> list[Session]:
    """Put each thread's activity into an evalr ``Session``, for drop-off.

    A thread's activity is every envelope in it: its messages, the runs of its agent, the
    changes and proposals made in it, their resolutions, and feedback. Proposals and their
    resolutions are paired by the proposal's id.

    Returns:
        One session per thread, identified by the thread's id, in the order threads began.
    """
    threads: dict[ThreadId, list[Activity]] = {}
    for envelope in await workspace.read():
        if envelope.thread_id is None:
            continue
        kind, ref = _activity(envelope.event)
        threads.setdefault(envelope.thread_id, []).append(
            Activity(at=envelope.ts, role=actor_role(envelope.actor), kind=kind, ref=ref)
        )
    return [Session(id=thread_id, activities=done) for thread_id, done in threads.items()]


def _activity(event: Event) -> tuple[str, str | None]:
    match event:
        case MessagePosted():
            return "message", None
        case ProposalCreated():
            return "proposal", event.proposal_id
        case ProposalResolved():
            return "resolution", event.proposal_id
        case _:
            return event.type, None


async def artifact_histories(
    workspace: Workspace, *, text: Callable[[Artifact], str] | None = None
) -> list[History]:
    """Put each artifact's versions into an evalr ``History``, for the rewrite rate.

    A version is written by whoever wrote its content. A proposal's content is its proposer's,
    so an agent's accepted proposal is the agent's version; a proposal accepted with the
    reviewer's own changes is two versions at once, the agent's proposal and the person's
    rewrite of it. Archiving changes no text, so it is not a version here.

    Args:
        workspace: The workspace.
        text: An artifact's text, for measuring how much a version changed; what the agent
            sees (``render_for_agent``) by default.

    Returns:
        One history per artifact, identified by the artifact's id, in the order they were
        created.
    """
    render = text or _rendered
    written: dict[tuple[ArtifactId, int], datetime] = {}
    proposals: dict[ProposalId, ProposalCreated] = {}
    accepted: dict[ProposalId, ProposalResolved] = {}
    for envelope in await workspace.read():
        match envelope.event:
            case ArtifactCreated() | ArtifactChanged() | ArtifactArchived() as event:
                written[event.artifact_id, event.version] = envelope.ts
            case ProposalCreated() as event:
                proposals[event.proposal_id] = event
            case ProposalResolved(decision="accept") as event:
                accepted[event.proposal_id] = event
            case _:
                pass
    histories: list[History] = []
    for artifact_id in dict.fromkeys(artifact_id for artifact_id, _ in written):
        versions: list[measures.Revision] = []
        previous: Revision | None = None
        for revision in await workspace.revisions(artifact_id):
            at = written[artifact_id, revision.version]
            if not revision.archived:
                resolved = accepted.get(revision.proposal_id or "")
                proposal = proposals.get(revision.proposal_id or "")
                versions += _versions(revision, previous, at, render, proposal, resolved)
            previous = revision
        histories.append(History(id=artifact_id, revisions=versions))
    return histories


def _versions(
    revision: Revision,
    previous: Revision | None,
    at: datetime,
    render: Callable[[Artifact], str],
    proposal: ProposalCreated | None,
    resolved: ProposalResolved | None,
) -> list[measures.Revision]:
    """One version as the measures see it: one revision, or two for a rewritten proposal."""
    final = render(load_artifact(revision.kind, revision.data))
    if proposal is None or resolved is None:
        return [measures.Revision(at=at, role=actor_role(revision.actor), text=final)]
    author = actor_role(resolved.proposed_by)
    if resolved.changes is None:
        return [measures.Revision(at=at, role=author, text=final)]
    change = proposal.change
    if isinstance(change, CreateArtifact):
        proposed = change.data
    else:
        assert isinstance(change, EditArtifact), "an archive changes no text"
        assert previous is not None, "an edit has a version to edit"
        proposed = apply_patch(previous.data, change.patch)
    return [
        measures.Revision(at=at, role=author, text=render(load_artifact(revision.kind, proposed))),
        measures.Revision(at=at, role=actor_role(revision.actor), text=final),
    ]


def _rendered(artifact: Artifact) -> str:
    return artifact.render_for_agent()


def completion_transcript(context: TargetContext) -> Transcript:
    """Build a task-completion judge's input: the thread's transcript and final artifacts.

    It is an input builder for a :class:`LogFeedbackSource` of :class:`TaskCompletion` and for
    an :class:`OnlineEvaluator` that judges threads. The request is the thread's first message
    from a person; the result is the artifacts the thread followed, each as the agent sees it.
    Long threads may need summarizing for a decision model's input budget, which is evalr's
    concern.
    """
    turns = [
        Turn(role=actor_role(envelope.actor), text=envelope.event.content)
        for envelope in context.transcript
        if isinstance(envelope.event, MessagePosted)
    ]
    request = next((turn.text for turn in turns if turn.role == "person"), "")
    result = "\n\n".join(_artifact_text(artifact) for artifact in context.artifacts)
    return Transcript(request=request, turns=turns, result=result or None)


def _artifact_text(artifact: Versioned[Artifact]) -> str:
    return (
        f'<artifact id="{artifact.id}" kind="{artifact.kind}" version="{artifact.version}">\n'
        f"{artifact.data.render_for_agent()}\n</artifact>"
    )
