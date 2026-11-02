"""Native files' commands (lattice RFC-0014, artifactr ADR-0104): listing a workspace's files and
reading a page of one's words, as the call's actor, through the files' app."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from artifactr.capabilities import FILES
from artifactr.commands import CATALOG
from artifactr.core import NotFound, UserActor
from artifactr.files.app import FakeApp
from artifactr.files.blobs import InMemoryBlobs, once
from artifactr.files.capabilities import PAGE_CHARS, NativeFilesProvider
from artifactr.files.checkouts import InMemoryCheckouts
from artifactr.files.manifest import DOCX, WordDocument
from artifactr.files.native import NativeFiles
from artifactr.workspace import InMemoryStorage, Workspaces
from lattice_core.capabilities import CallContext, PersonCaller, Scope
from lattice_core.taint import Clean
from tests.files.conftest import Switch

HERE = Scope(tenant_id="acme", workspace_id="w1")
ALICE = UserActor(id="alice")


def context(scope: Scope = HERE) -> CallContext:
    return CallContext(
        scope=scope,
        caller=PersonCaller(id="alice"),
        taint=Clean(),
        correlation_id="c1",
        surface="mcp",
    )


class World:
    def __init__(self) -> None:
        self.switch = Switch()
        self.files = NativeFiles(
            InMemoryBlobs(), InMemoryCheckouts(), FakeApp(), integrations=self.switch
        )
        self.workspaces = Workspaces(InMemoryStorage())
        self.provider = NativeFilesProvider(self.workspaces, self.files)

    async def upload(self, *paragraphs: str, artifact_id: str = "a1") -> None:
        ws = await self.workspaces.open("acme", "w1", actor=ALICE)
        made = once(FakeApp.file(*paragraphs))
        await self.files.upload(
            ws, WordDocument, "c.docx", made, media_type=DOCX, artifact_id=artifact_id
        )

    async def run(self, name: str, scope: Scope = HERE, **arguments: Any) -> str:
        [capability] = [c for c in self.provider.capabilities(scope) if c.name == name]
        output = (await self.provider.call(capability, arguments, context(scope))).output
        assert isinstance(output, str)
        return output


def test_it_offers_native_files_two_commands_as_the_catalog_declares_them() -> None:
    offered = World().provider.capabilities(HERE)
    commands = {c.name: c.capability for c in CATALOG.commands()}
    assert {c.name for c in offered} == FILES == {"artifactr.list_files", "artifactr.read_file"}
    assert all(capability == commands[capability.name] for capability in offered)


async def test_a_workspaces_files_are_listed_one_per_line() -> None:
    world = World()
    assert await world.run("artifactr.list_files") == "There are no native files here."
    await world.upload("Terms")
    [line] = (await world.run("artifactr.list_files")).splitlines()
    listed = json.loads(line)
    assert (listed["artifact_id"], listed["kind"], listed["name"]) == (
        "a1",
        "word_document",
        "c.docx",
    )
    assert (listed["version"], listed["media_type"]) == (1, DOCX)


async def test_a_files_words_are_read_a_page_at_a_time() -> None:
    world = World()
    await world.upload("Terms")
    assert (await world.run("artifactr.read_file", artifact_id="a1")).startswith("Terms")
    long = "x" * (PAGE_CHARS + 10)
    await world.upload(long, artifact_id="a2")
    first = await world.run("artifactr.read_file", artifact_id="a2")
    second = await world.run("artifactr.read_file", artifact_id="a2", page=2)
    assert first.endswith("[page 1 of 2]")
    assert second.endswith("[page 2 of 2]")
    beyond = await world.run("artifactr.read_file", artifact_id="a2", page=3)
    assert beyond == "a2 has 2 page(s) of text; there is no page 3."


async def test_a_read_is_refused_for_a_file_that_isnt_or_with_no_workspace_named() -> None:
    world = World()
    with pytest.raises(NotFound):
        await world.run("artifactr.read_file", artifact_id="nope")
    [listing] = [c for c in world.provider.capabilities(HERE) if c.name == "artifactr.list_files"]
    with pytest.raises(ValueError, match="is called in a workspace, and names none"):
        await world.provider.call(listing, {}, context(Scope(tenant_id="acme")))
    with pytest.raises(ValidationError):
        await world.provider.call(listing, {"page": 2}, context())


async def test_another_command_is_refused() -> None:
    world = World()
    commands = {c.name: c.capability for c in CATALOG.commands()}
    with pytest.raises(ValueError, match=r"artifactr\.list_threads isn't one of native files"):
        await world.provider.call(commands["artifactr.list_threads"], {}, context())
