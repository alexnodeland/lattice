"""Events: the closed union, forward compatibility, and envelopes."""

from datetime import UTC, datetime

from pydantic import TypeAdapter

from artifactr.core import (
    AppEvent,
    ArtifactChanged,
    Envelope,
    Event,
    MessagePosted,
    RunEnded,
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
