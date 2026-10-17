"""The checked-in wire schema matches the models."""

import io
import json
import runpy
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from artifactr.ui.wire import wire_schema

SCHEMA = Path(__file__).parents[2] / "schemas" / "artifactr_ui.v1.json"


def test_the_checked_in_schema_is_current() -> None:
    assert json.loads(SCHEMA.read_text()) == wire_schema(), "run `moon run artifactr:schema`"


def test_the_schema_holds_every_kind_and_ask_forms_request() -> None:
    assert set(wire_schema()["properties"]) == {
        "form",
        "submission",
        "dashboard",
        "app",
        "ask_form",
        "refusal_reason",
        "integration_key",
    }


# Running an already-imported module as __main__ is exactly what this test means to do.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_schema() -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        runpy.run_module("artifactr.ui.wire", run_name="__main__")
    assert json.loads(output.getvalue()) == wire_schema()
