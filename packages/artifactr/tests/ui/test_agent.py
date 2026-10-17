"""The agent's tools, run by artifactr's Runner on a scripted model, on every storage."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic_ai import (
    Agent,
    CallDeferred,
    DeferredToolRequests,
    FunctionToolset,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolReturnPart,
)

from artifactr.agent import ArtifactWorkspace, Runner, Session
from artifactr.core import (
    AnswerDeferred,
    InvalidState,
    NotFound,
    RunPaused,
    Thread,
    ValidationFailed,
)
from artifactr.ui import AGENT_TYPES, UI_TYPES, Dashboard, FeatureOff, Form, ui_checks
from artifactr.ui.agent import ui_tools
from artifactr.ui.integrations import DASHBOARDS, FORMS
from artifactr.ui.schema import MAX_SCHEMA_BYTES, FormSchema, json_size
from artifactr.workspace import Storage, Workspace, Workspaces
from tests.ui.model import Script, call, say
from tests.ui.people import ALICE, BOB
from tests.ui.refusals import locs
from tests.ui.toggles import Toggles

SCHEMA = {
    "type": "object",
    "properties": {
        "day": {"type": "string", "format": "date", "title": "Which day"},
        "people": {"type": "integer", "minimum": 1},
    },
    "required": ["day"],
}


@pytest.fixture
async def ws(workspaces: Workspaces) -> Workspace:
    return await workspaces.open("tenant_a", "ws_1", actor=ALICE)


@pytest.fixture
async def thread(ws: Workspace) -> Thread:
    return await ws.create_thread("Lunch")


@pytest.fixture
async def runners() -> AsyncIterator[list[Runner[None]]]:
    made: list[Runner[None]] = []
    yield made
    for runner in made:
        await runner.aclose()


def _runner(
    runners: list[Runner[None]],
    script: Script,
    toolset: FunctionToolset[Session[Any]] | None = None,
) -> Runner[None]:
    agent = Agent(
        script.model,
        deps_type=Session[None],
        output_type=[str, DeferredToolRequests],
        toolsets=[toolset or ui_tools()],
        capabilities=[ArtifactWorkspace(types=AGENT_TYPES, ask=True)],
    )
    runner = Runner(agent, app=None)
    runners.append(runner)
    return runner


async def _paused(runner: Runner[None], ws: Workspace, thread: Thread) -> str:
    sent = await runner.send(ws, thread.id, "When shall we have lunch?")
    assert sent.run is not None
    assert isinstance((await sent.run.wait()).output, DeferredToolRequests)
    return sent.run.run_id


# ─── ask_form ─────────────────────────────────────────────────────────────────


async def test_a_form_pauses_the_run_until_its_values_are_sent(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    script = Script(call("ask_form", "f1", title="Lunch", schema=SCHEMA), say("Friday it is."))
    runner = _runner(runners, script)
    run_id = await _paused(runner, ws, thread)
    [request] = (await ws.run(run_id)).pending
    assert (request.tool_name, request.kind) == ("ask_form", "question")
    values = {"day": "2026-10-23", "people": 4}
    resumed = (
        await runner.answer(ws, AnswerDeferred(run_id=run_id, tool_call_id="f1", answer=values))
    ).run
    assert resumed is not None
    assert (await resumed.wait()).output == "Friday it is."
    [returned] = [p for p in script.last_parts(1) if isinstance(p, ToolReturnPart)]
    assert returned.content == values


async def test_values_that_do_not_fit_are_refused_and_the_run_stays_paused(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    runner = _runner(runners, Script(call("ask_form", "f1", title="Lunch", schema=SCHEMA)))
    run_id = await _paused(runner, ws, thread)
    answer = AnswerDeferred(run_id=run_id, tool_call_id="f1", answer={"day": "Friday", "x": 1})
    with pytest.raises(ValidationFailed) as refused:
        await runner.answer(ws, answer)
    assert locs(refused.value) == [["day"], ["x"]]
    with pytest.raises(ValidationFailed):
        await ws.commit(answer.model_copy(update={"answer": "Friday"}))
    run = await ws.run(run_id)
    assert (run.status, run.answers) == ("paused", {})


async def test_a_second_answer_is_refused_as_answered(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    script = Script(call("ask_form", "f1", title="Lunch", schema=SCHEMA), say("Noted."))
    runner = _runner(runners, script)
    run_id = await _paused(runner, ws, thread)
    first = AnswerDeferred(run_id=run_id, tool_call_id="f1", answer={"day": "2026-10-23"})
    resumed = (await runner.answer(ws, first)).run
    assert resumed is not None
    await resumed.wait()
    with pytest.raises(InvalidState):
        await ws.as_actor(BOB).commit(first.model_copy(update={"answer": {"day": "2026-10-24"}}))
    with pytest.raises(InvalidState):
        await ws.as_actor(BOB).commit(first.model_copy(update={"answer": {"day": "not a day"}}))


async def test_an_answer_to_another_tool_or_to_no_request_is_left_to_artifactr(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    script = Script(call("ask_user", "q1", question="Who is coming?"), say("Thanks."))
    runner = _runner(runners, script)
    run_id = await _paused(runner, ws, thread)
    with pytest.raises(NotFound):
        await ws.commit(AnswerDeferred(run_id=run_id, tool_call_id="nope", answer="Bob"))
    resumed = (
        await runner.answer(ws, AnswerDeferred(run_id=run_id, tool_call_id="q1", answer="Bob"))
    ).run
    assert resumed is not None
    assert (await resumed.wait()).output == "Thanks."


async def test_a_refused_schema_goes_back_to_the_model_before_anything_pauses(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    bad = {"properties": {"secret": {"type": "string", "format": "password", "pattern": "x"}}}
    script = Script(
        call("ask_form", "f1", title="Log in", schema=bad, ui={"order": ["nope"]}),
        say("I won't ask for that."),
    )
    runner = _runner(runners, script)
    sent = await runner.send(ws, thread.id, "Ask me for my password")
    assert sent.run is not None
    assert (await sent.run.wait()).output == "I won't ask for that."
    [retry] = [p for p in script.last_parts(1) if isinstance(p, RetryPromptPart)]
    assert "pattern is not in the form subset" in str(retry.content)
    assert [e.event for e in await ws.read() if isinstance(e.event, RunPaused)] == []


async def test_a_32_kb_schema_survives_the_pause_storage_and_resume_unchanged(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    schema = _largest_schema()
    args = {"title": "Everything", "schema": schema, "ui": None}
    script = Script(call("ask_form", "big", **args), say("Got it."))
    runner = _runner(runners, script)
    run_id = await _paused(runner, ws, thread)
    [request] = (await ws.run(run_id)).pending
    assert request.args == args
    [paused] = [e.event for e in await ws.read() if isinstance(e.event, RunPaused)]
    assert paused.requests[0].args == args
    answer = AnswerDeferred(run_id=run_id, tool_call_id="big", answer={"p0": "a"})
    resumed = (await runner.answer(ws, answer)).run
    assert resumed is not None
    await resumed.wait()
    [asked] = [c for c in script.calls(1) if c.tool_name == "ask_form"]
    assert asked.args_as_dict() == args, "the resumed history holds the call as it was made"


def _largest_schema() -> dict[str, Any]:
    """A schema just under the limit as it is stored: 50 properties, with long descriptions."""
    properties = {f"p{i}": {"type": "string", "description": ""} for i in range(50)}
    schema = {
        "type": "object",
        "properties": properties,
        "required": [],
        "additionalProperties": False,
    }
    room = MAX_SCHEMA_BYTES - json_size({"title": "Everything", "schema": schema}) - 1
    for i, prop in enumerate(properties.values()):
        prop["description"] = "é" * (room // 100) + "x" * (room // 50 - 2 * (room // 100))
        if i == 0:
            prop["description"] += "x" * (room % 50)
    stored = FormSchema.model_validate(schema).model_dump(mode="json")
    assert stored == schema
    assert MAX_SCHEMA_BYTES - 100 < json_size(schema) < MAX_SCHEMA_BYTES
    return schema


async def test_a_chat_message_leaves_a_form_open_and_reaches_the_resumed_turn(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    script = Script(call("ask_form", "f1", title="Lunch", schema=SCHEMA), say("Friday, with Bob."))
    runner = _runner(runners, script)
    run_id = await _paused(runner, ws, thread)
    assert (await runner.send(ws, thread.id, "Bob is coming too")).run is None
    assert await runner.recover(ws) == [], "nothing is taken while the form is open"
    run = await ws.run(run_id)
    assert (run.status, run.answers) == ("paused", {})
    answer = AnswerDeferred(run_id=run_id, tool_call_id="f1", answer={"day": "2026-10-23"})
    resumed = (await runner.answer(ws, answer)).run
    assert resumed is not None
    assert (await resumed.wait()).output == "Friday, with Bob."
    texts = [str(part.content) for part in script.last_parts(1)]
    assert any("Bob is coming too" in text for text in texts)
    assert {"day": "2026-10-23"} in [
        part.content for part in script.last_parts(1) if isinstance(part, ToolReturnPart)
    ]


async def test_a_form_asked_past_the_subset_is_refused_as_such(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    unchecked = FunctionToolset[Session[Any]]()

    @unchecked.tool_plain
    async def ask_form(title: str) -> str:
        """A tool of the same name that asks without checking."""
        raise CallDeferred

    runner = _runner(runners, Script(call("ask_form", "f1", title="Lunch")), unchecked)
    run_id = await _paused(runner, ws, thread)
    answer = AnswerDeferred(run_id=run_id, tool_call_id="f1", answer={})
    with pytest.raises(ValidationFailed, match="not one the subset holds") as refused:
        await ws.commit(answer)
    assert locs(refused.value) == [["schema"]]


# ─── forms that take submissions, and dashboards ──────────────────────────────


async def test_create_form_makes_a_form_in_the_thread(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    script = Script(
        call("create_form", "c1", title="Lunch", schema={"anyOf": []}),
        call("create_form", "c2", title="Lunch", schema=SCHEMA, submissions="per_person"),
        say("Posted."),
    )
    runner = _runner(runners, script)
    sent = await runner.send(ws, thread.id, "Make a lunch poll")
    assert sent.run is not None
    await sent.run.wait()
    [retry] = [p for p in script.last_parts(1) if isinstance(p, RetryPromptPart)]
    assert "anyOf is not in the form subset" in str(retry.content)
    [form] = await ws.artifacts(Form)
    assert (form.data.submissions, form.data.form_schema) == (
        "per_person",
        FormSchema.model_validate(SCHEMA),
    )


async def test_a_dashboard_is_shown_and_updated_as_new_versions(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    stat = {"type": "stat", "label": "Open", "value": 3}

    def update(messages: list[ModelMessage]) -> ModelResponse:
        [shown] = [
            part.content
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart) and part.tool_name == "show_dashboard"
        ]
        dashboard_id = str(shown).split()[1]  # "Done: <id> is now at version 1."
        return call("update_dashboard", "d3", id=dashboard_id, panels=[{**stat, "value": 4}])

    script = Script(
        call("show_dashboard", "d1", title="Ops", panels=[{"type": "nope"}]),
        call("show_dashboard", "d2", title="Ops", panels=[stat]),
        update,
        say("Updated."),
    )
    runner = _runner(runners, script)
    sent = await runner.send(ws, thread.id, "Show me the open incidents")
    assert sent.run is not None
    await sent.run.wait()
    [retry] = [p for p in script.last_parts(1) if isinstance(p, RetryPromptPart)]
    assert "panels" in str(retry.content)
    [dashboard] = await ws.artifacts(Dashboard)
    assert dashboard.version == 2
    assert dashboard.data.panels[0].model_dump()["value"] == 4


async def test_the_toolset_offers_what_it_is_asked_for() -> None:
    assert set(ui_tools().tools) == {
        "ask_form",
        "create_form",
        "show_dashboard",
        "update_dashboard",
    }
    assert set(ui_tools(forms=False).tools) == {"show_dashboard", "update_dashboard"}
    assert set(ui_tools(dashboards=False).tools) == {"ask_form", "create_form"}


async def test_a_feature_switched_off_offers_no_tools_and_takes_no_answer(
    storage: Storage, runners: list[Runner[None]]
) -> None:
    toggles = Toggles()
    off = toggles.off.setdefault("ws_1", set())
    workspaces = Workspaces(storage, types=UI_TYPES, checks=ui_checks(integrations=toggles))
    ws = await workspaces.open("tenant_a", "ws_1", actor=ALICE)
    thread = await ws.create_thread("Lunch")
    script = Script(call("ask_form", "f1", title="Lunch", schema=SCHEMA), say("Later."))
    runner = _runner(runners, script, ui_tools(integrations=toggles))
    run_id = await _paused(runner, ws, thread)
    forms, dashboards = {"ask_form", "create_form"}, {"show_dashboard", "update_dashboard"}
    assert forms | dashboards <= set(script.tools[0])
    assert {(t, w) for t, w, _ in toggles.asked} == {("tenant_a", "ws_1")}
    off.add(FORMS)
    answer = AnswerDeferred(run_id=run_id, tool_call_id="f1", answer={"day": "2026-10-23"})
    with pytest.raises(FeatureOff, match="forms are off in this workspace") as refused:
        await runner.answer(ws, answer)
    assert refused.value.details() == {"reason": "off", "key": "ui:forms"}
    off.symmetric_difference_update({FORMS, DASHBOARDS})
    resumed = (await runner.answer(ws, answer)).run
    assert resumed is not None
    await resumed.wait()
    assert forms <= set(script.tools[1])
    assert dashboards.isdisjoint(script.tools[1]), "a feature that is off is not offered"
