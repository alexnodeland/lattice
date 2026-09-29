"""The rules: how commands and run facts change a workspace.

Every function here is pure. A host uses them in three steps:

1. :func:`needs` says which entities to load; the host loads them into a
   :class:`~artifactr.core.state.State`, repeating until nothing more is needed.
2. :func:`commit` (for commands) or :func:`record` (for facts about agent runs) decides the
   outcome, or raises a :class:`~artifactr.core.errors.Rejection`.
3. The host persists the returned :class:`~artifactr.core.state.CommitResult` in one
   transaction.
"""

from collections.abc import Mapping
from typing import assert_never

from artifactr.core.actors import (
    Actor,
    AgentActor,
    EvaluatorActor,
    SystemActor,
    is_agent,
    same_participant,
)
from artifactr.core.artifacts import Artifact, Versioned, get_artifact_type, load_artifact
from artifactr.core.commands import (
    AnswerDeferred,
    ArchiveArtifact,
    Command,
    CreateArtifact,
    CreateThread,
    EditArtifact,
    GiveFeedback,
    PostMessage,
    ProposeChange,
    ProposedChange,
    RespondToProposal,
    SetFocus,
    SetThreadMode,
)
from artifactr.core.errors import (
    Forbidden,
    InvalidState,
    NotFound,
    PatchFailed,
    VersionConflict,
)
from artifactr.core.events import (
    AppEvent,
    ArtifactArchived,
    ArtifactChanged,
    ArtifactCreated,
    DeferredAnswered,
    FeedbackGiven,
    FocusChanged,
    MessagePosted,
    ProposalCreated,
    ProposalResolved,
    RunEnded,
    RunEvent,
    RunPaused,
    RunStarted,
    ThreadCreated,
    ThreadModeChanged,
    ToolCalled,
    ToolReturned,
)
from artifactr.core.feedback import (
    ArtifactTarget,
    MessageTarget,
    ThreadTarget,
    TurnTarget,
    load_feedback,
)
from artifactr.core.ids import ArtifactId, ProposalId, RunId, ThreadId, TraceId
from artifactr.core.patches import Patch, apply_patch, describe_patch, diff
from artifactr.core.state import (
    Applied,
    CommitResult,
    DeferredAnswer,
    Needs,
    Proposal,
    Proposed,
    Recorded,
    Resolved,
    Revision,
    Run,
    State,
    Thread,
)

Fact = RunEvent | AppEvent
"""A fact recorded by the agent layer rather than commanded."""


class NotLoaded(LookupError):
    """The host called a rule without loading an entity that :func:`needs` asked for.

    This is a bug in the host, not a rejection of the command.
    """


# ─── needs ────────────────────────────────────────────────────────────────────


def needs(item: Command | Fact, *, actor: Actor, state: State | None = None) -> Needs:
    """Return the ids a host must still load before calling :func:`commit` or :func:`record`.

    Call it repeatedly, loading what it returns, until it returns an empty (falsy)
    :class:`~artifactr.core.state.Needs`: some commands only know what else they need once
    their first entities are loaded.
    """
    state = state or State()
    wanted = _wanted(item, actor, state)
    return Needs(
        artifacts=frozenset(i for i in wanted.artifacts if i not in state.artifacts),
        proposals=frozenset(i for i in wanted.proposals if i not in state.proposals),
        threads=frozenset(i for i in wanted.threads if i not in state.threads),
        runs=frozenset(i for i in wanted.runs if i not in state.runs),
        messages=frozenset(i for i in wanted.messages if i not in state.messages),
    )


def _wanted(item: Command | Fact, actor: Actor, state: State) -> Needs:
    match item:
        case CreateArtifact() | EditArtifact() | ArchiveArtifact():
            return Needs(
                artifacts=frozenset({item.artifact_id}),
                proposals=frozenset({item.proposal_id}),
                threads=_context_threads(item.thread_id, actor),
            )
        case ProposeChange():
            change = _wanted(item.change, actor, state)
            return Needs(
                artifacts=change.artifacts,
                proposals=frozenset({item.proposal_id}),
                threads=change.threads,
            )
        case RespondToProposal():
            proposal = state.proposals.get(item.proposal_id)
            return Needs(
                proposals=frozenset({item.proposal_id}),
                artifacts=frozenset({proposal.artifact_id}) if proposal else frozenset(),
            )
        case PostMessage():
            return Needs(threads=frozenset({item.thread_id}), messages=frozenset({item.message_id}))
        case CreateThread() | SetThreadMode():
            return Needs(threads=frozenset({item.thread_id}))
        case SetFocus():
            return Needs(
                threads=frozenset({item.thread_id}), artifacts=frozenset(item.artifact_ids)
            )
        case AnswerDeferred():
            return Needs(runs=frozenset({item.run_id}))
        case GiveFeedback():
            return _feedback_needs(item.target)
        case RunStarted():
            return Needs(threads=frozenset({item.thread_id}), runs=frozenset({item.run_id}))
        case ToolCalled() | ToolReturned() | RunPaused() | RunEnded():
            return Needs(runs=frozenset({item.run_id}))
        case AppEvent():
            return Needs(threads=frozenset({item.thread_id}) if item.thread_id else frozenset())
        case _:
            assert_never(item)


