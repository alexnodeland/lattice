"""artifactr in portalr's test application: notes, thumbs on messages, and a scripted agent.

The agent answers from a script, so the app's scenarios choose its path by what they post: a
message that mentions ``ask`` makes it ask a question, ``publish`` makes it call a tool that
waits for approval, ``propose ... to <note>`` makes it propose an edit to that note, and
anything else gets its words back. Each run streams, as every run does. acme's ``notes``
workspace starts with two notes for proposals, ``launch-accept`` and ``launch-reject``, one for
each scenario that resolves one.
"""

import re
from collections.abc import Awaitable, Callable

from pydantic import JsonValue
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
from artifactr.core import Actor, CreateArtifact
from artifactr.workspace import Storage
from grantr.core import Agent as AgentSubject
from grantr.core import ServicePrincipal, Subject, User
from grantr.grants import Grants

PROPOSE = re.compile(r"propose .* to (?P<note>[\w-]+)")
"""What makes the agent propose an edit, to the note it names."""

NOTES = ("launch-accept", "launch-reject")
"""The notes acme's ``notes`` workspace starts with, one per scenario that resolves a proposal."""


class Note(MarkdownArtifact):
    """A Markdown note."""


class Thumbs(Feedback, name="thumbs", targets={"message"}):
    """Whether a message helped."""

    up: bool


def answer(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
    """The script: what the agent says or calls, from what it was just given."""
    given = messages[-1]
    parts = given.parts if isinstance(given, ModelRequest) else []
    returned = [part for part in parts if isinstance(part, ToolReturnPart)]
    if returned:
        return ModelResponse(parts=[TextPart(f"Done: {returned[-1].model_response_str()}")])
    prompt = " ".join(str(part.content) for part in parts if isinstance(part, UserPromptPart))
    if proposal := PROPOSE.search(prompt):
        edit = {
            "artifact_id": proposal["note"],
            "old": "Monday",
            "new": "Tuesday",
            "summary": "Move the launch to Tuesday",
            "propose": True,
            "rationale": "Monday is a holiday.",
        }
        return ModelResponse(parts=[ToolCallPart("edit_text", edit)])
    if "publish" in prompt:
        return ModelResponse(parts=[ToolCallPart("publish", {"note": "the notes"})])
    if "ask" in prompt:
        return ModelResponse(parts=[ToolCallPart("ask_user", {"question": "Which week?"})])
    return ModelResponse(parts=[TextPart(f"You said: **{prompt}**")])


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
        capabilities=[ArtifactWorkspace(types=[Note], ask=True)],
    )


APPLICATION = ServicePrincipal(id="portalr-test")
"""The test application's own principal, which its runner acts as, holding grantr's
``application`` role."""


def subject_of(_tenant: str, _workspace: str | None, actor: Actor) -> Subject:
    """Who grantr checks for an artifactr actor, as the template maps them: the person a run or
    client acts for, and the application for its own system."""
    match actor:
        case UserActor():
            return User(id=actor.id)
        case AgentActor(on_behalf_of=acting) if acting is not None:
            return subject_of(_tenant, _workspace, acting)
        case ExternalAgentActor(on_behalf_of=person) if person is not None:
            return User(id=person.id)
        case SystemActor():
            return APPLICATION
        case _:  # an agent or a client acting for no one holds nothing here
            return AgentSubject()


def collaboration(
    grants: Grants,
) -> tuple[Workspaces, Runner[None], Callable[[], Awaitable[None]]]:
    """artifactr's workspaces, checked by grantr, its runner, and how to seed acme's notes."""
    storage: Storage = InMemoryStorage()
    hooks = grants.hooks(subject_of)
    workspaces = Workspaces(storage, types=[Note], authorize=hooks.authorize, hidden=hooks.hidden)
    runner = Runner[None](build_agent(), app=None, agent_name="assistant")

    async def seed() -> None:
        unchecked = Workspaces(storage, types=[Note])
        workspace = await unchecked.open("acme", "notes", actor=SystemActor())
        for note in NOTES:
            data: dict[str, JsonValue] = {"text": "Launch on Monday."}
            await workspace.commit(CreateArtifact(artifact_id=note, kind="note", data=data))

    return workspaces, runner, seed
