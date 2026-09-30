"""End-to-end measures from the log: drop-off and rewrites exactly, task completion judged."""

from datetime import UTC, datetime, timedelta

import pytest

from artifactr.core import (
    Actor,
    AgentActor,
    Applied,
    Artifact,
    EvaluatorActor,
    ExternalAgentActor,
    GiveFeedback,
    JsonPatch,
    Proposed,
    RespondToProposal,
    SetFocus,
    SystemActor,
    ThreadTarget,
    UserActor,
    create_artifact,
)
from artifactr.evals import (
    LogFeedbackSource,
    TaskCompletion,
    actor_role,
    artifact_histories,
    completion_transcript,
    target_context,
    thread_sessions,
)
from artifactr.workspace import InMemoryStorage, Workspace, Workspaces
from evalr.core import FunctionEvaluator
from evalr.measures import (
    Revision,
    Transcript,
    Turn,
    completion_rate,
    drop_off_evaluator,
    drop_off_rate,
    measure_drop_off,
    measure_rewrites,
    rewrite_evaluator,
    rewrite_rate,
)
from tests.artifact_types import Checklist, Note

ALICE = UserActor(id="alice", name="Alice")
WINDOW = timedelta(minutes=30)
START = datetime(2026, 9, 29, 9, 0, tzinfo=UTC)


class Clock:
    """The time the storage stamps on envelopes, moved on by the test."""

    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def at(self, minutes: int) -> None:
        self.now = START + timedelta(minutes=minutes)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
async def ws(clock: Clock) -> Workspace:
    return await Workspaces(InMemoryStorage(clock=clock)).open("t", "w", actor=ALICE)


def agent_in(ws: Workspace, thread_id: str) -> Workspace:
    return ws.as_actor(AgentActor(thread_id=thread_id))


@pytest.mark.parametrize(
    ("actor", "role"),
    [
        (ALICE, "person"),
        (AgentActor(thread_id="t"), "agent"),
        (ExternalAgentActor(client_id="mcp"), "agent"),
        (SystemActor(), "system"),
        (EvaluatorActor(name="judge", version="1"), "system"),
    ],
)
def test_actors_are_people_agents_or_the_system(actor: Actor, role: str) -> None:
    assert actor_role(actor) == role


async def test_drop_off_is_measured_from_each_threads_activity(ws: Workspace, clock: Clock) -> None:
    replied, proposed, ignored, recent = [await ws.create_thread(t) for t in "abcd"]
    await ws.post_message(replied.id, "Draft a note")
    clock.at(1)
    await agent_in(ws, replied.id).post_message(replied.id, "Drafted.")
    clock.at(5)
    await ws.post_message(replied.id, "Thanks")
    await ws.post_message(proposed.id, "Plan it")
    clock.at(6)
    plan = create_artifact(Checklist(title="Launch"), thread_id=proposed.id)
    assert isinstance(await agent_in(ws, proposed.id).commit(plan), Proposed)
    await ws.post_message(ignored.id, "Summarize")
    await agent_in(ws, ignored.id).post_message(ignored.id, "Summary: ship it.")
    clock.at(50)
    await ws.post_message(recent.id, "Anything new?")
    await agent_in(ws, recent.id).post_message(recent.id, "Nothing yet.")
    await ws.commit(create_artifact(Note(text="No thread")))  # outside any thread: no session
    sessions = await thread_sessions(ws)
    assert [s.id for s in sessions] == [replied.id, proposed.id, ignored.id, recent.id]
    [created, asked, drafted, thanked] = sessions[0].activities
    assert (created.kind, asked.kind, drafted.role, thanked.at) == (
        "thread_created",
        "message",
        "agent",
        START + timedelta(minutes=5),
    )
    [plan_proposed] = [a for a in sessions[1].activities if a.kind == "proposal"]
    assert (plan_proposed.role, plan_proposed.ref) == ("agent", plan.proposal_id)
    now = START + timedelta(minutes=60)
    measured = [measure_drop_off(session, window=WINDOW, now=now) for session in sessions]
    assert [(m.outcome, m.cause) for m in measured] == [
        ("continued", None),
        ("dropped", "unresolved_proposal"),
        ("dropped", "no_reply"),
        ("pending", None),
    ]


