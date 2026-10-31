"""The checked-in contracts' JSON Schemas match their models (lattice RFC-0011)."""

import io
import json
import runpy
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from lattice_core.capabilities import CONTRACT
from lattice_core.contracts import SCHEMAS, main

CHECKED_IN = Path(__file__).parent.parent / "schemas"


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_each_checked_in_schema_is_current(name: str) -> None:
    (path,) = CHECKED_IN.glob(f"{name}.v*.json")
    assert json.loads(path.read_text()) == SCHEMAS[name](), "run `moon run lattice-core:schema`"


def test_every_checked_in_schema_is_a_contracts() -> None:
    assert {path.name.split(".")[0] for path in CHECKED_IN.glob("*.json")} == set(SCHEMAS)


def test_a_schema_is_named_by_its_contracts_major_version() -> None:
    assert (CHECKED_IN / f"capabilities.v{CONTRACT.split('.')[0]}.json").is_file()
    assert SCHEMAS["capabilities"]()["title"] == f"lattice.capabilities {CONTRACT}"


@pytest.mark.parametrize("argv", [[], ["taint"], ["capabilities", "approvals"], ["bindings"]])
def test_main_needs_one_contract_it_knows(argv: list[str]) -> None:
    with pytest.raises(SystemExit, match="usage"):
        main(argv)


# Running an already-imported module as __main__ is exactly what this test means to do.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_schema_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["lattice_core.contracts", "capabilities"])
    output = io.StringIO()
    with redirect_stdout(output):
        runpy.run_module("lattice_core.contracts", run_name="__main__")
    assert json.loads(output.getvalue()) == SCHEMAS["capabilities"]()