def _feedback_needs(target: ArtifactTarget | ThreadTarget | TurnTarget | MessageTarget) -> Needs:
    match target:
        case ArtifactTarget():
            return Needs(artifacts=frozenset({target.artifact_id}))
        case ThreadTarget():
            return Needs(threads=frozenset({target.thread_id}))
        case TurnTarget():
            return Needs(runs=frozenset({target.run_id}))
        case MessageTarget():
            runs: frozenset[RunId] = frozenset({target.run_id} if target.run_id else ())
            return Needs(threads=frozenset({target.thread_id}), runs=runs)
        case _:
            assert_never(target)


def _context_threads(thread_id: ThreadId | None, actor: Actor) -> frozenset[ThreadId]:
    context = _context_thread_id(thread_id, actor)
    return frozenset({context}) if context else frozenset()


# ─── commit ───────────────────────────────────────────────────────────────────


def commit(command: Command, state: State, *, actor: Actor) -> CommitResult:
    """Decide a command against the loaded state.

    Returns:
        What to persist, and the outcome to report.

    Raises:
        Rejection: If the command cannot be applied; see :mod:`artifactr.core.errors`.
        NotLoaded: If ``state`` lacks something :func:`needs` asked for.
    """
    if isinstance(actor, EvaluatorActor) and not isinstance(command, GiveFeedback):
        raise Forbidden("an evaluator can only give feedback")
    match command:
        case CreateArtifact():
            return _create(command, state, actor)
        case EditArtifact():
            return _edit(command, state, actor)
        case ArchiveArtifact():
            return _archive(command, state, actor)
        case ProposeChange():
            return _propose(command.proposal_id, command.change, command.rationale, state, actor)
        case RespondToProposal():
            return _respond(command, state, actor)
        case CreateThread():
            return _create_thread(command, state)
        case PostMessage():
            return _post_message(command, state, actor)
        case SetFocus():
            return _set_focus(command, state)
        case SetThreadMode():
            return _set_thread_mode(command, state)
        case AnswerDeferred():
            return _answer(command, state)
        case GiveFeedback():
            return _give_feedback(command, state)
        case _:
            assert_never(command)


def _create(command: CreateArtifact, state: State, actor: Actor) -> CommitResult:
    artifact_type = get_artifact_type(command.kind)
    if _must_propose(artifact_type, command.thread_id, actor, state):
        return _propose(command.proposal_id, command, None, state, actor)
    return _apply_create(
        command,
        None,
        state,
        actor,
        thread_id=_context_thread_id(command.thread_id, actor),
        proposal_id=None,
    )


def _edit(command: EditArtifact, state: State, actor: Actor) -> CommitResult:
    current = _current(state, command.artifact_id)
    _check_version(current, command.base_version)
    if _must_propose(type(current.data), command.thread_id, actor, state):
        return _propose(command.proposal_id, command, None, state, actor)
    return _apply_edit(
        current,
        command.patch,
        None,
        actor=actor,
        summary=command.summary,
        thread_id=_context_thread_id(command.thread_id, actor),
        proposal_id=None,
    )


def _archive(command: ArchiveArtifact, state: State, actor: Actor) -> CommitResult:
    current = _current(state, command.artifact_id)
    _check_version(current, command.base_version)
    if _must_propose(type(current.data), command.thread_id, actor, state):
        return _propose(command.proposal_id, command, None, state, actor)
    return _apply_archive(
        current,
        actor=actor,
        thread_id=_context_thread_id(command.thread_id, actor),
        proposal_id=None,
    )


