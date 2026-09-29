"""Commits are traced and counted; what committed events did is counted too."""

from typing import Any

import pytest

from artifactr.core import (
    AgentActor,
    AnswerDeferred,
    CreateArtifact,
    CreateThread,
    DeferredRequest,
    EditArtifact,
    InvalidState,
    JsonPatch,
    NotFound,
    ProposeChange,
    RespondToProposal,
    RunEnded,
    RunPaused,
    RunStarted,
    RunUsage,
    SetFocus,
    ToolCalled,
    ToolReturned,
    UserActor,
    VersionConflict,
)
from artifactr.telemetry.attributes import (
    ACTOR_KIND,
    ARTIFACT_ID,
    ARTIFACT_KIND,
    ARTIFACT_VERSION,
    CHANGE,
    COMMAND_TYPE,
    ERROR_TYPE,
    GEN_AI_CONVERSATION_ID,
    GEN_AI_TOKEN_TYPE,
    GEN_AI_TOOL_NAME,
    OUTCOME,
    PATCH_KIND,
    PATCH_SIZE,
    PROPOSAL_ACTION,
    PROPOSAL_ID,
    REJECTION,
    RUN_ID,
    RUN_STATUS,
    SESSION_ID,
    TENANT_ID,
    THREAD_ID,
    TOOL_STATUS,
    USER_ID,
    WORKSPACE_ID,
)
from artifactr.workspace import InMemoryStorage, Scope, Workspace, Workspaces
from tests.artifact_types import Checklist, Note
from tests.telemetry.conftest import Recorder, attributes, trace_id

ALICE = UserActor(id="alice", name="Alice")


@pytest.fixture
async def ws(recorder: Recorder) -> Workspace:
    return await Workspaces(InMemoryStorage(), **recorder.providers).open("t1", "w1", actor=ALICE)


async def test_a_commit_is_a_span_with_its_command_and_outcome(
    ws: Workspace, recorder: Recorder
) -> None:
    await ws.create(Note(text="Ship Friday"), artifact_id="n1")
    span = recorder.span("artifactr.commit create_artifact")
    assert attributes(span) == {
        TENANT_ID: "t1",
        WORKSPACE_ID: "w1",
        ACTOR_KIND: "user",
        USER_ID: "alice",
        COMMAND_TYPE: "create_artifact",
        ARTIFACT_ID: "n1",
        OUTCOME: "applied",
        ARTIFACT_VERSION: 1,
    }
    [revision] = await ws.revisions("n1")
    assert revision.trace_id == trace_id(span), "the revision links to the commit's trace"
    assert recorder.total("artifactr.commands", {COMMAND_TYPE: "create_artifact"}) == 1
    assert recorder.total("artifactr.commit.duration", {OUTCOME: "applied"}) == 1


async def test_an_untraced_commit_links_no_trace() -> None:
    ws = await Workspaces(InMemoryStorage()).open("t1", "w1", actor=ALICE)
    await ws.create(Note(text="Ship Friday"), artifact_id="n1")
    [revision] = await ws.revisions("n1")
    assert revision.trace_id is None


