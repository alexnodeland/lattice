"""The committed vectors, which portalr's TypeScript tests read too, hold for the Python side."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from artifactr.core import ValidationFailed
from artifactr.ui.ids import submission_id
from artifactr.ui.schema import (
    MAX_CHOICES,
    MAX_LENGTH,
    MAX_NUMBER,
    MAX_PROPERTIES,
    MAX_SCHEMA_BYTES,
    MAX_VALUES_BYTES,
    FormSchema,
)
from tests.ui.refusals import locs

VECTORS = Path(__file__).parent / "vectors"
FORMS = json.loads((VECTORS / "forms.json").read_text())
IDS = json.loads((VECTORS / "submission_ids.json").read_text())

ACCEPTED = [
    (form["name"], form["schema"], values) for form in FORMS["forms"] for values in form["accepted"]
]
REFUSED = [
    (form["name"], form["schema"], case) for form in FORMS["forms"] for case in form["refused"]
]


@pytest.mark.parametrize(("name", "schema", "values"), ACCEPTED)
def test_a_form_accepts_its_accepted_values(name: str, schema: dict[str, Any], values: Any) -> None:
    assert FormSchema.model_validate(schema).validate_values(values) == values


@pytest.mark.parametrize(("name", "schema", "case"), REFUSED)
def test_a_form_refuses_its_refused_values_at_the_field(
    name: str, schema: dict[str, Any], case: dict[str, Any]
) -> None:
    with pytest.raises(ValidationFailed) as refused:
        FormSchema.model_validate(schema).validate_values(case["values"])
    assert case["loc"] in locs(refused.value)


@pytest.mark.parametrize("case", FORMS["refused_schemas"], ids=lambda case: case["names"])
def test_a_refused_schema_names_what_it_refuses(case: dict[str, Any]) -> None:
    with pytest.raises(ValidationError) as refused:
        FormSchema.model_validate(case["schema"])
    errors = refused.value.errors(include_url=False)
    assert any(list(error["loc"]) == case["loc"] for error in errors), errors
    assert case["names"] in str(refused.value)


def test_the_limits_are_the_modules() -> None:
    assert FORMS["limits"] == {
        "measure": FORMS["limits"]["measure"],
        "max_properties": MAX_PROPERTIES,
        "max_choices": MAX_CHOICES,
        "max_length": MAX_LENGTH,
        "max_schema_bytes": MAX_SCHEMA_BYTES,
        "max_values_bytes": MAX_VALUES_BYTES,
        "max_number": MAX_NUMBER,
        "property_name": FORMS["limits"]["property_name"],
    }


@pytest.mark.parametrize("case", IDS["cases"], ids=lambda case: case["id"])
def test_a_submission_id_is_its_vectors(case: dict[str, str]) -> None:
    derived = submission_id(
        case["form_id"], principal=case.get("principal"), nonce=case.get("nonce")
    )
    assert derived == case["id"]
