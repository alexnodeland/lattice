"""The schema subset's refusals, limits and hints, case by case."""

from typing import Any

import pytest
from pydantic import ValidationError

from artifactr.core import ValidationFailed
from artifactr.ui._common import json_size
from artifactr.ui.schema import (
    MAX_NUMBER,
    MAX_VALUES_BYTES,
    ChoiceProperty,
    FormSchema,
    StringProperty,
    UiHints,
)


def _schema(**properties: Any) -> FormSchema:
    return FormSchema.model_validate({"properties": properties})


def _refused(schema: dict[str, Any]) -> str:
    with pytest.raises(ValidationError) as refused:
        FormSchema.model_validate(schema)
    return str(refused.value)


def test_the_size_is_the_utf8_bytes_of_compact_json() -> None:
    assert json_size({"a": [1, "é"]}) == len('{"a":[1,"é"]}'.encode())
    assert json_size({"a": [1, "é"]}) == 14, "é is two bytes"


@pytest.mark.parametrize(
    ("format", "good", "bad"),
    [
        ("date", ["2026-10-17"], ["2026-13-01", "2026-10-17T00:00:00Z", "17/10/2026"]),
        (
            "date-time",
            ["2026-10-17T23:59:59-05:00", "2026-10-17t23:59:59z"],
            ["2026-02-30T00:00:00Z", "2026-10-17T24:00:00Z"],
        ),
        (
            "email",
            ["alice@example.com"],
            ["a@b", "a b@example.com", f"{'a' * 60}@{'b' * 200}.com"],
        ),
        (
            "uri",
            ["https://example.com", "HTTP://a.b", "mailto:a@b.c"],
            ["example.com", "https://a b", "javascript:alert(1)", "ftp://a.b", "data:,x"],
        ),
    ],
)
def test_each_format_has_its_check(format: str, good: list[str], bad: list[str]) -> None:
    schema = _schema(x={"type": "string", "format": format})
    for text in good:
        assert schema.validate_values({"x": text})
    for text in bad:
        with pytest.raises(ValidationFailed, match=f"valid {format}"):
            schema.validate_values({"x": text})


def test_a_string_is_at_most_ten_thousand_characters_whatever_its_max_length() -> None:
    schema = _schema(note={"type": "string"})
    assert schema.validate_values({"note": "a" * 10_000})
    with pytest.raises(ValidationFailed):
        schema.validate_values({"note": "a" * 10_001})


def test_values_over_the_limit_are_refused_whole() -> None:
    schema = _schema(**{f"p{i}": {"type": "string"} for i in range(8)})
    values: dict[str, Any] = {f"p{i}": "a" * 9_000 for i in range(8)}
    assert json_size(values) > MAX_VALUES_BYTES
    with pytest.raises(ValidationFailed) as refused:
        schema.validate_values(values)
    assert refused.value.errors == [{"type": "too_long", "loc": [], "msg": refused.value.message}]


@pytest.mark.parametrize(
    ("of", "value", "taken"),
    [(1e-300, 2.0**53 - 1, False), (1e10, 3.5, False), (1e10, 0, True), (0.1, 0.3, True)],
)
def test_a_multiple_is_checked_without_overflowing(of: float, value: float, taken: bool) -> None:
    schema = _schema(x={"type": "number", "multipleOf": of})
    if taken:
        assert schema.validate_values({"x": value})
    else:
        with pytest.raises(ValidationFailed, match="multiple of"):
            schema.validate_values({"x": value})


@pytest.mark.parametrize("number", [10**400, -(2**53), 2**53, 2.0**53, 1e300])
def test_every_number_is_within_two_to_the_fifty_three(number: float) -> None:
    assert "within ±(2**53 - 1)" in _refused(
        {"properties": {"x": {"type": "number", "minimum": number}}}
    )
    schema = _schema(n={"type": "integer"}, x={"type": "number"})
    for name in ("n", "x"):
        with pytest.raises(ValidationFailed, match=r"within ±\(2\*\*53 - 1\)"):
            schema.validate_values({name: number})
    assert schema.validate_values({"n": MAX_NUMBER, "x": -MAX_NUMBER})


def test_more_than_fifty_properties_are_refused() -> None:
    message = _refused({"properties": {f"p{i}": {"type": "boolean"} for i in range(51)}})
    assert "at most 50" in message


def test_more_than_sixty_four_choices_are_refused() -> None:
    assert "at most 64" in _refused({"properties": {"x": {"enum": [str(i) for i in range(65)]}}})


