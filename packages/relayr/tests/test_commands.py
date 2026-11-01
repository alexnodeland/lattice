"""relayr's commands (lattice RFC-0014, relayr ADR-0042): the tracker connector's two reads, each
gated by the reflexr action relayr's route asks."""

import io
import json
import runpy
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from lattice_core.commands import catalog
from reflexr.workspace import ACTIONS
from relayr.commands import CATALOG, LISTED
from relayr.commands.schema import catalog_document
from relayr.fastapi.reads import READ_FILED, READ_FOLLOWING

COMMANDS = {command.name: command for command in CATALOG.commands()}
DOCUMENT = Path(__file__).parent.parent / "schemas" / "relayr.commands.json"


def test_each_read_is_gated_by_the_reflexr_action_its_route_asks() -> None:
    gates = {name: c.capability.gate.action for name, c in COMMANDS.items()}
    assert gates == {"relayr.list_filed_items": READ_FILED, "relayr.tracker_status": READ_FOLLOWING}
    assert set(gates.values()) <= ACTIONS
    assert list(catalog(CATALOG)) == list(COMMANDS), "no two share a name or a tool name"
    assert not LISTED, "relayr asks no action of its own"


def test_both_are_reads_of_the_runs_page_in_automations() -> None:
    for command in COMMANDS.values():
        assert (command.capability.tier, command.toolset) == ("read", "automations")
        assert command.capability.input_schema == {
            "additionalProperties": False,
            "properties": {},
            "type": "object",
        }
        assert command.route == "/portalr/app/t/{tenant}/w/{workspace}/runs"


def test_each_is_called_in_a_workspace() -> None:
    assert not any(command.tenant_wide for command in COMMANDS.values())


def test_the_committed_catalog_is_current() -> None:
    assert json.loads(DOCUMENT.read_text()) == catalog_document(), "run `moon run relayr:schema`"


# Running an already-imported module as __main__ is exactly what this test means to do.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_catalog() -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        runpy.run_module("relayr.commands.schema", run_name="__main__")
    assert json.loads(output.getvalue()) == catalog_document()
