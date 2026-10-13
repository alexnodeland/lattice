"""The checked-in rule schema matches the models."""

import json
import runpy
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

import pytest
from jsonschema import Draft202012Validator

from reflexr.core import (
    SYSTEM_EVENTS,
    Event,
    EventFrame,
    FeedbackGiven,
    RuleArchived,
    RuleErrored,
    RuleFired,
    RuleInstalled,
    RuleReset,
    RunCancelled,
    RunDeadLettered,
    RunProgressed,
    RunRequeued,
    RunRetrying,
    RunSkipped,
    RunStarted,
    RunSucceeded,
    RunTarget,
    SystemActor,
    SystemEvent,
    Tick,
    UnknownEvent,
)
from reflexr.core.schema import (
    PROTOCOL_SCHEMA_ID,
    RULES_SCHEMA_ID,
    main,
    protocol_schema,
    rules_schema,
)
from tests.event_types import ServiceError

SCHEMAS = Path(__file__).parent.parent.parent / "schemas"


def test_the_checked_in_schemas_are_current() -> None:
    rules = json.loads((SCHEMAS / "reflexr.rules.v1.json").read_text())
    assert rules == rules_schema(), "run `make schema`"
    protocol = json.loads((SCHEMAS / "reflexr.v1.json").read_text())
    assert protocol == protocol_schema(), "run `make schema`"
    assert (rules["$id"], protocol["$id"]) == (RULES_SCHEMA_ID, PROTOCOL_SCHEMA_ID)
    assert set(protocol["properties"]) == {"client", "server"}


def test_either_schema_can_be_printed(capsys: pytest.CaptureFixture[str]) -> None:
    main(["protocol"])
    assert json.loads(capsys.readouterr().out) == protocol_schema()
    main(["rules"])
    assert json.loads(capsys.readouterr().out) == rules_schema()


@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_schema(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["schema"])
    sys.modules.pop("reflexr.core.schema", None)
    runpy.run_module("reflexr.core.schema", run_name="__main__")
    assert json.loads(capsys.readouterr().out) == rules_schema()


OWN = [*get_args(SystemEvent), FeedbackGiven, Tick]


def test_the_protocol_names_reflexrs_own_events_and_leaves_the_rest_open() -> None:
    defs = protocol_schema()["$defs"]
    assert defs["EventFrame"]["properties"]["event"]["$ref"] == "#/$defs/_LoggedEvent"
    assert defs["_LoggedEvent"]["title"] == "LoggedEvent"
    named = [variant["$ref"].removeprefix("#/$defs/") for variant in defs["_LoggedEvent"]["anyOf"]]
    assert named == [event.__name__ for event in OWN] + ["_OtherEvent"]
    assert {event.event_type for event in OWN} == {event.event_type for event in SYSTEM_EVENTS}
    for event in OWN:
        wire = defs[event.__name__]
        assert wire["properties"]["type"] == {"const": event.event_type}
        assert "type" in wire["required"]
        assert "additionalProperties" not in wire, "open to the fields a newer version adds"
    other = defs["_OtherEvent"]
    assert (other["title"], other["additionalProperties"]) == ("OtherEvent", True)
    assert other["properties"]["type"]["not"] == {
        "enum": sorted(event.event_type for event in OWN)
    }, "an application's event matches no event of reflexr's"


def test_an_event_types_own_schema_has_no_type() -> None:
    for event in (RunStarted, ServiceError):
        schema = event.model_json_schema()
        assert "type" not in schema["properties"], "a model validates an event's fields alone"
        assert schema["additionalProperties"] is False


def _frame(event: Event) -> dict[str, Any]:
    envelope = EventFrame(
        seq=1,
        id="evt_1",
        ts=AT,
        workspace_id="prod",
        actor=SystemActor(),
        correlation_id="evt_1",
        event=event,
    )
    return envelope.model_dump(mode="json")


AT = datetime(2026, 10, 13, tzinfo=UTC)
EXAMPLES: list[Event] = [
    RuleFired(rule="app:r", scope={}, scope_key="k", firing_id="fir_1", matched=(1,)),
    RuleErrored(rule="app:r", seq=1, error="boom"),
    RuleReset(rule="app:r", generation=1, reason="changed", from_seq=1),
    RuleInstalled(rule="chat:r", version=1, spec={}, provenance={}),
    RuleArchived(rule="chat:r", version=2, cancelled=0),
    RunStarted(run_id="fir_1", rule="app:r", scope_key="k", attempt=1),
    RunProgressed(run_id="fir_1", rule="app:r", step="plan"),
    RunRetrying(run_id="fir_1", rule="app:r", attempt=1, error="boom", next_attempt_at=AT),
    RunSucceeded(run_id="fir_1", rule="app:r"),
    RunDeadLettered(run_id="fir_1", rule="app:r", attempts=3, error="boom"),
    RunCancelled(run_id="fir_1", rule="app:r"),
    RunRequeued(run_id="fir_1", rule="app:r"),
    RunSkipped(run_id="fir_1", rule="app:r"),
    FeedbackGiven(feedback_type="useful", target=RunTarget(run_id="fir_1"), value={}),
    Tick(schedule="clock", at=AT),
    ServiceError(service="auth"),
    UnknownEvent.model_validate({"unknown_type": "reflexr:new_thing", "detail": 1}),
]


def test_every_kind_of_event_on_the_wire_matches_the_schema() -> None:
    assert {type(e) for e in EXAMPLES} >= set(SYSTEM_EVENTS), "one of each of reflexr's own"
    frames = Draft202012Validator(
        {"$defs": protocol_schema()["$defs"], "$ref": "#/$defs/EventFrame"}
    )
    for event in EXAMPLES:
        frames.validate(_frame(event))
    newer = _frame(RunSucceeded(run_id="fir_1", rule="app:r"))
    newer["event"]["duration_ms"] = 12  # a field a newer version of reflexr adds
    frames.validate(newer)
    wrong = _frame(RunSucceeded(run_id="fir_1", rule="app:r"))
    del wrong["event"]["run_id"]
    assert not frames.is_valid(wrong), "a reflexr event is checked against its own schema"
