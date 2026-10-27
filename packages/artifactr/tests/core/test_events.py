"""Events: the closed union, forward compatibility, and envelopes."""

from datetime import UTC, datetime
from typing import get_args

from pydantic import TypeAdapter

from artifactr.core import (
    WORKSPACE_SCOPED,
    AppEvent,
    ArtifactChanged,
    DeferredAnswered,
    Envelope,
    Event,
    KnownEvent,
    MessagePosted,
    RunEnded,
    RunStarted,
    RunUsage,
    StepUsage,
    TextEdit,
    TextEdits,
    ThreadCreated,
    UnknownEvent,
    UserActor,
    scope_of,
)

EVENTS = TypeAdapter[Event](Event)


def test_known_events_validate_to_their_class() -> None:
    event = EVENTS.validate_python({"type": "thread_created", "thread_id": "t1", "title": "x"})
    assert event == ThreadCreated(thread_id="t1", title="x")


def test_model_instances_pass_through_the_discriminator() -> None:
    event = MessagePosted(thread_id="t1", message_id="m1", content="hi")
    assert EVENTS.validate_python(event) == event


def test_unknown_event_types_round_trip() -> None:
    raw = {"type": "artifact_forked", "artifact_id": "a1", "into": "a2"}
    event = EVENTS.validate_python(raw)
    assert isinstance(event, UnknownEvent)
    assert event.type == "artifact_forked"
    assert EVENTS.dump_python(event) == raw


def test_an_answer_recorded_before_it_named_its_tool_reads_without_one() -> None:
    raw = {"type": "deferred_answered", "run_id": "r1", "thread_id": "t1", "tool_call_id": "c1"}
    event = EVENTS.validate_python(raw)
    assert isinstance(event, DeferredAnswered)
    assert event.tool_name is None


def test_messages_and_starts_recorded_before_models_were_chosen_read_without_one() -> None:
    posted = EVENTS.validate_json(
        '{"type": "message_posted", "thread_id": "t1", "message_id": "m1", "content": "hi"}'
    )
    started = EVENTS.validate_json('{"type": "run_started", "run_id": "r1", "thread_id": "t1"}')
    assert isinstance(posted, MessagePosted)
    assert isinstance(started, RunStarted)
    assert (posted.model, started.model) == (None, None)
    chosen = started.model_copy(update={"model": "fast"})
    assert EVENTS.validate_json(EVENTS.dump_json(chosen)) == chosen


def test_usage_recorded_before_steps_were_counted_reads_as_none() -> None:
    raw = {
        "type": "run_ended",
        "run_id": "r1",
        "thread_id": "t1",
        "status": "completed",
        "usage": {"requests": 2, "input_tokens": 30, "output_tokens": 4},
    }
    event = EVENTS.validate_python(raw)
    assert isinstance(event, RunEnded)
    assert event.usage is not None
    assert event.usage == RunUsage(requests=2, input_tokens=30, output_tokens=4)
    assert (event.usage.steps, event.usage.model) == ((), None)


def test_usage_with_its_steps_round_trips() -> None:
    step = StepUsage(
        model="glm-4.7",
        input_tokens=30,
        output_tokens=4,
        cache_read_tokens=20,
        cache_write_tokens=5,
        reasoning_tokens=2,
        duration_ms=812,
    )
    usage = RunUsage(requests=1, input_tokens=30, output_tokens=4, model="glm-4.7", steps=(step,))
    event = RunEnded(run_id="r1", thread_id="t1", status="stopped", usage=usage)
    assert EVENTS.validate_json(EVENTS.dump_json(event)) == event


def test_values_without_a_string_type_are_unknown() -> None:
    assert EVENTS.validate_python({"type": "x"}) == UnknownEvent(type="x")
    assert isinstance(EVENTS.validate_python(UnknownEvent(type="y")), UnknownEvent)


def test_scope_comes_from_the_event() -> None:
    patch = TextEdits(edits=(TextEdit(old="a", new="b"),))
    changed = ArtifactChanged(
        artifact_id="a1", kind="note", version=2, patch=patch, summary="s", thread_id="t1"
    )
    assert scope_of(changed) == ("t1", None)
    assert scope_of(RunEnded(run_id="r1", thread_id="t1", status="completed")) == ("t1", "r1")
    assert scope_of(AppEvent(name="exported")) == (None, None)


def test_artifact_and_proposal_events_are_workspace_scoped() -> None:
    kinds = {member.model_fields["type"].default for member in get_args(KnownEvent)}
    scoped = {kind for kind in kinds if kind.startswith(("artifact_", "proposal_"))}
    assert scoped == WORKSPACE_SCOPED


def test_envelopes_are_the_wire_shape() -> None:
    envelope = Envelope(
        seq=7,
        id="e7",
        ts=datetime(2026, 9, 28, tzinfo=UTC),
        workspace_id="w1",
        thread_id="t1",
        actor=UserActor(id="alice"),
        event=MessagePosted(thread_id="t1", message_id="m1", content="hi"),
    )
    wire = envelope.model_dump(mode="json")
    assert wire["event"]["type"] == "message_posted"
    assert Envelope.model_validate(wire) == envelope
