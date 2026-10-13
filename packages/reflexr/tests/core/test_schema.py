"""The checked-in rule schema matches the models."""

import json
import runpy
import sys
from pathlib import Path

import pytest

from reflexr.core import SYSTEM_EVENTS, UnknownEvent
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


def test_the_protocol_names_reflexrs_own_events_and_leaves_the_rest_open() -> None:
    defs = protocol_schema()["$defs"]
    assert defs["EventFrame"]["properties"]["event"]["$ref"] == "#/$defs/LoggedEvent"
    named = [variant["$ref"].removeprefix("#/$defs/") for variant in defs["LoggedEvent"]["anyOf"]]
    assert named == [event.__name__ for event in SYSTEM_EVENTS] + ["OtherEvent"]
    for event in SYSTEM_EVENTS:
        schema = defs[event.__name__]
        assert schema["properties"]["type"] == {"const": event.event_type}
        assert (next(iter(schema["properties"])), schema["required"][0]) == ("type", "type")
    other = defs["OtherEvent"]
    assert other["additionalProperties"] is True
    assert other["properties"]["type"]["not"] == {
        "enum": sorted(event.event_type for event in SYSTEM_EVENTS)
    }, "an application's event matches no event of reflexr's"


def test_an_event_types_schema_names_its_type_and_an_abstract_ones_none() -> None:
    assert ServiceError.model_json_schema()["properties"]["type"] == {"const": "app:service.error"}
    assert "type" not in UnknownEvent.model_json_schema()["properties"]
