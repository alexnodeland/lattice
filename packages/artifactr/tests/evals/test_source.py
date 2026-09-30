"""Datasets from the log: feedback as evalr examples, with the context of what it is about."""

from collections.abc import Collection

from pydantic import JsonValue

from artifactr.core import (
    ArtifactTarget,
    EvaluatorActor,
    ExternalAgentActor,
    GiveFeedback,
    MessagePosted,
    MessageTarget,
    TargetKind,
    ThreadTarget,
    TurnTarget,
    UserActor,
)
from artifactr.evals import FeedbackContext, LogFeedbackSource, TargetContext, target_context
from artifactr.workspace import Workspace
from evalr.contracts import check_feedback_source
from evalr.core import collect
from tests.artifact_types import Accuracy, Helpfulness, Note
from tests.evals.conftest import Said, chat, said
from tests.telemetry.conftest import Recorder

BOB = UserActor(id="bob", name="Bob")
JUDGE = EvaluatorActor(name="judge", version="1")


def build(context: TargetContext) -> Said:
    return Said(
        said=said(context.transcript),
        followed=[a.data.render_for_agent() for a in context.artifacts],
    )


async def rate(
    workspace: Workspace, target: TurnTarget | ThreadTarget | MessageTarget, rating: int
) -> None:
    value: dict[str, JsonValue] = {"rating": rating}
    await workspace.commit(GiveFeedback(feedback_type="helpfulness", target=target, value=value))


async def test_each_piece_of_feedback_is_an_example_of_what_it_is_about(
    traced: Workspace, recorder: Recorder
) -> None:
    done = await chat(traced, recorder)
    drafted = TurnTarget(run_id=done.drafted.id)
    await rate(traced.as_actor(BOB), drafted, 2)  # earlier feedback on the same turn
    await rate(traced, drafted, 4)
    await rate(traced, ThreadTarget(thread_id=done.thread.id), 5)
    source = LogFeedbackSource(traced, feedback_type=Helpfulness, input_type=Said, input=build)
    assert (source.input_type, source.verdict_type) == (Said, Helpfulness)
    first, second, whole = [example async for example in source.examples()]
    log = await traced.read()
    # A turn is judged as it ended: later messages, and feedback, are not part of it.
    assert (
        first.input
        == second.input
        == Said(said=["user: Draft a launch note", "agent: Drafted."], followed=["Ship Monday"])
    )
    assert first.verdict == Helpfulness(rating=2)
    assert first.trace_id == done.drafted.trace_ids[-1]
    assert first.id == next(
        e.id for e in log if e.seq == 1 + max(e.seq for e in log if e.run_id == done.answered.id)
    )
    assert second.metadata == {
        "tenant_id": "t",
        "workspace_id": "w",
        "thread_id": done.thread.id,
        "target": "turn",
        "given_by": "user:alice",
        "seq": log[-2].seq,
    }
    # A thread is judged as it was when the feedback was given.
    assert whole.input.said == [
        "user: Draft a launch note",
        "agent: Drafted.",
        "user: Thanks, anything else?",
        "agent: No, that's all.",
    ]
    assert (whole.verdict, whole.trace_id) == (Helpfulness(rating=5), None)


async def test_the_context_of_a_turn_is_its_run_up_to_its_end(
    traced: Workspace, recorder: Recorder
) -> None:
    done = await chat(traced, recorder)
    await rate(traced, TurnTarget(run_id=done.drafted.id), 4)
    contexts: list[FeedbackContext[Helpfulness]] = []

    def keep(context: FeedbackContext[Helpfulness]) -> Said:
        contexts.append(context)
        return build(context)

    source = LogFeedbackSource(traced, feedback_type=Helpfulness, input_type=Said, input=keep)
    [example] = [example async for example in source.examples()]
    [context] = contexts
    assert context.envelope.id == example.id
    assert context.feedback == Helpfulness(rating=4)
    assert context.thread == await traced.thread(done.thread.id)
    assert [e.event.type for e in context.events] == [
        "run_started",
        "tool_called",
        "artifact_created",
        "tool_returned",
        "message_posted",
        "run_ended",
    ]
    assert context.seq == context.events[-1].seq
    assert (context.revision, context.artifact) == (None, None)
    [note] = context.artifacts
    assert (note.version, note.data) == (1, Note(text="Ship Monday"))


async def test_a_message_is_judged_as_it_was_posted(traced: Workspace, recorder: Recorder) -> None:
    done = await chat(traced, recorder)
    [reply] = [
        e
        for e in await traced.read()
        if isinstance(e.event, MessagePosted) and e.event.content == "Drafted."
    ]
    assert isinstance(reply.event, MessagePosted)
    target = MessageTarget(
        message_id=reply.event.message_id, thread_id=done.thread.id, run_id=done.drafted.id
    )
    await rate(traced, target, 3)
    context = await target_context(traced, target)
    assert context.seq == reply.seq
    assert context.events[-1] == reply
    assert context.trace_id == done.drafted.trace_ids[-1]
    assert said(context.transcript) == ["user: Draft a launch note", "agent: Drafted."]


