"""artifactr in portalr's test application: notes, thumbs on messages, and a scripted agent.

The agent answers from a script, so the app's scenarios choose its path by the first word they post:
``ask`` makes it ask two questions, and ``form`` a form through artifactr.ui's ``ask_form`` (lattice
RFC-0005), whose answers it repeats; ``publish`` makes it call a tool that waits for approval,
``propose`` makes it write a note of its own and propose an edit to it, which it names in its
answer, so each scenario resolves a proposal of its own; what follows ``propose``, such as ``a
tighter plan``, is what the note is about, so two proposals aren't one. ``draft`` makes it draft a
Word document about what follows, as ``documents.py`` does, which it names in its answer; ``revise``
and a document's id make it read the document and edit it by the app's commands, which is a
proposal, or, while someone has it checked out, an answer that says who, and that it plans again
after the check-in. ``write`` makes it create a Word document and a presentation blank, with
``create_native_file``, and propose what goes in each, as the owner once asked for a travel plan
(lattice#874). ``draw`` makes it draw a flowchart of the stack from Mermaid, a diagram it
proposes (lattice RFC-0006). ``wait`` keeps its turn running until it is stopped, and ``fail``
fails its turn, for admin's count of failed turns. Anything else gets its words back. Each run
streams, as every run does.
"""

import asyncio
import re
from collections.abc import Mapping
from typing import Any

from pydantic_ai import (
    Agent,
    DeferredToolRequests,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    Tool,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo

from artifactr import (
    AgentActor,
    ArtifactWorkspace,
    ExternalAgentActor,
    Feedback,
    InMemoryStorage,
    MarkdownArtifact,
    Runner,
    Session,
    SystemActor,
    UserActor,
    Workspaces,
)
from artifactr.agent import function_model
from artifactr.core import Actor, Command
from artifactr.excalidraw import (
    Diagram,
    FakeConverter,
    diagram_tools,
    excalidraw_checks,
    excalidraw_key_of,
)
from artifactr.files.blobs import Blobs
from artifactr.files.manifest import Presentation, WordDocument
from artifactr.files.native import NativeFiles
from artifactr.files.tools import native_file_tools
from artifactr.ui import UI_TYPES, ui_checks
from artifactr.ui.agent import ui_tools
from artifactr.workspace import Check, Workspace, integration_gate
from grantr.core import Agent as AgentSubject
from grantr.core import ServicePrincipal, Subject, User
from grantr.grants import Grants
from lattice_core.integrations import Integrations
from tests.app.documents import document_tools, native_files

CREATED = re.compile(r"^Done: (?P<note>\S+) is now at version")
"""What artifactr tells the agent when it has written a note or a document: which one."""

VERSION = re.compile(r"^\S+ \(\w+, v(?P<version>\d+)\)")
"""The version an artifact is at, in what ``read_artifact`` tells the agent."""

MADE = re.compile(r"^Created (?P<file>\S+):")
"""What ``create_native_file`` tells the agent when it has made a file: which one."""

PLAN = {
    "word_document": (
        "Write the travel plan",
        ["Travel plan", "Day 1: Lisbon, the old town.", "Day 2: Sintra by train."],
    ),
    "presentation": ("Write the travel plan's slides", ["Travel plan", "Lisbon", "Sintra"]),
}
"""What ``write`` creates, in order, and the change it proposes for each: its summary, and the
paragraphs it adds."""


class Note(MarkdownArtifact):
    """A Markdown note."""


class Thumbs(Feedback, name="thumbs", targets={"message", "artifact", "turn"}):
    """Whether a message, an artifact or a turn helped, and why."""

    up: bool
    comment: str | None = None


LEAVE = {
    "title": "Request leave",
    "schema": {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "title": "Working days", "minimum": 1, "maximum": 30},
            "note": {"type": "string", "title": "Anything else"},
        },
        "required": ["days"],
    },
    "ui": {"submit_label": "Ask for leave"},
}
"""The form ``form`` asks: how many working days, at most 30, and a note."""

QUESTIONS = {
    "questions": [
        {
            "question": "Which week?",
            "header": "Week",
            "options": [
                {"label": "This week", "description": "Starting Monday"},
                {"label": "The next", "description": "A week to prepare", "recommended": True},
            ],
            "other": True,
        },
        {
            "question": "What should the notes cover?",
            "header": "Topics",
            "options": [
                {"label": "Agenda", "description": "What is planned, in order"},
                {"label": "Decisions", "description": "What was settled, and by whom"},
                {"label": "Actions", "description": "Who does what next"},
            ],
            "multiple": True,
        },
    ]
}
"""What ``ask`` asks through ``ask_user``: one choice that takes words of a person's own, and
several choices."""

DEFAULT_TOPIC = "launch"
"""What a note is about when ``propose`` says no more than "an edit"."""


STACK = "flowchart LR\n  API -- reads --> DB\n  DB -- copies --> Backup"
"""The diagram ``draw`` makes: a flowchart, which the fake converter draws as the worker would."""


