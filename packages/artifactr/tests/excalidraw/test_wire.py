"""The checked-in wire schema matches the models."""

import io
import json
import runpy
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from artifactr.excalidraw.wire import wire_schema

SCHEMA = Path(__file__).parents[2] / "schemas" / "artifactr_excalidraw.v1.json"


def test_the_checked_in_schema_is_current() -> None:
    assert json.loads(SCHEMA.read_text()) == wire_schema(), "run `moon run artifactr:schema`"


def test_the_schema_names_excalidraws_own_fields() -> None:
    element = wire_schema()["$defs"]["Element"]
    assert {"versionNonce", "isDeleted"} <= set(element["properties"])
    assert element["additionalProperties"] is True


# Running an already-imported module as __main__ is exactly what this test means to do.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_schema() -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        runpy.run_module("artifactr.excalidraw.wire", run_name="__main__")
    assert json.loads(output.getvalue()) == wire_schema()