async def test_a_resolution_pairs_with_its_proposal(ws: Workspace, clock: Clock) -> None:
    thread = await ws.create_thread("Plan")
    proposal = await agent_in(ws, thread.id).commit(
        create_artifact(Checklist(title="Launch"), thread_id=thread.id)
    )
    assert isinstance(proposal, Proposed)
    clock.at(10)
    await ws.commit(RespondToProposal(proposal_id=proposal.proposal_id, decision="reject"))
    [session] = await thread_sessions(ws)
    [resolution] = [a for a in session.activities if a.kind == "resolution"]
    assert (resolution.role, resolution.ref) == ("person", proposal.proposal_id)
    measured = measure_drop_off(session, window=WINDOW, now=START + timedelta(hours=2))
    assert measured.outcome == "continued"


def title_or_text(artifact: Artifact) -> str:
    return artifact.title if isinstance(artifact, Checklist) else artifact.render_for_agent()


async def test_rewrites_count_what_people_changed_of_what_the_agent_wrote(
    ws: Workspace, clock: Clock
) -> None:
    thread = await ws.create_thread("Launch")
    agent = agent_in(ws, thread.id)
    # A note the agent wrote, and a person rewrote.
    rewritten = await agent.commit(
        create_artifact(Note(text="Ship on Monday, after the review"), thread_id=thread.id)
    )
    assert isinstance(rewritten, Applied)
    clock.at(5)
    note = await ws.get(Note, rewritten.artifact_id)
    await ws.commit(note.edit_text("Ship on Monday, after the review", "Hold the launch"))
    # A note the agent wrote, and a person touched up.
    kept = await agent.commit(
        create_artifact(Note(text="Tell the team on Friday"), thread_id=thread.id)
    )
    assert isinstance(kept, Applied)
    clock.at(8)
    touched = await ws.get(Note, kept.artifact_id)
    await ws.commit(touched.edit_text("Friday", "Friday."))
    # A plan the agent proposed, which a person accepted as it was, then rewrote on accepting
    # the agent's next change, and archived.
    created = await agent.commit(
        create_artifact(Checklist(title="Launch plan"), thread_id=thread.id)
    )
    assert isinstance(created, Proposed)
    clock.at(10)
    await ws.commit(RespondToProposal(proposal_id=created.proposal_id, decision="accept"))
    [plan] = await ws.artifacts(Checklist)
    edited = await agent.commit(plan.edit(lambda p: setattr(p, "title", "Launch plan, v2")))
    assert isinstance(edited, Proposed)
    clock.at(12)
    mine = JsonPatch(ops=({"op": "replace", "path": "/title", "value": "Our own schedule"},))
    await ws.commit(
        RespondToProposal(proposal_id=edited.proposal_id, decision="accept", changes=mine)
    )
    plan = await ws.get(Checklist, plan.id)
    await ws.commit(plan.archive())
    # A proposal to create, rewritten as it was accepted.
    retitled = await agent.commit(create_artifact(Checklist(title="Retro"), thread_id=thread.id))
    assert isinstance(retitled, Proposed)
    clock.at(20)
    ours = JsonPatch(ops=({"op": "replace", "path": "/title", "value": "Postmortem notes"},))
    await ws.commit(
        RespondToProposal(proposal_id=retitled.proposal_id, decision="accept", changes=ours)
    )

    histories = await artifact_histories(ws, text=title_or_text)

    def at(minutes: int) -> datetime:
        return START + timedelta(minutes=minutes)

    assert [h.revisions for h in histories] == [
        [
            Revision(at=at(0), role="agent", text="Ship on Monday, after the review"),
            Revision(at=at(5), role="person", text="Hold the launch"),
        ],
        [
            Revision(at=at(5), role="agent", text="Tell the team on Friday"),
            Revision(at=at(8), role="person", text="Tell the team on Friday."),
        ],
        [
            Revision(at=at(10), role="agent", text="Launch plan"),
            Revision(at=at(12), role="agent", text="Launch plan, v2"),
            Revision(at=at(12), role="person", text="Our own schedule"),
        ],
        [
            Revision(at=at(20), role="agent", text="Retro"),
            Revision(at=at(20), role="person", text="Postmortem notes"),
        ],
    ]
    measured = [measure_rewrites(h, window=WINDOW) for h in histories]
    assert [(m.agent_revisions, m.rewritten) for m in measured] == [(1, 1), (1, 0), (2, 1), (1, 1)]
    evaluator = rewrite_evaluator(window=WINDOW)
    assert rewrite_rate([await evaluator.evaluate(h) for h in histories]) == 3 / 5
    # By default, an artifact's text is what the agent sees of it.
    [first, *_] = await artifact_histories(ws)
    assert first.revisions[-1].text == "Hold the launch"


