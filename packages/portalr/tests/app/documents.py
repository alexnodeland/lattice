"""Native files in portalr's test application: Word documents and presentations, read and edited
by stand-in apps.

WordCraft and DeckCraft themselves are too large and too slow for the scenarios, so each one's
integration, ``files:wordcraft`` and ``files:deckcraft``, switches a stand-in: artifactr's
``FakeApp``, whose files are JSON paragraphs.
A document here is a ``word_document`` whose bytes are the stand-in's, so a scenario checks one out,
edits it as a person would by saving another of the stand-in's files, and checks it in. The agent
drafts one with ``draft_document``, which uploads it as the person it acts for: an upload is how a
person adds a file, and the agent's own would be a proposal, as every agent's change to a native
file is. The agent also creates both kinds blank with ``create_native_file``, and proposes what
goes in them. Nightly runs the same routes with WordCraft (artifactr's ``test_pilot_live.py``).

The stand-in reads every file in this process: it is for trusted files only, as artifactr's
``Subprocess`` adapter is, and isolates nothing.
"""

from typing import Any

from pydantic_ai import FunctionToolset, RunContext

from artifactr import AgentActor, Session, Workspaces
from artifactr.agent import describe_outcome
from artifactr.core import Forbidden
from artifactr.excalidraw import Diagram
from artifactr.files.app import FakeApp
from artifactr.files.blobs import Blobs, once
from artifactr.files.checkouts import InMemoryCheckouts
from artifactr.files.manifest import DOCX, Presentation, WordDocument
from artifactr.files.native import NativeFiles
from lattice_core.integrations import Integrations


class StandIn(FakeApp):
    """artifactr's fake app, switched as WordCraft is, by ``files:wordcraft``."""

    name: str = "wordcraft"
    integration: str = "files:wordcraft"


class DeckStandIn(FakeApp):
    """artifactr's fake app, switched as DeckCraft is, by ``files:deckcraft``."""

    name: str = "deckcraft"
    integration: str = "files:deckcraft"


def native_files(integrations: Integrations, blobs: Blobs) -> NativeFiles:
    """The application's native files, kept in `blobs`, read and edited by the stand-ins.

    Diagrams keep the images a person puts on them in the same store, which its collection keeps
    while a revision names them (artifactr ADR-0092).
    """
    return NativeFiles(
        blobs,
        InMemoryCheckouts(),
        {WordDocument: StandIn(), Presentation: DeckStandIn()},
        integrations=integrations,
        naming=(Diagram,),
    )


def document_tools(workspaces: Workspaces, files: NativeFiles) -> FunctionToolset[Session[Any]]:
    """The tool the scripted agent drafts a document with, as the person it acts for."""
    toolset = FunctionToolset[Session[Any]]()

    @toolset.tool
    async def draft_document(
        ctx: RunContext[Session[Any]], name: str, paragraphs: list[str]
    ) -> str:
        """Draft a Word document of paragraphs, named as given.

        Args:
            name: The file's name, such as ``brief.docx``.
            paragraphs: Its paragraphs, in order.
        """
        agent = ctx.deps.workspace
        person = agent.actor.on_behalf_of if isinstance(agent.actor, AgentActor) else None
        if person is None:
            raise Forbidden("a document is drafted for the person who asked for it")
        ws = await workspaces.open(agent.tenant_id, agent.workspace_id, actor=person)
        made = await files.upload(
            ws,
            WordDocument,
            name,
            once(StandIn.file(*paragraphs)),
            media_type=DOCX,
            thread_id=ctx.deps.thread_id,
        )
        assert made is not None, "an upload under a new id is always made"
        return describe_outcome(made)

    return toolset