async def test_commit_spans_describe_patches_threads_and_proposals(
    ws: Workspace, recorder: Recorder
) -> None:
    thread = await ws.create_thread("Launch")
    await ws.post_message(thread.id, "hello")
    await ws.create(Note(text="Ship Friday"), artifact_id="n1", thread_id=thread.id)
    note = await ws.get(Note, "n1")
    await ws.commit(note.edit_text("Friday", "Monday"))
    await ws.commit(
        EditArtifact(
            artifact_id="n1",
            base_version=2,
            patch=JsonPatch(ops=({"op": "replace", "path": "/title", "value": "Plan"},)),
        )
    )
    posted = recorder.span("artifactr.commit post_message")
    assert {SESSION_ID, GEN_AI_CONVERSATION_ID, THREAD_ID} <= set(attributes(posted))
    assert attributes(posted)[SESSION_ID] == thread.id
    first, second = recorder.spans("artifactr.commit edit_artifact")
    assert (attributes(first)[PATCH_KIND], attributes(first)[PATCH_SIZE]) == ("text_edits", 1)
    assert (attributes(second)[PATCH_KIND], attributes(second)[PATCH_SIZE]) == ("json_patch", 1)

    agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_1"))
    await agent.record(RunStarted(run_id="run_1", thread_id=thread.id))
    proposal = ProposeChange(
        change=CreateArtifact(artifact_id="c1", kind="checklist", data={}), proposal_id="p1"
    )
    await agent.commit(proposal)
    proposed = attributes(recorder.span("artifactr.commit propose_change"))
    assert proposed[ACTOR_KIND] == "agent"
    assert (proposed[THREAD_ID], proposed[RUN_ID]) == (thread.id, "run_1"), "from the agent"
    assert (proposed[ARTIFACT_ID], proposed[PROPOSAL_ID], proposed[OUTCOME]) == (
        "c1",
        "p1",
        "proposed",
    )
    await ws.commit(RespondToProposal(proposal_id="p1", decision="accept"))
    resolved = attributes(recorder.span("artifactr.commit respond_to_proposal"))
    assert (resolved[PROPOSAL_ID], resolved[OUTCOME], resolved[ARTIFACT_VERSION]) == (
        "p1",
        "resolved",
        1,
    )
    await agent.commit(ProposeChange(change=(await ws.get(Checklist, "c1")).archive()))
    [pending] = await ws.proposals()
    await ws.commit(RespondToProposal(proposal_id=pending.id, decision="reject"))
    rejected = attributes(recorder.spans("artifactr.commit respond_to_proposal")[-1])
    assert ARTIFACT_VERSION not in rejected
    await ws.commit(SetFocus(thread_id=thread.id, artifact_ids=("n1",)))
    assert attributes(recorder.span("artifactr.commit set_focus"))[OUTCOME] == "recorded"


async def test_a_rejected_commit_is_recorded_as_rejected(ws: Workspace, recorder: Recorder) -> None:
    await ws.create(Note(text="a"), artifact_id="n1")
    note = await ws.get(Note, "n1")
    await ws.commit(note.edit_text("a", "b"))
    with pytest.raises(VersionConflict):
        await ws.commit(note.edit_text("a", "c"))
    with pytest.raises(NotFound):
        await ws.commit(AnswerDeferred(run_id="run_nope", tool_call_id="c1", answer="x"))
    conflict, _ = recorder.spans("artifactr.commit edit_artifact")[::-1]
    assert (attributes(conflict)[OUTCOME], attributes(conflict)[REJECTION]) == (
        "rejected",
        "version_conflict",
    )
    answered = attributes(recorder.span("artifactr.commit answer_deferred"))
    assert answered[RUN_ID] == "run_nope"
    where = {OUTCOME: "rejected", REJECTION: "version_conflict", ACTOR_KIND: "user"}
    assert recorder.total("artifactr.commands", where) == 1
    assert recorder.total("artifactr.commands", {REJECTION: "not_found"}) == 1


async def test_a_type_outside_the_allowlist_is_a_rejected_commit(recorder: Recorder) -> None:
    workspaces = Workspaces(InMemoryStorage(), types=[Note], **recorder.providers)
    ws = await workspaces.open("t1", "w1", actor=ALICE)
    with pytest.raises(NotFound):
        await ws.commit(CreateArtifact(kind="checklist", data={}))
    assert attributes(recorder.span("artifactr.commit create_artifact"))[REJECTION] == "not_found"


