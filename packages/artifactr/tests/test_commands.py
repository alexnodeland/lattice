"""artifactr's commands (lattice RFC-0014, artifactr ADR-0100): a static catalog in which every
action is some command's gate, or is listed with its reason."""

import io
import json
import runpy
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from artifactr.capabilities import NAMES as PROVIDED
from artifactr.commands import CATALOG, LISTED
from artifactr.commands.schema import catalog_document
from artifactr.workspace import ACTIONS
from lattice_core.commands import NotExposed, catalog

COMMANDS = {command.name: command for command in CATALOG.commands()}
DOCUMENT = Path(__file__).parent.parent / "schemas" / "artifactr.commands.json"


def test_every_command_is_artifactrs_and_gated_by_one_of_its_actions() -> None:
    assert all(name.startswith("artifactr.") for name in COMMANDS)
    assert {c.capability.gate.action for c in COMMANDS.values()} <= ACTIONS
    assert list(catalog(CATALOG)) == list(COMMANDS), "no two share a name or a tool name"


def test_every_action_is_a_commands_gate_or_listed_with_its_reason() -> None:
    gates = {c.capability.gate.action for c in COMMANDS.values()}
    assert gates | set(LISTED) == ACTIONS
    assert not gates & set(LISTED), "an action listed is no command's gate"
    assert all(LISTED.values())


def test_answering_a_deferred_call_and_the_focus_are_portalrs_alone() -> None:
    hidden = {n for n, c in COMMANDS.items() if isinstance(c.exposure, NotExposed)}
    assert hidden == {"artifactr.answer_deferred", "artifactr.set_focus"}
    assert all(COMMANDS[n].surfaces == {"portalr"} for n in hidden)


def test_a_thread_and_an_artifact_are_resources_too() -> None:
    resources = {n: c.resource for n, c in COMMANDS.items() if c.resource}
    assert resources == {
        "artifactr.read_thread": "artifactr://{tenant}/{workspace}/threads/{thread_id}",
        "artifactr.read_artifact": "artifactr://{tenant}/{workspace}/artifacts/{artifact_id}",
    }


def test_the_providers_tools_are_commands_of_their_names() -> None:
    assert set(PROVIDED) <= set(COMMANDS)
    assert all(COMMANDS[name].capability.provider == "command" for name in PROVIDED)


def test_the_committed_catalog_is_current() -> None:
    assert json.loads(DOCUMENT.read_text()) == catalog_document(), "run `moon run artifactr:schema`"


# Running an already-imported module as __main__ is exactly what this test means to do.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_catalog() -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        runpy.run_module("artifactr.commands.schema", run_name="__main__")
    assert json.loads(output.getvalue()) == catalog_document()
