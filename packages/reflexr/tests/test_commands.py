"""reflexr's commands (lattice RFC-0014, reflexr ADR-0067): a static catalog in which every action
is some command's gate, or is listed with its reason, named as reflexr's own MCP tools."""

import io
import json
import runpy
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from lattice_core.commands import catalog
from reflexr.commands import CATALOG, LISTED
from reflexr.commands.schema import catalog_document
from reflexr.core import Rule
from reflexr.workspace import ACTIONS

COMMANDS = {command.name: command for command in CATALOG.commands()}
DOCUMENT = Path(__file__).parent.parent / "schemas" / "reflexr.commands.json"


def test_every_command_is_reflexrs_and_gated_by_one_of_its_actions() -> None:
    assert all(name.startswith("reflexr.") for name in COMMANDS)
    assert {c.capability.gate.action for c in COMMANDS.values()} <= ACTIONS
    assert list(catalog(CATALOG)) == list(COMMANDS), "no two share a name or a tool name"


def test_every_action_is_a_commands_gate_or_listed_with_its_reason() -> None:
    gates = {c.capability.gate.action for c in COMMANDS.values()}
    assert gates | set(LISTED) == ACTIONS
    assert not gates & set(LISTED), "an action listed is no command's gate"
    assert all(LISTED.values())


def test_the_commands_are_the_tools_reflexrs_own_server_serves() -> None:
    served = {
        "publish_event",
        "read_events",
        "list_rules",
        "rule_status",
        "get_rule",
        "rule_history",
        "schedule_status",
        "replay_rule",
        "install_rule",
        "update_rule",
        "archive_rule",
        "list_runs",
        "get_run",
        "retry_run",
        "skip_run",
        "cancel_run",
        "list_dead_letters",
        "give_feedback",
    }
    assert set(COMMANDS) == {f"reflexr.{name}" for name in served}


def test_each_is_an_automation_but_feedback_and_every_surface_offers_it() -> None:
    toolsets = {name: command.toolset for name, command in COMMANDS.items()}
    assert toolsets.pop("reflexr.give_feedback") == "feedback"
    assert set(toolsets.values()) == {"automations"}
    assert all(c.exposure != "resource" and len(c.surfaces) == 4 for c in COMMANDS.values())


def test_reads_read_and_what_runs_actions_again_is_irreversible() -> None:
    reads = {n for n, c in COMMANDS.items() if c.capability.tier == "read"}
    assert all(COMMANDS[n].capability.gate.action.startswith("reflexr:read_") for n in reads)
    assert all(COMMANDS[n].capability.reversibility == "none" for n in reads)
    irreversible = {n for n, c in COMMANDS.items() if c.capability.reversibility == "irreversible"}
    assert {"reflexr.replay_rule", "reflexr.retry_run", "reflexr.publish_event"} <= irreversible


def test_a_run_is_a_resource_too_by_the_uri_reflexr_serves() -> None:
    resources = {n: c.resource for n, c in COMMANDS.items() if c.resource}
    assert resources == {"reflexr.get_run": "reflexr://{tenant}/{workspace}/runs/{run_id}"}
    assert COMMANDS["reflexr.get_run"].exposure == "both"


def test_a_rule_to_install_is_described_by_reflexrs_rule_schema() -> None:
    schema = json.loads(json.dumps(COMMANDS["reflexr.install_rule"].capability.input_schema))
    assert schema["required"] == ["rule"]
    assert schema["$defs"]["Rule"]["properties"] == Rule.model_json_schema()["properties"]


def test_the_committed_catalog_is_current() -> None:
    assert json.loads(DOCUMENT.read_text()) == catalog_document(), "run `moon run reflexr:schema`"


# Running an already-imported module as __main__ is exactly what this test means to do.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_catalog() -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        runpy.run_module("reflexr.commands.schema", run_name="__main__")
    assert json.loads(output.getvalue()) == catalog_document()
