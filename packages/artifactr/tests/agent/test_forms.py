"""A chat message doesn't answer a form: a form is answered only by its own answer (RFC-0005)."""

from typing import Any

from pydantic_ai import CallDeferred, DeferredToolRequests, FunctionToolset
from pydantic_ai.messages import ModelResponse

from artifactr.agent import Session
from artifactr.core import AnswerDeferred, RunStarted, Thread
from artifactr.workspace import Workspace
from tests.agent.conftest import Gate, MakeRunner, Script, call, make_agent, say, started

ASKING = [str, DeferredToolRequests]
VALUES = {"day": "Monday", "attendees": 3}


def _form_tools() -> FunctionToolset[Session[Gate]]:
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool_plain
    async def ask_form(title: str, schema: dict[str, Any]) -> str:
        """Ask the people in this thread to fill in a form, as artifactr-ui's tool does."""
        raise CallDeferred(metadata={"kind": "question"})

    return tools


def _ask(*calls: ModelResponse) -> ModelResponse:
    return ModelResponse(parts=[part for response in calls for part in response.parts])


FORM = call("ask_form", call_id="f1", title="Book the room", schema={"type": "object"})


async def _starts(ws: Workspace) -> list[tuple[str, tuple[str, ...]]]:
    return [
        (e.event.trigger, e.event.message_ids)
        for e in await ws.read()
        if isinstance(e.event, RunStarted)
    ]


async def test_a_message_answers_the_questions_and_leaves_a_form_open(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(
        lambda _: _ask(call("ask_user", call_id="q1", question="Which day?"), FORM),
        say("Booked."),
    )
    runner = runners(make_agent(script, ask=True, tools=[_form_tools()], output_type=ASKING))
    paused = started(await runner.send(ws, thread.id, "Book a room"))
    await paused.wait()
    replied = await runner.send(ws, thread.id, "Monday", message_id="m2")
    assert replied.run is None, "the form is still open, so the run stays paused"
    later = await runner.send(ws, thread.id, "Ten people", message_id="m3")
    assert later.run is None, "with only the form open, a message answers nothing"
    run = await ws.run(paused.run_id)
    assert (run.status, list(run.answers)) == ("paused", ["q1"])
    form = AnswerDeferred(run_id=run.id, tool_call_id="f1", answer=VALUES)
    resumed = started(await runner.answer(ws, form))
    assert resumed.run_id == run.id
    await resumed.wait()
    assert script.tool_returns(1) == ["Monday", str(VALUES)]
    assert script.prompt_texts(1)[-1] == "Ten people", "the message not taken is the prompt"
    assert (await ws.run(run.id)).status == "completed"
    assert (await _starts(ws))[-1] == ("resume", ("m3",))


async def test_a_message_while_only_a_form_is_open_waits_for_its_answer(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(FORM, say("Booked, in metric."))
    runner = runners(make_agent(script, tools=[_form_tools()], output_type=ASKING))
    paused = started(await runner.send(ws, thread.id, "Book a room", message_id="m1"))
    await paused.wait()
    for message_id, text in (("m2", "Use metric"), ("m3", "And a projector")):
        sent = await runner.send(ws, thread.id, text, message_id=message_id)
        assert sent.run is None, "a message answers no form, and starts nothing"
    assert await runner.recover(ws) == [], "nothing is taken while the form is open"
    run = await ws.run(paused.run_id)
    assert (run.status, run.answers) == ("paused", {})
    form = AnswerDeferred(run_id=run.id, tool_call_id="f1", answer=VALUES)
    await started(await runner.answer(ws, form)).wait()
    assert script.tool_returns(1) == [str(VALUES)]
    assert script.prompt_texts(1)[-2:] == ["Use metric", "And a projector"]
    assert await _starts(ws) == [("message", ("m1",)), ("resume", ("m2", "m3"))]
