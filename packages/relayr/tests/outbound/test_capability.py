"""A rule's agent acting in artifactr through `ArtifactrCapability`, with a scripted model."""

import json
from collections.abc import Callable, Iterator
from typing import Any

from pydantic_ai import Agent, ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.messages import RetryPromptPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import reflexr
import reflexr.workspace as r
from reflexr.agent import AgentAction, function_model
from relayr.events import MessagePosted
from relayr.ledger import Ledger
from relayr.outbound import Allowlist, ArtifactrCapability, Outbound
from tests.app_types import Note
from tests.outbound.test_actions import people
from tests.stack import ALICE, KEY, Stack, bridged

ACTING = reflexr.Rule(
    name="app:agent",
    when=reflexr.on(MessagePosted).where(reflexr.F.author.kind.eq("user")),
    then=reflexr.run("agent"),
    retry=reflexr.RetryPolicy(max_attempts=1),
)

type Step = Callable[[list[str]], tuple[str, dict[str, Any]]]
"""A tool call, made from what the calls before it returned."""


def script(steps: list[Step]) -> tuple[FunctionModel, list[str]]:
    """A model that makes each call in turn, then answers; and what each call returned."""
    returned: list[str] = []
    calls: Iterator[Step] = iter(steps)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        for part in messages[-1].parts:
            if isinstance(part, ToolReturnPart):
                returned.append(str(part.content))
            elif isinstance(part, RetryPromptPart):
                returned.append(f"retry: {part.model_response()}")
        step = next(calls, None)
        if step is None:
            return ModelResponse(parts=[TextPart("Done.")])
        return ModelResponse(parts=[ToolCallPart(*step(returned))])

    return function_model(respond), returned


def call(tool: str, **args: Any) -> Step:
    return lambda returned: (tool, args)


def on_note(tool: str, **args: Any) -> Step:
    """A call on the note the second call created."""
    return lambda returned: (tool, {"artifact_id": returned[1], **args})


async def test_an_agent_acts_through_its_tools(ledger: Ledger, stack: Stack) -> None:
    model, returned = script(
        [
            call("create_artifact", kind="nothing", data={}),
            call("create_artifact", kind="note", data={"text": "hi"}),
            on_note("read_artifact"),
            on_note("edit_artifact", path="/text", value="bye", summary="said bye"),
            on_note("edit_artifact", path="/text", value="x", thread_id="thr_other"),
            call("post_notice", content="Made a note."),
            call("post_notice", content="Elsewhere.", thread_id="thr_other"),
            call("create_thread", title="mine"),
            call("send_message", content="Look."),
        ]
    )
    acting: list[AgentAction[Outbound, str]] = []

    async def agent_action(reaction: r.Reaction[Outbound]) -> str:
        return await acting[0](reaction)  # the agent's capability needs the process's adapter

    direct = Allowlist(direct=frozenset({"note"}))
    app = stack.process(
        ledger, rules=[ACTING], actions={"agent": agent_action}, allowlists={"app:agent": direct}
    )
    capability = ArtifactrCapability(app.outbound)
    agent = Agent(model, deps_type=r.Reaction[Outbound], name="agent", capabilities=[capability])
    acting.append(AgentAction(agent))
    alice = await app.collaboration.open(*KEY, actor=ALICE)
    thread = await alice.create_thread()
    await alice.post_message(thread.id, "go")
    await bridged(stack, 1)
    await app.reactor.settle()

    [unknown, note, read, edited, elsewhere, notice, nowhere, thread_refused, turn_refused] = (
        returned
    )
    assert unknown.startswith("retry:")
    assert json.loads(read) == {"kind": "note", "version": 1, "data": {"text": "hi"}}
    assert edited == "Done."
    assert "chain's threads" in elsewhere
    assert notice.startswith("msg_")
    assert "chain's threads" in nowhere
    assert "may not create threads" in thread_refused
    assert "may not start turns" in turn_refused
    assert (await (await people(stack)).get(Note, note)).data.text == "bye"
    assert "proposals for people to review" in capability.get_instructions()
