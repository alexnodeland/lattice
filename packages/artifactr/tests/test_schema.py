"""The checked-in protocol schema matches the frame models."""

import io
import json
import runpy
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from artifactr.core.schema import protocol_schema

SCHEMA = Path(__file__).parent.parent / "schemas" / "artifactr.v1.json"


def test_the_checked_in_schema_is_current() -> None:
    assert json.loads(SCHEMA.read_text()) == protocol_schema(), "run `make schema`"


# Running an already-imported module as __main__ is exactly what this test means to do.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_schema() -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        runpy.run_module("artifactr.core.schema", run_name="__main__")
    assert json.loads(output.getvalue()) == protocol_schema()