async def test_an_unexpected_failure_is_an_error(
    recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = InMemoryStorage()

    def broken(scope: Scope) -> Any:
        raise RuntimeError("the database is down")

    monkeypatch.setattr(storage, "transaction", broken)
    ws = await Workspaces(storage, **recorder.providers).open("t1", "w1", actor=ALICE)
    with pytest.raises(RuntimeError, match="the database is down"):
        await ws.commit(CreateThread())
    span = recorder.span("artifactr.commit create_thread")
    assert (attributes(span)[OUTCOME], attributes(span)[ERROR_TYPE]) == ("error", "RuntimeError")
    assert not span.status.is_ok
    assert [event.name for event in span.events] == ["exception"]
    assert recorder.total("artifactr.commands", {OUTCOME: "error"}) == 1


async def test_what_events_do_is_counted(ws: Workspace, recorder: Recorder) -> None:
    thread = await ws.create_thread()
    await ws.post_message(thread.id, "hello")
    await ws.create(Note(text="a"), artifact_id="n1")
    await ws.commit((await ws.get(Note, "n1")).edit_text("a", "b"))
    await ws.commit((await ws.get(Note, "n1")).archive())
    agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_1"))
    await agent.record(RunStarted(run_id="run_1", thread_id=thread.id))
    await agent.record(
        ToolCalled(run_id="run_1", thread_id=thread.id, tool_call_id="c1", tool_name="pick")
    )
    await agent.record(
        ToolReturned(
            run_id="run_1", thread_id=thread.id, tool_call_id="c1", tool_name="pick", status="ok"
        )
    )
    await agent.commit(ProposeChange(change=CreateArtifact(kind="checklist", data={})))
    [proposal] = await ws.proposals()
    await ws.commit(RespondToProposal(proposal_id=proposal.id, decision="reject"))
    await agent.post_message(thread.id, "done")
    question = DeferredRequest(tool_call_id="q1", tool_name="ask_user", kind="question")
    usage = RunUsage(requests=1, input_tokens=10, output_tokens=0)
    await agent.record(
        RunPaused(run_id="run_1", thread_id=thread.id, requests=(question,), usage=usage)
    )
    await agent.record(
        RunEnded(
            run_id="run_1",
            thread_id=thread.id,
            status="completed",
            usage=RunUsage(requests=1, input_tokens=5, output_tokens=7),
        )
    )
    await agent.record(RunStarted(run_id="run_2", thread_id=thread.id))
    await agent.record(RunEnded(run_id="run_2", thread_id=thread.id, status="failed"))

    assert recorder.total("artifactr.messages", {ACTOR_KIND: "user"}) == 1
    assert recorder.total("artifactr.messages", {ACTOR_KIND: "agent"}) == 1
    for change in ("created", "changed", "archived"):
        where = {CHANGE: change, ARTIFACT_KIND: "note", ACTOR_KIND: "user"}
        assert recorder.total("artifactr.artifact.changes", where) == 1
    assert recorder.total("artifactr.proposals", {PROPOSAL_ACTION: "created"}) == 1
    assert recorder.total("artifactr.proposals", {PROPOSAL_ACTION: "rejected"}) == 1
    where = {GEN_AI_TOOL_NAME: "pick", TOOL_STATUS: "ok", TENANT_ID: "t1"}
    assert recorder.total("artifactr.tool_calls", where) == 1
    for status in ("paused", "completed", "failed"):
        assert recorder.total("artifactr.runs", {RUN_STATUS: status}) == 1
    assert recorder.total("artifactr.tokens", {GEN_AI_TOKEN_TYPE: "input"}) == 15
    assert recorder.total("artifactr.tokens", {GEN_AI_TOKEN_TYPE: "output"}) == 7


async def test_an_accepted_proposal_counts_as_accepted(ws: Workspace, recorder: Recorder) -> None:
    thread = await ws.create_thread()
    agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_1"))
    await agent.commit(ProposeChange(change=CreateArtifact(kind="checklist", data={})))
    [proposal] = await ws.proposals()
    await ws.commit(RespondToProposal(proposal_id=proposal.id, decision="accept"))
    assert recorder.total("artifactr.proposals", {PROPOSAL_ACTION: "accepted"}) == 1
    with pytest.raises(InvalidState):
        await ws.commit(RespondToProposal(proposal_id=proposal.id, decision="accept"))