async def test_a_transcript_leaves_notices_out(traced: Workspace, recorder: Recorder) -> None:
    done = await chat(traced, recorder)
    rule = traced.as_actor(ExternalAgentActor(client_id="reflexr:timeline-entry"))
    await rule.post_message(done.thread.id, "The rule is live", kind="notice")
    context = await target_context(traced, ThreadTarget(thread_id=done.thread.id))
    assert said(context.transcript) == [
        "user: Draft a launch note",
        "agent: Drafted.",
        "user: Thanks, anything else?",
        "agent: No, that's all.",
    ], "a rule's notice would read as the agent's turn"


async def test_an_artifact_version_is_judged_with_its_revision_and_its_run(
    traced: Workspace, recorder: Recorder
) -> None:
    done = await chat(traced, recorder)
    [note] = await traced.artifacts(Note)
    await traced.commit(note.edit_text("Monday", "Tuesday"))  # outside any thread
    for version in (1, 2):
        target = ArtifactTarget(artifact_id=note.id, version=version)
        await traced.commit(
            GiveFeedback(feedback_type="accuracy", target=target, value={"correct": version == 2})
        )
    contexts: list[FeedbackContext[Accuracy]] = []

    def keep(context: FeedbackContext[Accuracy]) -> Said:
        contexts.append(context)
        return build(context)

    source = LogFeedbackSource(traced, feedback_type=Accuracy, input_type=Said, input=keep)
    by_agent, by_alice = [example async for example in source.examples()]
    first, second = contexts
    assert first.revision is not None
    assert first.artifact is not None
    assert (first.artifact.version, first.artifact.data) == (1, Note(text="Ship Monday"))
    assert by_agent.trace_id == first.revision.trace_id == done.drafted.trace_ids[-1]
    assert first.thread is not None
    assert first.events[-1].event.type == "artifact_created"
    assert by_agent.input.said == ["user: Draft a launch note"]
    assert second.artifact is not None
    assert second.artifact.data == Note(text="Ship Tuesday")
    assert (second.thread, second.transcript, second.events) == (None, (), ())
    assert by_alice.verdict == Accuracy(correct=True)


async def test_other_types_targets_and_evaluators_verdicts_are_left_out(
    traced: Workspace, recorder: Recorder
) -> None:
    done = await chat(traced, recorder)
    drafted = TurnTarget(run_id=done.drafted.id)
    await rate(traced, drafted, 4)
    await rate(traced, ThreadTarget(thread_id=done.thread.id), 5)
    await rate(traced.as_actor(JUDGE), drafted, 1)
    mcp = traced.as_actor(ExternalAgentActor(client_id="mcp"))
    await rate(mcp, drafted, 3)
    [note] = await traced.artifacts(Note)
    await traced.commit(
        GiveFeedback(
            feedback_type="accuracy",
            target=ArtifactTarget(artifact_id=note.id, version=1),
            value={"correct": True},
        )
    )

    async def ratings(
        targets: Collection[TargetKind] | None = None, *, include_evaluators: bool = False
    ) -> list[tuple[object, int]]:
        source = LogFeedbackSource(
            traced,
            feedback_type=Helpfulness,
            input_type=Said,
            input=build,
            targets=targets,
            include_evaluators=include_evaluators,
        )
        return [
            (example.metadata["given_by"], example.verdict.rating)
            async for example in source.examples()
            if example.verdict
        ]

    assert await ratings() == [("user:alice", 4), ("user:alice", 5), ("external_agent:mcp", 3)]
    assert await ratings({"thread"}) == [("user:alice", 5)]
    assert await ratings({"turn"}, include_evaluators=True) == [
        ("user:alice", 4),
        ("evaluator:judge@1", 1),
        ("external_agent:mcp", 3),
    ]


async def test_builders_may_be_async(traced: Workspace, recorder: Recorder) -> None:
    done = await chat(traced, recorder)
    await rate(traced, TurnTarget(run_id=done.answered.id), 4)

    async def reread(context: FeedbackContext[Helpfulness]) -> Said:
        run = await context.workspace.run(done.answered.id)
        return Said(said=[run.status, *said(context.transcript)])

    source = LogFeedbackSource(traced, feedback_type=Helpfulness, input_type=Said, input=reread)
    [example] = [example async for example in source.examples()]
    assert example.input.said[0] == "completed"
    assert len(example.input.said) == 5


async def test_the_source_meets_evalrs_contract(traced: Workspace, recorder: Recorder) -> None:
    done = await chat(traced, recorder)
    await rate(traced, TurnTarget(run_id=done.drafted.id), 4)
    await rate(traced, ThreadTarget(thread_id=done.thread.id), 2)
    source = LogFeedbackSource(traced, feedback_type=Helpfulness, input_type=Said, input=build)
    await check_feedback_source(source)
    dataset = await collect("helpfulness", source)
    assert [example.verdict for example in dataset] == [
        Helpfulness(rating=4),
        Helpfulness(rating=2),
    ]