def _propose(
    proposal_id: ProposalId,
    change: ProposedChange,
    rationale: str | None,
    state: State,
    actor: Actor,
) -> CommitResult:
    if _loaded(state.proposals, proposal_id, "proposal") is not None:
        raise InvalidState(f"proposal {proposal_id} already exists")
    if not isinstance(change, CreateArtifact):
        _check_version(_current(state, change.artifact_id), change.base_version)
    thread_id = _context_thread_id(change.thread_id, actor)
    # The change must apply now; what it would produce is discarded until someone accepts it,
    # except the summary of an edit, which tells reviewers what they are asked to accept.
    dry_run = _apply_change(
        change, None, state, actor, thread_id=thread_id, proposal_id=proposal_id
    )
    if isinstance(change, EditArtifact) and change.summary is None:
        [changed] = dry_run.events
        assert isinstance(changed, ArtifactChanged)
        change = change.model_copy(update={"summary": changed.summary})
    proposal = Proposal(
        id=proposal_id,
        change=change,
        proposed_by=actor,
        rationale=rationale,
        thread_id=thread_id,
    )
    event = ProposalCreated(
        proposal_id=proposal_id,
        change=change,
        rationale=rationale,
        thread_id=thread_id,
        run_id=_run_id(actor),
    )
    return CommitResult(
        outcome=Proposed(proposal_id=proposal_id), events=(event,), proposals=(proposal,)
    )


def _respond(command: RespondToProposal, state: State, actor: Actor) -> CommitResult:
    proposal = _loaded(state.proposals, command.proposal_id, "proposal")
    if proposal is None:
        raise NotFound("proposal", command.proposal_id)
    if proposal.status != "pending":
        raise InvalidState(f"proposal {proposal.id} is already {proposal.status}")
    if same_participant(actor, proposal.proposed_by):
        raise Forbidden("a proposal must be resolved by someone other than its author")
    if command.decision == "reject":
        return CommitResult(
            outcome=Resolved(proposal_id=proposal.id, decision="reject"),
            events=(_resolved(proposal, command, actor, version=None),),
            proposals=(proposal.model_copy(update={"status": "rejected"}),),
        )
    applied = _apply_change(
        proposal.change,
        command.changes,
        state,
        actor,
        thread_id=proposal.thread_id,
        proposal_id=proposal.id,
    )
    assert isinstance(applied.outcome, Applied)
    version = applied.outcome.version
    return CommitResult(
        outcome=Resolved(proposal_id=proposal.id, decision="accept", version=version),
        events=(*applied.events, _resolved(proposal, command, actor, version=version)),
        artifacts=applied.artifacts,
        revisions=applied.revisions,
        proposals=(proposal.model_copy(update={"status": "accepted"}),),
    )


def _resolved(
    proposal: Proposal, command: RespondToProposal, actor: Actor, *, version: int | None
) -> ProposalResolved:
    return ProposalResolved(
        proposal_id=proposal.id,
        decision=command.decision,
        proposed_by=proposal.proposed_by,
        artifact_id=proposal.artifact_id,
        changes=command.changes,
        reason=command.reason,
        version=version,
        thread_id=proposal.thread_id,
        run_id=_run_id(actor),
    )


def _apply_change(
    change: ProposedChange,
    changes: Patch | None,
    state: State,
    actor: Actor,
    *,
    thread_id: ThreadId | None,
    proposal_id: ProposalId,
) -> CommitResult:
    """Apply a proposed change, rebased onto the current version, ignoring write policy."""
    match change:
        case CreateArtifact():
            return _apply_create(
                change, changes, state, actor, thread_id=thread_id, proposal_id=proposal_id
            )
        case EditArtifact():
            return _apply_edit(
                _current(state, change.artifact_id),
                change.patch,
                changes,
                actor=actor,
                # A reviewer's changes make the proposal's summary stale: describe the result.
                summary=change.summary if changes is None else None,
                thread_id=thread_id,
                proposal_id=proposal_id,
            )
        case ArchiveArtifact():
            if changes is not None:
                raise PatchFailed("changes cannot be applied to a proposal to archive")
            return _apply_archive(
                _current(state, change.artifact_id),
                actor=actor,
                thread_id=thread_id,
                proposal_id=proposal_id,
            )
        case _:
            assert_never(change)


