"""portalr's commands (lattice RFC-0014, portalr ADR-0094): its admin's reads, each of its actions
a gate, and creating a tenant and inviting a member, gated as portalr's routes gate them."""

import ast
import io
import json
import runpy
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from lattice_core.commands import catalog
from portalr.actions import ACTIONS
from portalr.commands import ADD_MEMBER, CATALOG, CREATE_TENANT, LISTED
from portalr.commands.schema import catalog_document
from portalr.readers.tempo import TraceQuery

COMMANDS = {command.name: command for command in CATALOG.commands()}
DOCUMENT = Path(__file__).parent.parent / "schemas" / "portalr.commands.json"
COMMANDS_SOURCE = Path(__file__).parent.parent / "src" / "portalr" / "commands"
ROUTER = Path(__file__).parent.parent / "src" / "portalr" / "fastapi" / "router.py"


def test_every_command_is_portalrs_and_every_portalr_action_a_gate() -> None:
    assert all(name.startswith("portalr.") for name in COMMANDS)
    gates = {c.capability.gate.action for c in COMMANDS.values()}
    assert gates == ACTIONS | {CREATE_TENANT, ADD_MEMBER}
    assert list(catalog(CATALOG)) == list(COMMANDS), "no two share a name or a tool name"
    assert not LISTED


def test_the_grantr_actions_are_the_ones_portalrs_routes_ask() -> None:
    asked = ROUTER.read_text()
    assert f'"{CREATE_TENANT}"' in asked
    assert f'"{ADD_MEMBER}"' in asked


def test_each_is_an_admin_tool_and_what_emails_someone_sends_out() -> None:
    assert {c.toolset for c in COMMANDS.values()} == {"admin"}
    assert all(c.exposure == "tool" for c in COMMANDS.values())
    writes = {n for n, c in COMMANDS.items() if c.capability.tier == "write"}
    assert writes == {"portalr.create_tenant", "portalr.invite_member"}
    assert all(COMMANDS[n].capability.effects == {"sends_out"} for n in writes)
    reads = set(COMMANDS) - writes
    assert all(COMMANDS[n].capability.effects == {"reads_private"} for n in reads)


def test_every_one_is_tenant_wide() -> None:
    assert all(command.tenant_wide for command in COMMANDS.values())


def test_a_reads_arguments_are_its_routes_query() -> None:
    schema = json.loads(json.dumps(COMMANDS["portalr.list_traces"].capability.input_schema))
    assert schema["properties"] == TraceQuery.model_json_schema()["properties"]


def test_the_catalog_knows_no_web_framework() -> None:
    for path in COMMANDS_SOURCE.rglob("*.py"):
        tree = ast.parse(path.read_text())
        imported = {
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        assert not {m for m in imported if m.split(".")[0] in ("fastapi", "starlette", "httpx")}


def test_the_committed_catalog_is_current() -> None:
    assert json.loads(DOCUMENT.read_text()) == catalog_document(), "run `moon run portalr:schema`"


# Running an already-imported module as __main__ is exactly what this test means to do.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_catalog() -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        runpy.run_module("portalr.commands.schema", run_name="__main__")
    assert json.loads(output.getvalue()) == catalog_document()
