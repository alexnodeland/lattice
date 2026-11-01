"""The parity test: every action a person takes is a command, and every surface offers it.

lattice RFC-0014's parity test (#916, lattice ADR-0042), here since it spans packages. It composes
every library's catalog, grantr's catalog of every library's actions and every OpenAPI document
the libraries publish, and fails on each gap:

- **An operation calls no command:** each operation of every ``schemas/*.openapi.json`` says what
  it calls in ``x-lattice-command``: a command of the catalogs, the member of its body that
  carries command frames, each frame's ``type`` naming some command's action, or why it calls
  none.
- **A command has no tool:** each is a tool, a resource or both, or says why it is none.
- **A command is in no toolset.**
- **A tool has no grantr check:** each command's gate is an action of grantr's catalog.
- **A grantr action has no command:** each action is some command's gate, or is listed by its
  library with a reason (claiming threads, keeping cursors, a run's own steps).
- **portalr's client sends a command no surface of portalr's offers:** each name in
  ``commands.used.json``, the commands its UIs' requests name (portalr ADR-0096), is a command of
  the catalogs offered on ``portalr``.

Each gap has a fixture that fails it, run through the same checks. portr's generated tools follow
(#917).
"""

import json
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from artifactr.commands import CATALOG as ARTIFACTR
from artifactr.commands import LISTED as ARTIFACTR_LISTED
from artifactr.workspace import ACTIONS as ARTIFACTR_ACTIONS
from grantr.commands import CATALOG as GRANTR
from grantr.core import Catalog
from lattice_core.commands import (
    EXTENSION,
    TOOLSETS,
    Command,
    Frames,
    NoCommand,
    NotExposed,
    called,
    catalog,
)
from portalr.actions import ACTIONS as PORTALR_ACTIONS
from portalr.commands import CATALOG as PORTALR
from portalr.commands import LISTED as PORTALR_LISTED
from reflexr.commands import CATALOG as REFLEXR
from reflexr.commands import LISTED as REFLEXR_LISTED
from reflexr.workspace import ACTIONS as REFLEXR_ACTIONS
from relayr.commands import CATALOG as RELAYR
from relayr.commands import LISTED as RELAYR_LISTED

ROOT = Path(__file__).parent.parent
USED = ROOT / "packages/portalr/web/client/commands.used.json"
METHODS = ("get", "put", "post", "delete", "patch", "head", "options")

type Document = Mapping[str, Any]


@dataclass(frozen=True)
class Composed:
    """Everything the parity test holds to each other."""

    commands: Mapping[str, Command]
    """Every catalog's commands, by name."""
    actions: frozenset[str]
    """grantr's catalog of every library's actions, and its own."""
    listed: Mapping[str, str]
    """Each action no command gates, and why, as its library lists it."""
    documents: Mapping[str, Document]
    """Every OpenAPI document the libraries publish, by its file's name."""
    used: frozenset[str]
    """The commands portalr's UIs send over REST, as ``commands.used.json`` lists them."""


def composed() -> Composed:
    """lattice as it is: the catalogs, the actions and the documents in the repository."""
    listed = {**ARTIFACTR_LISTED, **REFLEXR_LISTED, **RELAYR_LISTED, **PORTALR_LISTED}
    documents = {
        path.name: json.loads(path.read_text())
        for path in sorted(ROOT.glob("packages/*/schemas/*.openapi.json"))
    }
    return Composed(
        commands=catalog(ARTIFACTR, GRANTR, REFLEXR, RELAYR, PORTALR),
        actions=Catalog.of(ARTIFACTR_ACTIONS, REFLEXR_ACTIONS, PORTALR_ACTIONS).actions,
        listed=MappingProxyType(listed),
        documents=MappingProxyType(documents),
        used=frozenset(json.loads(USED.read_text())),
    )


def _resolved(document: Document, node: Any) -> Any:
    while isinstance(node, dict) and "$ref" in node:
        ref: str = node["$ref"]
        node = document
        for part in ref.removeprefix("#/").split("/"):
            node = node[part]
    return node


def _frame_types(document: Document, operation: Document, member: str) -> list[str] | None:
    """The ``type`` of each frame the body's ``member`` may be, or None if it is no frame."""
    content = operation.get("requestBody", {}).get("content", {}).get("application/json", {})
    body = _resolved(document, content.get("schema"))
    union = _resolved(document, (body or {}).get("properties", {}).get(member))
    mapping = (union or {}).get("discriminator", {}).get("mapping")
    return sorted(mapping) if mapping else None