def _apply_create(
    command: CreateArtifact,
    changes: Patch | None,
    state: State,
    actor: Actor,
    *,
    thread_id: ThreadId | None,
    proposal_id: ProposalId | None,
) -> CommitResult:
    if _loaded(state.artifacts, command.artifact_id, "artifact") is not None:
        raise InvalidState(f"artifact {command.artifact_id} already exists")
    data = command.data if changes is None else apply_patch(command.data, changes)
    artifact = load_artifact(command.kind, data)
    stored = artifact.to_json()
    return CommitResult(
        outcome=Applied(artifact_id=command.artifact_id, version=1),
        events=(
            ArtifactCreated(
                artifact_id=command.artifact_id,
                kind=artifact.kind,
                version=1,
                data=stored,
                proposal_id=proposal_id,
                thread_id=thread_id,
                run_id=_run_id(actor),
            ),
        ),
        artifacts=(
            Versioned[Artifact](id=command.artifact_id, version=1, data=artifact, updated_by=actor),
        ),
        revisions=(
            Revision(
                artifact_id=command.artifact_id,
                version=1,
                kind=artifact.kind,
                data=stored,
                actor=actor,
                proposal_id=proposal_id,
            ),
        ),
    )


def _apply_edit(
    current: Versioned[Artifact],
    patch: Patch,
    changes: Patch | None,
    *,
    actor: Actor,
    summary: str | None,
    thread_id: ThreadId | None,
    proposal_id: ProposalId | None,
) -> CommitResult:
    before = current.data.to_json()
    patched = apply_patch(before, patch)
    if changes is not None:
        patched = apply_patch(patched, changes)
    after = load_artifact(current.kind, patched)
    stored = after.to_json()
    if stored == before:
        raise PatchFailed("the change leaves the artifact unchanged")
    # The recorded patch must turn the previous version into exactly what is stored. The
    # original patch does, unless changes were layered on or validation normalized the data.
    recorded = patch if changes is None and stored == patched else diff(before, stored)
    version = current.version + 1
    return CommitResult(
        outcome=Applied(artifact_id=current.id, version=version),
        events=(
            ArtifactChanged(
                artifact_id=current.id,
                kind=current.kind,
                version=version,
                patch=recorded,
                summary=summary or after.describe_change(current.data) or describe_patch(recorded),
                proposal_id=proposal_id,
                thread_id=thread_id,
                run_id=_run_id(actor),
            ),
        ),
        artifacts=(
            Versioned[Artifact](id=current.id, version=version, data=after, updated_by=actor),
        ),
        revisions=(
            Revision(
                artifact_id=current.id,
                version=version,
                kind=current.kind,
                data=stored,
                patch=recorded,
                actor=actor,
                proposal_id=proposal_id,
            ),
        ),
    )


def _apply_archive(
    current: Versioned[Artifact],
    *,
    actor: Actor,
    thread_id: ThreadId | None,
    proposal_id: ProposalId | None,
) -> CommitResult:
    version = current.version + 1
    return CommitResult(
        outcome=Applied(artifact_id=current.id, version=version),
        events=(
            ArtifactArchived(
                artifact_id=current.id,
                kind=current.kind,
                version=version,
                proposal_id=proposal_id,
                thread_id=thread_id,
                run_id=_run_id(actor),
            ),
        ),
        artifacts=(
            Versioned[Artifact](
                id=current.id,
                version=version,
                data=current.data,
                updated_by=actor,
                archived=True,
            ),
        ),
        revisions=(
            Revision(
                artifact_id=current.id,
                version=version,
                kind=current.kind,
                data=current.data.to_json(),
                actor=actor,
                proposal_id=proposal_id,
                archived=True,
            ),
        ),
    )


def _create_thread(command: CreateThread, state: State) -> CommitResult:
    if _loaded(state.threads, command.thread_id, "thread") is not None:
        raise InvalidState(f"thread {command.thread_id} already exists")
    return CommitResult(
        outcome=Recorded(),
        events=(ThreadCreated(thread_id=command.thread_id, title=command.title),),
        threads=(Thread(id=command.thread_id, title=command.title),),
    )


def _post_message(command: PostMessage, state: State, actor: Actor) -> CommitResult:
    _thread(state, command.thread_id)
    if _loaded(state.messages, command.message_id, "message"):
        raise InvalidState(f"message {command.message_id} already exists")
    return CommitResult(
        outcome=Recorded(),
        events=(
            MessagePosted(
                thread_id=command.thread_id,
                message_id=command.message_id,
                content=command.content,
                run_id=_run_id(actor),
            ),
        ),
        messages=(command.message_id,),
    )


