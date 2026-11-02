"""artifactr's commands (lattice RFC-0014, artifactr ADR-0100): a static catalog in which every
action is some command's gate, or is listed with its reason."""

import io
import json
import runpy
from contextlib import redirect_stdout
from pathlib import Path
from typing import get_args

import pytest
from pydantic import TypeAdapter

from artifactr.capabilities import NAMES as PROVIDED
from artifactr.commands import ARGUMENTS, CATALOG, LISTED
from artifactr.commands.arguments import FeedbackTarget, ModeArguments
from artifactr.commands.schema import catalog_document
from artifactr.core import ArtifactTarget, MessageTarget, ThreadMode, ThreadTarget, TurnTarget
from artifactr.core import FeedbackTarget as CoreTarget
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


def test_listing_the_workspaces_alone_is_tenant_wide() -> None:
    tenant_wide = {name for name, command in COMMANDS.items() if command.tenant_wide}
    assert tenant_wide == {"artifactr.list_workspaces"}, "a client finds a workspace with it"


def test_each_commands_arguments_are_the_models_its_input_schema_is() -> None:
    assert list(ARGUMENTS) == list(COMMANDS)
    for name, command in COMMANDS.items():
        schema = ARGUMENTS[name].model_json_schema()
        del schema["title"]
        assert command.capability.input_schema == schema, name


@pytest.mark.parametrize(
    "target",
    [
        ArtifactTarget(artifact_id="art_1", version=2),
        ThreadTarget(thread_id="thr_1"),
        TurnTarget(run_id="run_1"),
        MessageTarget(message_id="msg_1", thread_id="thr_1", run_id="run_1"),
    ],
)
def test_feedbacks_targets_are_cores_as_a_call_names_them(target: CoreTarget) -> None:
    named = TypeAdapter(FeedbackTarget).validate_python(target.model_dump())
    assert TypeAdapter(CoreTarget).validate_python(named.model_dump()) == target


def test_a_threads_modes_are_cores() -> None:
    assert get_args(ModeArguments.model_fields["mode"].annotation) == get_args(ThreadMode)


def test_the_committed_catalog_is_current() -> None:
    assert json.loads(DOCUMENT.read_text()) == catalog_document(), "run `moon run artifactr:schema`"


# Running an already-imported module as __main__ is exactly what this test means to do.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_catalog() -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        runpy.run_module("artifactr.commands.schema", run_name="__main__")
    assert json.loads(output.getvalue()) == catalog_document()