def _operations(document: Document) -> Iterator[tuple[str, Document]]:
    for path, item in document["paths"].items():
        for method in METHODS:
            if method in item:
                yield f"{method.upper()} {path}", item[method]


def operation_gaps(world: Composed) -> Iterator[str]:
    """Each operation that says nothing of what it calls, or names what doesn't exist."""
    gates = {c.capability.gate.action for c in world.commands.values()}
    for name, document in world.documents.items():
        package = name.split(".")[0].split("-")[0]
        for where, operation in _operations(document):
            try:
                says = called(operation.get(EXTENSION))
            except ValueError:
                yield f"{name}: {where} says nothing readable of what it calls"
                continue
            if isinstance(says, NoCommand):
                continue
            if isinstance(says, Frames):
                types = _frame_types(document, operation, says.frames)
                if types is None:
                    yield f"{name}: {where} carries frames in {says.frames}, which is no frame"
                for kind in sorted(set(says.none) - set(types or ())):
                    yield f"{name}: {where} says why {kind} asks nothing, but carries no {kind}"
                for kind in types or ():
                    if kind not in says.none and f"{package}:{kind}" not in gates:
                        yield f"{name}: {where} carries {kind}, which is no command's action"
                continue
            for command in says:
                if command not in world.commands:
                    yield f"{name}: {where} calls {command}, which no catalog declares"


def command_gaps(world: Composed) -> Iterator[str]:
    """Each command no surface reaches without a reason, in no toolset, or gated by no action."""
    for name, command in world.commands.items():
        exposure = command.exposure
        if isinstance(exposure, NotExposed) and not exposure.reason:
            yield f"{name} is neither a tool nor a resource, and says no reason"
        elif not isinstance(exposure, NotExposed) and exposure not in ("tool", "resource", "both"):
            yield f"{name} is exposed as {exposure!r}, which no surface offers"
        if command.toolset not in TOOLSETS:
            yield f"{name} is in no toolset"
        if command.capability.gate.action not in world.actions:
            action = command.capability.gate.action
            yield f"{name} is gated by {action}, which grantr's catalog lacks"


def action_gaps(world: Composed) -> Iterator[str]:
    """Each action that is no command's gate and isn't listed, or is listed for no reason."""
    gates = {c.capability.gate.action: n for n, c in world.commands.items()}
    for action in sorted(world.actions):
        if action not in gates and not world.listed.get(action):
            yield f"{action} is no command's gate, and isn't listed with a reason"
    for action in sorted(world.listed):
        if action in gates:
            yield f"{action} is listed, but gates {gates[action]}"
        elif action not in world.actions:
            yield f"{action} is listed, but is no action"


def client_gaps(world: Composed) -> Iterator[str]:
    """Each command portalr's client sends that no catalog declares, or portalr doesn't offer."""
    for name in sorted(world.used):
        command = world.commands.get(name)
        if command is None:
            yield f"portalr's client sends {name}, which no catalog declares"
        elif "portalr" not in command.surfaces:
            yield f"portalr's client sends {name}, which isn't offered on portalr"


def gaps(world: Composed) -> list[str]:
    """Every gap in ``world``."""
    return [
        *operation_gaps(world),
        *command_gaps(world),
        *action_gaps(world),
        *client_gaps(world),
    ]


WORLD = composed()


def test_lattice_has_no_gap() -> None:
    assert gaps(WORLD) == []


def test_every_document_and_every_catalog_is_read() -> None:
    assert len(WORLD.documents) >= 7, "artifactr's three, grantr's, portalr's, reflexr's, relayr's"
    packages = {name.partition(".")[0] for name in WORLD.commands}
    assert packages == {"artifactr", "grantr", "reflexr", "relayr", "portalr"}
    assert "grantr.revoke_key" in WORLD.used, "portalr's client's requests are read"


def _changed(document: str, where: str, change: Callable[[dict[str, Any]], None]) -> Composed:
    documents = json.loads(json.dumps(dict(WORLD.documents)))
    method, _, path = where.partition(" ")
    change(documents[document]["paths"][path][method.lower()])
    return replace(WORLD, documents=MappingProxyType(documents))


def _without(command: str) -> Composed:
    return replace(
        WORLD, commands=MappingProxyType({n: c for n, c in WORLD.commands.items() if n != command})
    )


def _with(command: str, **changes: Any) -> Composed:
    changed = WORLD.commands[command].model_construct(
        **{**dict(WORLD.commands[command]), **changes}
    )
    return replace(WORLD, commands=MappingProxyType({**WORLD.commands, command: changed}))