def _set_focus(command: SetFocus, state: State) -> CommitResult:
    thread = _thread(state, command.thread_id)
    for artifact_id in command.artifact_ids:
        if _loaded(state.artifacts, artifact_id, "artifact") is None:
            raise NotFound("artifact", artifact_id)
    focus = tuple(dict.fromkeys(command.artifact_ids))
    if focus == thread.focus:
        return CommitResult(outcome=Recorded())
    return CommitResult(
        outcome=Recorded(),
        events=(FocusChanged(thread_id=thread.id, artifact_ids=focus),),
        threads=(thread.model_copy(update={"focus": focus}),),
    )


def _set_thread_mode(command: SetThreadMode, state: State) -> CommitResult:
    thread = _thread(state, command.thread_id)
    if command.mode == thread.mode:
        return CommitResult(outcome=Recorded())
    return CommitResult(
        outcome=Recorded(),
        events=(ThreadModeChanged(thread_id=thread.id, mode=command.mode),),
        threads=(thread.model_copy(update={"mode": command.mode}),),
    )


def _answer(command: AnswerDeferred, state: State) -> CommitResult:
    run = _run(state, command.run_id)
    if run.status != "paused":
        raise InvalidState(f"run {run.id} is {run.status}, not paused")
    request = next((r for r in run.pending if r.tool_call_id == command.tool_call_id), None)
    if request is None:
        raise NotFound("deferred request", command.tool_call_id)
    if command.tool_call_id in run.answers:
        raise InvalidState(f"deferred request {command.tool_call_id} is already answered")
    if (request.kind == "approval") != (command.approved is not None):
        raise InvalidState(
            "an approval needs approved=true or false"
            if request.kind == "approval"
            else "a question is answered with answer, not approved"
        )
    answer = DeferredAnswer(answer=command.answer, approved=command.approved)
    return CommitResult(
        outcome=Recorded(),
        events=(
            DeferredAnswered(
                run_id=run.id,
                thread_id=run.thread_id,
                tool_call_id=command.tool_call_id,
                answer=command.answer,
                approved=command.approved,
            ),
        ),
        runs=(run.model_copy(update={"answers": {**run.answers, command.tool_call_id: answer}}),),
    )


def _give_feedback(command: GiveFeedback, state: State) -> CommitResult:
    feedback = load_feedback(command.feedback_type, command.target, command.value)
    thread_id, run_id = _feedback_scope(command.target, state)
    return CommitResult(
        outcome=Recorded(),
        events=(
            FeedbackGiven(
                feedback_type=command.feedback_type,
                target=command.target,
                value=feedback.model_dump(mode="json"),
                thread_id=thread_id,
                run_id=run_id,
            ),
        ),
    )


def _feedback_scope(
    target: ArtifactTarget | ThreadTarget | TurnTarget | MessageTarget, state: State
) -> tuple[ThreadId | None, RunId | None]:
    """Check that feedback's target exists; return the thread and run it belongs to."""
    match target:
        case ArtifactTarget():
            artifact = _loaded(state.artifacts, target.artifact_id, "artifact")
            if artifact is None:
                raise NotFound("artifact", target.artifact_id)
            if target.version > artifact.version:
                raise NotFound("artifact version", f"{target.artifact_id} v{target.version}")
            return None, None
        case ThreadTarget():
            return _thread(state, target.thread_id).id, None
        case TurnTarget():
            run = _run(state, target.run_id)
            return run.thread_id, run.id
        case MessageTarget():
            _thread(state, target.thread_id)
            if target.run_id is not None:
                run = _run(state, target.run_id)
                if run.thread_id != target.thread_id:
                    raise InvalidState(f"run {run.id} belongs to thread {run.thread_id}")
            return target.thread_id, target.run_id
        case _:
            assert_never(target)


# ─── record ───────────────────────────────────────────────────────────────────


