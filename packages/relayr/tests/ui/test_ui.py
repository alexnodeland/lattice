"""relayr.ui: what a person sends reaches a rule as one event, whichever way it was asked."""

import asyncio
from contextlib import aclosing
from typing import Any

import pytest
from pydantic import ValidationError
from pydantic_ai import (
    Agent,
    DeferredToolRequests,
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

import artifactr
import artifactr.core as a
import reflexr
import reflexr.core
import reflexr.workspace as r
from artifactr.agent import ArtifactWorkspace, Runner, Session, function_model
from artifactr.core import AnswerDeferred, Applied, ArchiveArtifact, CreateArtifact, InvalidState
from artifactr.ui import AGENT_TYPES, UI_TYPES, submission_id, ui_checks
from artifactr.ui.agent import ui_tools
from relayr.events import BRIDGED, Projections
from relayr.inbound import SOURCE, Followers
from relayr.ledger import Ledger
from relayr.ui import (
    UI_EVENTS,
    UI_PROJECTIONS,
    UI_PUBLISHERS,
    AppSubmitted,
    FormSubmitted,
)

ALICE = a.UserActor(id="alice", name="Alice")
BOB = a.UserActor(id="bob", name="Bob")

TENANT, WORKSPACE = "acme", "prod"
FORM: dict[str, Any] = {
    "title": "Lunch?",
    "schema": {"properties": {"day": {"enum": ["fri", "sat"]}}},
}


async def _bridged(reader: r.Workspace, *, forms: int, apps: int) -> list[str]:
    """Follow reflexr's log until the follower has bridged as many of each as awaited."""
    seen: list[str] = []
    async with asyncio.timeout(30), aclosing(reader.subscribe()) as envelopes:
        async for envelope in envelopes:
            seen.append(envelope.event.event_type)
            if seen.count("ui:form_submitted") == forms and seen.count("ui:app_submitted") == apps:
                break
    return seen


def _agent(thread_id: str) -> a.AgentActor:
    return a.AgentActor(thread_id=thread_id, run_id="run_1", on_behalf_of=ALICE)


def _script(*steps: ModelResponse) -> FunctionModel:
    """A model that answers each request with the next step."""
    left = list(steps)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return left.pop(0)

    return function_model(respond)


async def test_a_rule_fires_once_on_form_submitted_from_each_way_of_asking(
    ledger: Ledger,
) -> None:
    fired: list[reflexr.Event] = []

    async def record(reaction: r.Reaction[None]) -> None:
        fired.extend(envelope.event for envelope in reaction.events)

    rules = [
        reflexr.Rule(name=name, when=reflexr.on(t), then=reflexr.run("record"))
        for name, t in [("app:forms", FormSubmitted), ("app:apps", AppSubmitted)]
    ]
    automation = r.Workspaces(
        r.InMemoryStorage(), events=[*BRIDGED, *UI_EVENTS], publishers=UI_PUBLISHERS, rules=rules
    )

    async def on_open(tenant_id: str, workspace_id: str) -> None:
        await followers.watch(tenant_id, workspace_id)

    collaboration = artifactr.Workspaces(
        artifactr.InMemoryStorage(), types=UI_TYPES, checks=ui_checks(), on_open=on_open
    )
    followers = Followers(
        collaboration, automation, ledger, projections=Projections(**UI_PROJECTIONS)
    )
    reactor = r.Reactor(automation, actions={"record": record})
    asking = ToolCallPart(tool_name="ask_form", args=FORM, tool_call_id="f1")
    model = _script(ModelResponse(parts=[asking]), ModelResponse(parts=[TextPart("Friday then.")]))
    runner = Runner(
        Agent(
            model,
            deps_type=Session[None],
            output_type=[str, DeferredToolRequests],
            toolsets=[ui_tools()],
            capabilities=[ArtifactWorkspace(types=AGENT_TYPES)],
        ),
        app=None,
    )
    try:
        ws = await collaboration.open(TENANT, WORKSPACE, actor=ALICE)
        thread = await ws.create_thread("Lunch")

        sent = await runner.send(ws, thread.id, "When is lunch?")
        assert sent.run is not None
        await sent.run.wait()
        answer = AnswerDeferred(run_id=sent.run.run_id, tool_call_id="f1", answer={"day": "fri"})
        resumed = (await runner.answer(ws, answer)).run
        assert resumed is not None
        await resumed.wait()

        made = await ws.as_actor(_agent(thread.id)).commit(
            CreateArtifact(kind="form", data=FORM, thread_id=thread.id)
        )
        assert isinstance(made, Applied)
        submit = CreateArtifact(
            kind="submission",
            artifact_id=submission_id(made.artifact_id),
            data={"form_id": made.artifact_id, "version": 1, "values": {"day": "sat"}},
            thread_id=thread.id,
        )
        await ws.as_actor(BOB).commit(submit)
        with pytest.raises(InvalidState):
            await ws.as_actor(BOB).commit(submit)
        archive = ArchiveArtifact(artifact_id=submission_id(made.artifact_id), base_version=1)
        await ws.as_actor(BOB).commit(archive)

        app: dict[str, Any] = {"title": "Dice", "summary": "Rolls a die", "html": "<p>4</p>"}
        built = await ws.as_actor(_agent(thread.id)).commit(CreateArtifact(kind="app", data=app))
        assert isinstance(built, Applied)
        app_id = built.artifact_id
        await ws.commit(
            CreateArtifact(
                kind="submission",
                artifact_id=submission_id(app_id, nonce="n1"),
                data={"app_id": app_id, "version": 1, "values": {"rolled": 4}, "nonce": "n1"},
            )
        )

        reader = await automation.open(TENANT, WORKSPACE, actor=reflexr.SystemActor())
        await _bridged(reader, forms=2, apps=1)
        await reactor.settle()
    finally:
        await runner.aclose()
        await followers.aclose()

    asked = FormSubmitted(
        author=ALICE,
        thread_id=thread.id,
        values={"day": "fri"},
        turn_id=sent.run.run_id,
        tool_call_id="f1",
    )
    submitted = FormSubmitted(
        author=BOB, thread_id=thread.id, values={"day": "sat"}, form_id=made.artifact_id, version=1
    )
    to_app = AppSubmitted(author=ALICE, values={"rolled": 4}, app_id=app_id, version=1)
    assert len(fired) == 3
    assert all(fired.count(event) == 1 for event in (asked, submitted, to_app)), fired
    types = [e.event.event_type for e in await reader.read()]
    assert "artifactr:deferred_answered" not in types, "the answer became ui:form_submitted"
    assert types.count("artifactr:artifact_created") == 2, "the form and the app, not submissions"
    assert "artifactr:artifact_archived" not in types, "a submission's archive bridges nothing"


async def test_no_client_publishes_a_submission_itself() -> None:
    automation = r.Workspaces(r.InMemoryStorage(), events=UI_EVENTS, publishers=UI_PUBLISHERS)
    client = await automation.open(TENANT, WORKSPACE, actor=reflexr.UserActor(id="mallory"))
    forged = FormSubmitted(author=ALICE, values={"day": "fri"}, form_id="form_1", version=1)
    with pytest.raises(reflexr.core.Forbidden, match="reserved to source:artifactr"):
        await client.publish(forged)
    assert await client.as_actor(SOURCE).publish(forged), "the follower's publisher may"


@pytest.mark.parametrize(
    "named",
    [
        {},
        {"form_id": "form_1"},
        {"form_id": "form_1", "version": 1, "turn_id": "run_1"},
        {"form_id": "form_1", "turn_id": "run_1"},
        {"form_id": "form_1", "version": 1, "turn_id": "run_1", "tool_call_id": "f1"},
    ],
)
def test_a_form_is_sent_as_a_submission_or_as_an_answer(named: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="only one"):
        FormSubmitted(author=ALICE, values={}, **named)