def _gate(command: str, action: str) -> Composed:
    found = WORLD.commands[command]
    gate = found.capability.gate.model_construct(integration=None, action=action)
    capability = found.capability.model_construct(**{**dict(found.capability), "gate": gate})
    return _with(command, capability=capability)


MEMBERS = "GET /grantr/v1/tenants/{tenant}/members"
COMMANDS = "POST /workspaces/{workspace_id}/commands"


@pytest.mark.parametrize(
    ("world", "gap"),
    [
        pytest.param(
            _changed("grantr.openapi.json", MEMBERS, lambda o: o.pop(EXTENSION)),
            f"grantr.openapi.json: {MEMBERS} says nothing readable of what it calls",
            id="an operation without its extension",
        ),
        pytest.param(
            _changed("grantr.openapi.json", MEMBERS, lambda o: o.update({EXTENSION: {"none": ""}})),
            f"grantr.openapi.json: {MEMBERS} says nothing readable of what it calls",
            id="an operation that calls none, for no reason",
        ),
        pytest.param(
            _changed(
                "grantr.openapi.json", MEMBERS, lambda o: o.update({EXTENSION: "grantr.members"})
            ),
            f"grantr.openapi.json: {MEMBERS} calls grantr.members, which no catalog declares",
            id="an operation that names no command",
        ),
        pytest.param(
            _changed(
                "artifactr.openapi.json", COMMANDS, lambda o: o.update({EXTENSION: {"frames": "x"}})
            ),
            f"artifactr.openapi.json: {COMMANDS} carries frames in x, which is no frame",
            id="frames in a member that is none",
        ),
        pytest.param(
            _changed(
                "artifactr.openapi.json",
                COMMANDS,
                lambda o: o[EXTENSION]["none"].pop("watch_run"),
            ),
            f"artifactr.openapi.json: {COMMANDS} carries watch_run, which is no command's action",
            id="a frame that asks no action, for no reason",
        ),
        pytest.param(
            _changed(
                "reflexr.openapi.json",
                COMMANDS,
                lambda o: o[EXTENSION]["none"].update({"dance": "why"}),
            ),
            f"reflexr.openapi.json: {COMMANDS} says why dance asks nothing, but carries no dance",
            id="a reason for a frame the body hasn't",
        ),
        pytest.param(
            _without("artifactr.post_message"),
            "artifactr:post_message is no command's gate, and isn't listed with a reason",
            id="an action without its command",
        ),
        pytest.param(
            _without("reflexr.publish_event"),
            f"reflexr.openapi.json: {COMMANDS} carries publish, which is no command's action",
            id="a frame whose action is no command's",
        ),
        pytest.param(
            _with("grantr.issue_key", exposure=NotExposed.model_construct(reason="")),
            "grantr.issue_key is neither a tool nor a resource, and says no reason",
            id="a command that is no tool, for no reason",
        ),
        pytest.param(
            _with("grantr.list_keys", exposure="prompt"),
            "grantr.list_keys is exposed as 'prompt', which no surface offers",
            id="a command exposed as nothing a surface offers",
        ),
        pytest.param(
            _with("grantr.list_keys", toolset="everything"),
            "grantr.list_keys is in no toolset",
            id="a command in no toolset",
        ),
        pytest.param(
            _gate("grantr.list_keys", "grantr:read_keys"),
            "grantr.list_keys is gated by grantr:read_keys, which grantr's catalog lacks",
            id="a tool without its grantr check",
        ),
        pytest.param(
            replace(WORLD, listed=MappingProxyType({**WORLD.listed, "artifactr:open": ""})),
            "artifactr:open is no command's gate, and isn't listed with a reason",
            id="an action listed for no reason",
        ),
        pytest.param(
            replace(WORLD, listed=MappingProxyType({**WORLD.listed, "grantr:grant": "why"})),
            "grantr:grant is listed, but gates grantr.grant_on_tenant",
            id="an action listed though a command's gate",
        ),
        pytest.param(
            replace(WORLD, listed=MappingProxyType({**WORLD.listed, "grantr:dance": "why"})),
            "grantr:dance is listed, but is no action",
            id="a listed action that is none",
        ),
        pytest.param(
            replace(WORLD, used=WORLD.used | {"grantr.dance"}),
            "portalr's client sends grantr.dance, which no catalog declares",
            id="the client sending a command that is none",
        ),
        pytest.param(
            _with("grantr.revoke_key", surfaces=frozenset({"mcp"})),
            "portalr's client sends grantr.revoke_key, which isn't offered on portalr",
            id="the client sending a command portalr doesn't offer",
        ),
    ],
)
def test_each_gap_is_found(world: Composed, gap: str) -> None:
    assert gap in gaps(world)