def record(fact: Fact, state: State, *, actor: Actor) -> CommitResult:
    """Decide a fact about an agent run, or an application event, against the loaded state.

    Only the thread's own agent, or the system, may record facts about the thread's runs.

    Raises:
        Rejection: If the fact contradicts the run's state, such as a tool call after the run
            ended, or the actor may not record it.
        NotLoaded: If ``state`` lacks something :func:`needs` asked for.
    """
    if not isinstance(fact, AppEvent):
        _check_recorder(actor, fact.thread_id)
    match fact:
        case RunStarted():
            return _run_started(fact, state)
        case ToolCalled() | ToolReturned():
            _active_run(state, fact.run_id, fact.thread_id, allowed=("running",))
            return CommitResult(outcome=Recorded(), events=(fact,))
        case RunPaused():
            run = _active_run(state, fact.run_id, fact.thread_id, allowed=("running",))
            paused = run.model_copy(update={"status": "paused", "pending": fact.requests})
            return CommitResult(outcome=Recorded(), events=(fact,), runs=(paused,))
        case RunEnded():
            run = _active_run(state, fact.run_id, fact.thread_id, allowed=("running", "paused"))
            ended = run.model_copy(update={"status": fact.status, "pending": (), "answers": {}})
            return CommitResult(outcome=Recorded(), events=(fact,), runs=(ended,))
        case AppEvent():
            if fact.thread_id is not None:
                _thread(state, fact.thread_id)
            return CommitResult(outcome=Recorded(), events=(fact,))
        case _:
            assert_never(fact)


def _check_recorder(actor: Actor, thread_id: ThreadId) -> None:
    if isinstance(actor, SystemActor):
        return
    if isinstance(actor, AgentActor) and actor.thread_id == thread_id:
        return
    raise Forbidden(f"only thread {thread_id}'s agent or the system may record its runs")


def _run_started(fact: RunStarted, state: State) -> CommitResult:
    _thread(state, fact.thread_id)
    existing = _loaded(state.runs, fact.run_id, "run")
    traces: tuple[TraceId, ...] = ()
    if existing is not None:
        if existing.thread_id != fact.thread_id:
            raise InvalidState(f"run {existing.id} belongs to thread {existing.thread_id}")
        if existing.status != "paused":
            raise InvalidState(f"run {existing.id} is {existing.status} and cannot start again")
        traces = existing.trace_ids
    if fact.trace_id is not None:
        traces = (*traces, fact.trace_id)
    run = Run(id=fact.run_id, thread_id=fact.thread_id, trace_ids=traces)
    return CommitResult(outcome=Recorded(), events=(fact,), runs=(run,))


# ─── helpers ──────────────────────────────────────────────────────────────────


def _loaded[K, V](entities: Mapping[K, V | None], key: K, entity: str) -> V | None:
    if key not in entities:
        raise NotLoaded(f"{entity} {key} was not loaded; load what needs() returns first")
    return entities[key]


def _current(state: State, artifact_id: ArtifactId) -> Versioned[Artifact]:
    artifact = _loaded(state.artifacts, artifact_id, "artifact")
    if artifact is None:
        raise NotFound("artifact", artifact_id)
    if artifact.archived:
        raise InvalidState(f"artifact {artifact_id} is archived")
    return artifact


def _thread(state: State, thread_id: ThreadId) -> Thread:
    thread = _loaded(state.threads, thread_id, "thread")
    if thread is None:
        raise NotFound("thread", thread_id)
    return thread


def _run(state: State, run_id: RunId) -> Run:
    run = _loaded(state.runs, run_id, "run")
    if run is None:
        raise NotFound("run", run_id)
    return run


def _active_run(
    state: State, run_id: RunId, thread_id: ThreadId, *, allowed: tuple[str, ...]
) -> Run:
    run = _run(state, run_id)
    if run.thread_id != thread_id:
        raise InvalidState(f"run {run_id} belongs to thread {run.thread_id}")
    if run.status not in allowed:
        raise InvalidState(f"run {run_id} is {run.status}")
    return run


def _check_version(current: Versioned[Artifact], base_version: int) -> None:
    if base_version != current.version:
        raise VersionConflict(current.id, base=base_version, head=current.version)


def _context_thread_id(thread_id: ThreadId | None, actor: Actor) -> ThreadId | None:
    if thread_id is not None:
        return thread_id
    return actor.thread_id if isinstance(actor, AgentActor) else None


def _run_id(actor: Actor) -> RunId | None:
    return actor.run_id if isinstance(actor, AgentActor) else None


def _must_propose(
    artifact_type: type[Artifact], thread_id: ThreadId | None, actor: Actor, state: State
) -> bool:
    if not is_agent(actor):
        return False
    if artifact_type.write_policy == "propose":
        return True
    context = _context_thread_id(thread_id, actor)
    return context is not None and _thread(state, context).mode == "suggest"
