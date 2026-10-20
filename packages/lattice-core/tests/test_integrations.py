"""The registry of integrations, its keys, and the answer without a store."""

from typing import cast

import pytest

from lattice_core.integrations import KEY, KNOWN, Defaults, Integration, Integrations, registry


def test_lattices_integrations_are_declared_once_each() -> None:
    assert list(KNOWN) == [
        "tracker:plane",
        "tracker:vikunja",
        "files:wordcraft",
        "files:gridcraft",
        "files:deckcraft",
        "files:pdfcraft",
        "files:cadcraft",
        "files:photocraft",
        "files:vectorcraft",
        "files:designcraft",
        "files:figcraft",
        "files:freecad",
        "files:filmcraft",
        "files:effectcraft",
        "files:soundcraft",
        "files:lightcraft",
        "ui:forms",
        "ui:dashboards",
        "ui:mini-apps",
        "excalidraw",
        "markdown:math",
        "markdown:mermaid",
    ]
    assert all(key == integration.key for key, integration in KNOWN.items())


def test_mini_apps_mermaid_and_every_crafting_app_but_wordcraft_are_off_by_default() -> None:
    crafts = {key for key in KNOWN if key.startswith("files:")} - {"files:wordcraft"}
    assert {key for key, integration in KNOWN.items() if not integration.default} == {
        "ui:mini-apps",
        "markdown:mermaid",
        *crafts,
    }
    assert len(crafts) == 13


@pytest.mark.parametrize("key", ["excalidraw", "ui:mini-apps", "files:word-craft2", "a:b"])
def test_a_key_is_a_name_or_a_family_and_a_name(key: str) -> None:
    assert KEY.fullmatch(key)
    assert Integration(key, default=True, description="It.").key == key


@pytest.mark.parametrize("key", ["", "Plane", "tracker:", ":plane", "a:b:c", "a b", "2fa", "a_b"])
def test_a_malformed_key_is_refused(key: str) -> None:
    with pytest.raises(ValueError, match="an integration key"):
        Integration(key, default=True, description="It.")


def test_an_integration_says_what_it_is() -> None:
    with pytest.raises(ValueError, match="needs a description"):
        Integration("excalidraw", default=True, description="  ")


def test_an_application_adds_its_own_with_one_declaration() -> None:
    mine = Integration("crm:hubspot", default=False, description="HubSpot: deals as artifacts.")
    known = registry(*KNOWN.values(), mine)
    assert known["crm:hubspot"] is mine
    assert list(known)[: len(KNOWN)] == list(KNOWN)


def test_a_key_declared_twice_is_refused() -> None:
    plane = KNOWN["tracker:plane"]
    with pytest.raises(ValueError, match="tracker:plane is declared twice"):
        registry(plane, plane)


def test_the_registry_is_read_only() -> None:
    writable = cast("dict[str, Integration]", KNOWN)
    with pytest.raises(TypeError):
        writable["excalidraw"] = KNOWN["excalidraw"]


async def test_without_a_store_each_integration_is_its_default() -> None:
    defaults: Integrations = Defaults()
    for key, integration in KNOWN.items():
        assert await defaults.is_enabled("acme", "launch", key) is integration.default


async def test_a_key_no_one_declared_is_off() -> None:
    assert not await Defaults().is_enabled("acme", "launch", "crm:hubspot")
    mine = registry(Integration("crm:hubspot", default=True, description="HubSpot."))
    assert await Defaults(mine).is_enabled("acme", "launch", "crm:hubspot")
    assert not await Defaults(mine).is_enabled("acme", "launch", "excalidraw")
