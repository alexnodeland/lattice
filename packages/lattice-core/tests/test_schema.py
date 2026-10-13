"""tag_required: a union member's tag is required in its JSON Schema."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue

from lattice_core.schema import tag_required


class Tagged(BaseModel):
    model_config = ConfigDict(json_schema_extra=tag_required)

    type: Literal["tagged"] = "tagged"
    note: str = ""
    count: int


class Untagged(BaseModel):
    model_config = ConfigDict(json_schema_extra=tag_required)

    note: str = ""


def test_a_field_fixed_to_one_value_is_required_beside_the_others() -> None:
    assert Tagged.model_json_schema()["required"] == ["count", "type"]


def test_a_model_without_a_tag_requires_nothing_more() -> None:
    assert Untagged.model_json_schema()["required"] == []


def test_a_tag_already_required_is_listed_once() -> None:
    schema: dict[str, JsonValue] = {"properties": {"kind": {"const": "a"}}, "required": ["kind"]}
    tag_required(schema)
    assert schema["required"] == ["kind"]
