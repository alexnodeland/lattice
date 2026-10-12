"""artifactr in portalr's test application: notes, thumbs on messages, and a scripted agent.

The agent answers from a script, so the app's scenarios choose its path by the first word they
post: ``ask`` makes it ask a question, ``publish`` makes it call a tool that waits for approval,
and ``propose`` makes it write a note of its own and propose an edit to it, which it names in its
answer, so each scenario resolves a proposal of its own. Anything else gets its words back. Each
run streams, as every run does.
"""

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
from grantr.core import Agent as AgentSubject
from grantr.core import ServicePrincipal, Subject, User
from grantr.grants import Grants

CREATED = re.compile(r"^Done: (?P<note>\S+) is now at version")
"""What artifactr tells the agent when it has written a note: which note."""


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
        return after(returned[-1], messages)
    prompt = " ".join(str(part.content) for part in parts if isinstance(part, UserPromptPart))
    match prompt.split(maxsplit=1)[:1]:
        case ["propose"]:
            note = {"kind": "note", "data": {"text": "Launch on Monday."}}
            return ModelResponse(parts=[ToolCallPart("create_artifact", note)])
        case ["publish"]:
            return ModelResponse(parts=[ToolCallPart("publish", {"note": "the notes"})])
        case ["ask"]:
            return ModelResponse(parts=[ToolCallPart("ask_user", {"question": "Which week?"})])
        case _:
            return ModelResponse(parts=[TextPart(f"You said: **{prompt}**")])


def after(returned: ToolReturnPart, messages: list[ModelMessage]) -> ModelResponse:
    """What the agent does when a tool returns: propose an edit to a note it just wrote, or say
    how the tool went."""
    told = returned.model_response_str()
    if returned.tool_name == "create_artifact" and (created := CREATED.search(told)):
        edit = {
            "artifact_id": created["note"],
            "old": "Monday",
            "new": "Tuesday",
            "summary": "Move the launch to Tuesday",
            "propose": True,
            "rationale": "Monday is a holiday.",
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
        InMemoryStorage(), types=[Note], authorize=hooks.authorize, hidden=hooks.hidden
    )
    return workspaces, Runner[None](build_agent(), app=None, agent_name="assistant")