@pytest.mark.parametrize(
    ("schema", "named"),
    [
        (
            {"properties": {"x": {"enum": ["a"], "oneOf": [{"const": "a", "title": "A"}]}}},
            "one of the two",
        ),
        ({"properties": {"x": {"type": "array", "items": {}}}}, "one of the two"),
        ({"properties": {"x": {"type": "string", "oneOf": [{"const": "a"}]}}}, "title"),
        ({"properties": {"x": {"type": "boolean"}}, "required": ["x", "x"]}, "each property once"),
        ({"properties": {"x": {"type": "number", "multipleOf": 0}}}, "greater than 0"),
        ({"properties": {"x": {"type": "number", "minimum": True}}}, "Input should be a number"),
        ({"properties": {"x": {"type": "number", "maximum": "3"}}}, "Input should be a number"),
        ({"properties": {"x": {"type": "integer", "default": 1.5}}}, "the default"),
        (
            {"properties": {"x": {"type": "string", "format": "email", "default": "a"}}},
            "the default",
        ),
        ({"properties": {"x": {"type": "boolean", "default": "true"}}}, "boolean"),
        ({"properties": {"x": {"type": ["string", "null"]}}}, "Each property is"),
        ({"properties": {"x": "a string"}}, "Each property is"),
        ({"properties": {"": {"type": "boolean"}}}, "property's name"),
        ({"type": "array"}, "'object'"),
        ({"properties": {"x": {"oneOf": ["a"]}}}, "valid dictionary"),
        ({"properties": {"x": {"type": "string", "minLength": 3, "maxLength": 2}}}, "minLength"),
        ({"properties": {"x": {"type": "number", "minimum": 3, "maximum": 2}}}, "no number"),
        (
            {"properties": {"x": {"type": "number", "minimum": 2, "exclusiveMaximum": 2}}},
            "no number",
        ),
        (
            {"properties": {"x": {"type": "number", "exclusiveMinimum": 2, "maximum": 2}}},
            "no number",
        ),
        (
            {
                "properties": {
                    "x": {"type": "array", "items": {"enum": ["a"]}, "minItems": 2, "maxItems": 1}
                }
            },
            "minItems is more than maxItems",
        ),
        (
            {
                "properties": {
                    "x": {
                        "type": "array",
                        "items": {"enum": ["a"]},
                        "uniqueItems": True,
                        "minItems": 2,
                    }
                }
            },
            "more than the choices",
        ),
        ({"properties": {"1x": {"type": "boolean"}}}, "property's name"),
        ({"properties": {"a b": {"type": "boolean"}}}, "property's name"),
        ({"properties": {"__proto__": {"type": "boolean"}}}, "property's name"),
        ({"properties": {"constructor": {"type": "boolean"}}}, "property's name"),
        ({"properties": {"x" * 65: {"type": "boolean"}}}, "property's name"),
        ({"properties": {"x": {"type": "string", "properties": {}}}}, "nested objects"),
    ],
)
def test_what_the_subset_refuses_is_named(schema: dict[str, Any], named: str) -> None:
    assert named in _refused(schema)


def test_a_schema_built_in_python_tells_its_properties_apart() -> None:
    string = StringProperty.model_validate({"type": "string"})
    choice = ChoiceProperty.model_validate({"enum": ["a"]})
    schema = FormSchema.model_validate({"properties": {"s": string, "c": choice}})
    assert schema.validate_values({"s": "x", "c": "a"}) == {"s": "x", "c": "a"}


def test_a_schema_is_written_back_as_json_schema() -> None:
    schema = _schema(n={"type": "integer", "minimum": 1}, c={"enum": ["a"]})
    assert schema.model_dump(mode="json") == {
        "type": "object",
        "properties": {
            "n": {"type": "integer", "minimum": 1},
            "c": {"type": "string", "enum": ["a"]},
        },
        "required": [],
        "additionalProperties": False,
    }


def test_choices_offer_their_values_in_order() -> None:
    labelled = ChoiceProperty.model_validate(
        {"oneOf": [{"const": "b", "title": "B"}, {"const": "a", "title": "A"}]}
    )
    assert labelled.offered == ["b", "a"]


# ─── hints ────────────────────────────────────────────────────────────────────

SCHEMA = _schema(
    note={"type": "string"},
    level={"enum": ["low", "high"]},
    paged={"type": "boolean"},
    count={"type": "integer"},
)


def test_hints_that_name_the_schemas_properties_and_fit_them_pass() -> None:
    hints = UiHints.model_validate(
        {
            "fields": {
                "note": {"widget": "textarea", "placeholder": "What happened", "help": "Briefly"},
                "level": {"widget": "select"},
                "paged": {"widget": "checkbox"},
                "count": {"help": "How many"},
            },
            "order": ["level", "note"],
            "sections": [{"title": "More", "properties": ["paged", "count"]}],
            "submit_label": "Report",
        }
    )
    hints.check(SCHEMA)
    assert hints.model_dump(mode="json")["fields"]["level"] == {"widget": "select"}


@pytest.mark.parametrize(
    ("hints", "message"),
    [
        ({"fields": {"nope": {}}}, "ui names nope, not a property"),
        ({"order": ["note", "gone"]}, "ui names gone"),
        ({"order": ["note", "note"]}, "order names a property twice"),
        (
            {
                "sections": [
                    {"title": "A", "properties": ["note"]},
                    {"title": "B", "properties": ["note"]},
                ]
            },
            "sections names",
        ),
        ({"sections": [{"title": "S", "properties": ["x"]}]}, "ui names x"),
        ({"fields": {"note": {"widget": "select"}}}, "ui gives note a select, which a string"),
        ({"fields": {"count": {"widget": "textarea"}}}, "which a number can't take"),
    ],
)
def test_hints_that_name_another_property_or_do_not_fit_are_refused(
    hints: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        UiHints.model_validate(hints).check(SCHEMA)


@pytest.mark.parametrize(
    "hint", [{"colour": "red"}, {"class": "big"}, {"html": "<b>"}, {"url": "x"}]
)
def test_a_hint_carries_no_colour_class_html_or_url(hint: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        UiHints.model_validate({"fields": {"note": hint}})
    with pytest.raises(ValidationError):
        UiHints.model_validate(hint)