def topic_of(prompt: str) -> str:
    """What ``propose ...`` or ``draft ...`` is about: the words after it, without their article."""
    words = re.sub(r"^(?:an?|the)\s+", "", prompt.partition(" ")[2].strip())
    return DEFAULT_TOPIC if words in ("", "edit") else words


def first_prompt(messages: list[ModelMessage]) -> str:
    """What the person first asked of the agent in this turn's conversation."""
    return next(
        (
            str(part.content)
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, UserPromptPart)
        ),
        "",
    )


async def answer(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
    """The script: what the agent says or calls, from what it was just given."""
    given = messages[-1]
    parts = given.parts if isinstance(given, ModelRequest) else []
    returned = [part for part in parts if isinstance(part, ToolReturnPart)]
    if returned:
        return after(returned[-1], messages)
    prompt = " ".join(str(part.content) for part in parts if isinstance(part, UserPromptPart))
    match prompt.split(maxsplit=1)[:1]:
        case ["propose"]:
            note = {"kind": "note", "data": {"text": f"{topic_of(prompt).capitalize()} on Monday."}}
            return ModelResponse(parts=[ToolCallPart("create_artifact", note)])
        case ["draft"]:
            about = topic_of(prompt).capitalize()
            # Four paragraphs, which the stand-in lays out on two pages.
            paragraphs = [about, f"{about} starts on Monday.", "Who comes.", "What to bring."]
            document = {"name": f"{about.lower().replace(' ', '-')}.docx", "paragraphs": paragraphs}
            return ModelResponse(parts=[ToolCallPart("draft_document", document)])
        case ["revise"]:
            # The document's id, and none of the change notes that may follow it.
            document = (prompt.split()[1:] or [""])[0]
            return ModelResponse(parts=[ToolCallPart("read_artifact", {"artifact_id": document})])
        case ["write"] if writes(prompt):
            return ModelResponse(parts=[create_next(messages)])
        case ["draw"]:
            drawn = {"mermaid": STACK, "summary": "the stack", "name": "Stack"}
            return ModelResponse(parts=[ToolCallPart("draw_mermaid", drawn)])
        case ["publish"]:
            return ModelResponse(parts=[ToolCallPart("publish", {"note": "the notes"})])
        case ["ask"]:
            return ModelResponse(parts=[ToolCallPart("ask_user", QUESTIONS)])
        case ["form"]:
            return ModelResponse(parts=[ToolCallPart("ask_form", LEAVE)])
        case ["wait"]:
            await asyncio.Event().wait()  # until someone stops the turn, which cancels it
            return ModelResponse(parts=[TextPart("Done waiting.")])
        case ["fail"]:
            raise RuntimeError("the turn was asked to fail")
        case _:
            return ModelResponse(parts=[TextPart(f"You said: **{prompt}**")])


def after(returned: ToolReturnPart, messages: list[ModelMessage]) -> ModelResponse:
    """What the agent does when a tool returns: propose an edit to a note it just wrote, edit a
    document it just read, or say how the tool went."""
    told = returned.model_response_str()
    if returned.tool_name == "ask_user" and isinstance(returned.content, list):
        chosen = (
            ", ".join([*answer["selected"], *filter(None, [answer.get("other")])])
            for answer in returned.content
        )
        return ModelResponse(parts=[TextPart(f"Done: {'; '.join(chosen)}")])
    if returned.tool_name == "ask_form" and isinstance(returned.content, dict):
        return ModelResponse(parts=[TextPart(f"Done: {returned.content['days']} working days off")])
    if returned.tool_name == "create_artifact" and (created := CREATED.search(told)):
        about = topic_of(first_prompt(messages))
        edit = {
            "artifact_id": created["note"],
            "old": "Monday",
            "new": "Tuesday",
            "summary": f"Move the {about} to Tuesday",
            "propose": True,
            "rationale": f"Monday is a holiday, so the {about} moves.",
        }
        return ModelResponse(parts=[ToolCallPart("edit_text", edit)])
    if returned.tool_name == "edit_text":
        note = called(returned, messages)["artifact_id"]
        return ModelResponse(parts=[TextPart(f"Done: proposed an edit to {note}")])
    if returned.tool_name in ("create_native_file", "edit_native") and writes(
        first_prompt(messages)
    ):
        return write_next(messages)
    if returned.tool_name == "draw_mermaid":
        return ModelResponse(parts=[TextPart("Drew the stack.")])
    if returned.tool_name == "draft_document" and (created := CREATED.search(told)):
        return ModelResponse(parts=[TextPart(f"Drafted {created['note']}")])
    if returned.tool_name == "read_artifact" and (read := VERSION.search(told)):
        edit = {
            "artifact_id": called(returned, messages)["artifact_id"],
            "base_version": int(read["version"]),
            "commands": [{"name": "add_paragraph", "args": {"text": "Signed off by the agent."}}],
            "summary": "Add a sign-off",
        }
        return ModelResponse(parts=[ToolCallPart("edit_native", edit)])
    return ModelResponse(parts=[TextPart(f"Done: {told}")])


def writes(prompt: str) -> bool:
    """Whether a prompt is ``write``'s: "write up ...", which no other scenario posts."""
    return prompt.startswith("write up ")


def create_next(messages: list[ModelMessage]) -> ToolCallPart:
    """``write``'s next file to create: the first of ``PLAN``'s kinds it hasn't."""
    made = len(calls(messages, "create_native_file"))
    return ToolCallPart("create_native_file", {"type": list(PLAN)[made], "title": "Travel plan"})


def write_next(messages: list[ModelMessage]) -> ModelResponse:
    """``write``'s next step: create the next file, then propose each one's paragraphs, in turn."""
    if len(calls(messages, "create_native_file")) < len(PLAN):
        return ModelResponse(parts=[create_next(messages)])
    made = [
        found["file"]
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "create_native_file"
        if (found := MADE.search(part.model_response_str()))
    ]
    edited = len(calls(messages, "edit_native"))
    if edited < len(made):
        summary, paragraphs = list(PLAN.values())[edited]
        edit = {
            "artifact_id": made[edited],
            # Each file is as created, version 1: its only change is this proposal, not yet
            # accepted, since the turn proposes and ends before anyone answers.
            "base_version": 1,
            "commands": [{"name": "add_paragraph", "args": {"text": each}} for each in paragraphs],
            "summary": summary,
        }
        return ModelResponse(parts=[ToolCallPart("edit_native", edit)])
    return ModelResponse(
        parts=[TextPart("Created the travel plan as a document and slides: both wait for review.")]
    )


def calls(messages: list[ModelMessage], tool: str) -> list[ToolCallPart]:
    """The agent's calls of a tool in this turn's conversation, in order."""
    return [
        part
        for message in messages
        for part in message.parts
        if isinstance(part, ToolCallPart) and part.tool_name == tool
    ]


def called(returned: ToolReturnPart, messages: list[ModelMessage]) -> dict[str, Any]:
    """The arguments of the call a tool returned from."""
    calls = (
        part
        for message in messages
        for part in message.parts
        if isinstance(part, ToolCallPart) and part.tool_call_id == returned.tool_call_id
    )
    return next(calls).args_as_dict()


def publish(note: str) -> str:
    """Publish a note for everyone to read."""
    return f"Published {note}"


def build_agent(
    workspaces: Workspaces, files: NativeFiles, integrations: Integrations
) -> Agent[Session[None], str | DeferredToolRequests]:
    """The notes agent, on the script, with a tool that waits for a person's approval, and the
    tools for native files and diagrams."""
    return Agent[Session[None], str | DeferredToolRequests](
        function_model(answer),
        deps_type=Session[None],
        output_type=[str, DeferredToolRequests],
        tools=[Tool(publish, requires_approval=True)],
        toolsets=[
            ui_tools(dashboards=False),
            native_file_tools(files),
            document_tools(workspaces, files),
            diagram_tools(FakeConverter(), integrations=integrations),
        ],
        capabilities=[
            ArtifactWorkspace(types=[Note, WordDocument, Presentation, Diagram], ask=True)
        ],
    )


APPLICATION = ServicePrincipal(id="portalr-test")
"""The test application's own principal, which its runner acts as, holding grantr's
``application`` role."""


def subject_of(tenant: str, workspace: str | None, actor: Actor) -> Subject:
    """Who grantr checks for an artifactr actor, as the template maps them: the person a run or
    client acts for, and the application for its own system."""
    match actor:
        case UserActor():
            return User(id=actor.id)
        case AgentActor(on_behalf_of=acting) if acting is not None:
            return subject_of(tenant, workspace, acting)
        case ExternalAgentActor(on_behalf_of=person) if person is not None:
            return User(id=person.id)
        case SystemActor():
            return APPLICATION
        case _:  # an agent or a client acting for no one holds nothing here
            return AgentSubject()


def _together(*each: Mapping[str, Check]) -> dict[str, Check]:
    """Checks for the same command types, run in turn: artifactr takes one check a type."""

    def joined(found: list[Check]) -> Check:
        async def check(workspace: Workspace, command: Command) -> None:
            for one in found:
                await one(workspace, command)

        return check

    kinds = sorted({kind for checks in each for kind in checks})
    return {kind: joined([checks[kind] for checks in each if kind in checks]) for kind in kinds}


def collaboration(grants: Grants, blobs: Blobs) -> tuple[Workspaces, Runner[None], NativeFiles]:
    """artifactr's workspaces, checked by grantr and switched by its integrations, its runner, and
    its native files, kept in `blobs` with diagrams' images."""
    hooks = grants.hooks(subject_of)
    files = native_files(grants, blobs)
    workspaces = Workspaces(
        InMemoryStorage(),
        types=[Note, WordDocument, Presentation, Diagram, *UI_TYPES],
        checks=_together(ui_checks(), excalidraw_checks()),
        authorize=hooks.authorize,
        hidden=hooks.hidden,
        gate=integration_gate(
            grants, lambda kind, data: excalidraw_key_of(kind, data) or files.key_of(kind, data)
        ),
    )
    runner = Runner[None](build_agent(workspaces, files, grants), app=None, agent_name="assistant")
    return workspaces, runner, files