async def test_drop_off_rate_over_a_workspace(ws: Workspace, clock: Clock) -> None:
    thread = await ws.create_thread("Launch")
    await ws.post_message(thread.id, "Hi")
    await agent_in(ws, thread.id).post_message(thread.id, "Hello")
    evaluator = drop_off_evaluator(window=WINDOW, now=START + timedelta(hours=1))
    verdicts = [await evaluator.evaluate(session) for session in await thread_sessions(ws)]
    assert drop_off_rate(verdicts) == 1.0


async def test_task_completion_is_judged_over_the_transcript_and_final_artifacts(
    ws: Workspace, clock: Clock
) -> None:
    thread = await ws.create_thread("Launch")
    agent = agent_in(ws, thread.id)
    await ws.post_message(thread.id, "Draft a launch note")
    note = await agent.commit(create_artifact(Note(text="Ship Monday"), thread_id=thread.id))
    assert isinstance(note, Applied)
    await ws.commit(SetFocus(thread_id=thread.id, artifact_ids=(note.artifact_id,)))
    await agent.post_message(thread.id, "Drafted.")
    await ws.commit(
        GiveFeedback(
            feedback_type="task_completion",
            target=ThreadTarget(thread_id=thread.id),
            value={"completed": True, "quality": 4},
        )
    )
    context = await target_context(ws, ThreadTarget(thread_id=thread.id))
    assert completion_transcript(context) == Transcript(
        request="Draft a launch note",
        turns=[
            Turn(role="person", text="Draft a launch note"),
            Turn(role="agent", text="Drafted."),
        ],
        result=f'<artifact id="{note.artifact_id}" kind="note" version="1">\n'
        "Ship Monday\n</artifact>",
    )
    source = LogFeedbackSource(
        ws, feedback_type=TaskCompletion, input_type=Transcript, input=completion_transcript
    )
    [example] = [e async for e in source.examples()]
    assert example.input == completion_transcript(context)

    def completed(transcript: Transcript) -> TaskCompletion:
        return TaskCompletion(completed=transcript.result is not None, quality=3)

    judge = FunctionEvaluator(completed, verdict_type=TaskCompletion)
    assert completion_rate([await judge.evaluate(example.input)]) == 1.0
    assert TaskCompletion.feedback_type == "task_completion"


async def test_a_thread_without_people_or_artifacts_has_an_empty_request(ws: Workspace) -> None:
    thread = await ws.create_thread("Quiet")
    await agent_in(ws, thread.id).post_message(thread.id, "Hello?")
    transcript = completion_transcript(await target_context(ws, ThreadTarget(thread_id=thread.id)))
    assert (transcript.request, transcript.result) == ("", None)
