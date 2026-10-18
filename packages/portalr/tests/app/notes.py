"""artifactr in portalr's test application: notes, thumbs on messages, and a scripted agent.

The agent answers from a script, so the app's scenarios choose its path by the first word they
post: ``ask`` makes it ask a question, ``form`` asks a form through artifactr.ui's ``ask_form``
(lattice RFC-0005), whose answer it repeats, ``publish`` makes it call a tool that waits for
approval, ``propose`` makes it write a note of its own and propose an edit to it, which it names
in its answer, so each scenario resolves a proposal of its own; what follows ``propose``, such as
``a tighter plan``, is what the note is about, so two proposals aren't one. ``wait`` keeps its
turn running until it is stopped, and ``fail`` fails its turn, for admin's count of failed turns.
Anything else gets its words back. Each run streams, as every run does.
"""

import asyncio
import re

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
from artifactr.core import Actor
from artifactr.ui import UI_TYPES, ui_checks
from artifactr.ui.agent import ui_tools
from grantr.core import Agent as AgentSubject
from grantr.core import ServicePrincipal, Subject, User
from grantr.grants import Grants

CREATED = re.compile(r"^Done: (?P<note>\S+) is now at version")
"""What artifactr tells the agent when it has written a note: which note."""


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

DEFAULT_TOPIC = "launch"
"""What a note is about when ``propose`` says no more than "an edit"."""


def topic_of(prompt: str) -> str:
    """What ``propose ...`` asks a note about: the words after it, without their article."""
    words = re.sub(r"^(?:an?|the)\s+", "", prompt.removeprefix("propose").strip())
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
        case ["publish"]:
            return ModelResponse(parts=[ToolCallPart("publish", {"note": "the notes"})])
        case ["ask"]:
            return ModelResponse(parts=[ToolCallPart("ask_user", {"question": "Which week?"})])
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
    """What the agent does when a tool returns: propose an edit to a note it just wrote, or say
    how the tool went."""
    told = returned.model_response_str()
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
        calls = (
            part
            for message in messages
            for part in message.parts
            if isinstance(part, ToolCallPart) and part.tool_call_id == returned.tool_call_id
        )
        note = next(calls).args_as_dict()["artifact_id"]
        return ModelResponse(parts=[TextPart(f"Done: proposed an edit to {note}")])
    return ModelResponse(parts=[TextPart(f"Done: {told}")])


def publish(note: str) -> str:
    """Publish a note for everyone to read."""
    return f"Published {note}"


def build_agent() -> Agent[Session[None], str | DeferredToolRequests]:
    """The notes agent, on the script, with a tool that waits for a person's approval."""
    return Agent[Session[None], str | DeferredToolRequests](
        function_model(answer),
        deps_type=Session[None],
        output_type=[str, DeferredToolRequests],
        tools=[Tool(publish, requires_approval=True)],
        toolsets=[ui_tools(dashboards=False)],
        capabilities=[ArtifactWorkspace(types=[Note], ask=True)],
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


def collaboration(grants: Grants) -> tuple[Workspaces, Runner[None]]:
    """artifactr's workspaces, checked by grantr, and its runner."""
    hooks = grants.hooks(subject_of)
    workspaces = Workspaces(
        InMemoryStorage(),
        types=[Note, *UI_TYPES],
        checks=ui_checks(),
        authorize=hooks.authorize,
        hidden=hooks.hidden,
    )
    return workspaces, Runner[None](build_agent(), app=None, agent_name="assistant")
