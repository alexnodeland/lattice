"""A rule's agent writing to its tracker through `TrackerCapability`, with a scripted model."""

import json
from collections.abc import Callable, Iterator
from typing import Any

from pydantic_ai import Agent, ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.messages import RetryPromptPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo

import reflexr.workspace as r
from reflexr.agent import function_model
from relayr.ledger import Ledger
from relayr.trackers import FakeTracker, Refused, TrackerCapability
from tests.clock import FakeClock
from tests.trackers.conftest import PROJECT, Runs, Tenant, connector

type Step = Callable[[], tuple[str, dict[str, Any]]]


def script(steps: list[Step]) -> tuple[Any, list[str]]:
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
        return ModelResponse(parts=[ToolCallPart(*step())])

    return function_model(respond), returned


def call(tool: str, **args: Any) -> Step:
    return lambda: (tool, args)


def refused(tracker: FakeTracker, tool: str, **args: Any) -> Step:
    """A call the tracker refuses."""

    def step() -> tuple[str, dict[str, Any]]:
        tracker.fail(Refused("invalid"))
        return tool, args

    return step


def deleted(tracker: FakeTracker, tool: str, **args: Any) -> Step:
    """A call after a person deleted the item."""

    def step() -> tuple[str, dict[str, Any]]:
        tracker.delete(tracker.items_in(PROJECT)[0].ref)
        return tool, args

    return step


async def test_an_agent_files_and_changes_items_through_its_tools(
    runs: Runs, tracker: FakeTracker
) -> None:
    model, returned = script(
        [
            call("file_item", key="incident/7", title="Payments down", priority="urgent"),
            refused(tracker, "file_item", key="incident/8", title="t"),
            call("comment_on_item", key="incident/7", body="<p>Paged.</p>"),
            refused(tracker, "comment_on_item", key="incident/7", body="<p>Again.</p>"),
            call("comment_on_item", key="incident/9", body="<p>Nothing filed.</p>"),
            call("set_item_state", key="incident/7", state="started"),
            refused(tracker, "set_item_state", key="incident/7", state="done"),
            call("read_item", key="incident/7"),
            refused(tracker, "read_item", key="incident/7"),
            deleted(tracker, "read_item", key="incident/7"),
            call("file_item", key="incident/7", title="Payments down"),
        ]
    )
    capability = TrackerCapability(runs.trackers)
    agent = Agent(model, deps_type=r.Reaction[None], capabilities=[capability], retries=5)
    await agent.run("A deploy failed.", deps=await runs.reaction())
    [filed, *rest] = returned
    assert filed == "Filed as OPS-1: https://tracker.test/ops/1"
    assert rest[:6] == [
        "retry: invalid\n\nFix the errors and try again.",
        "Done.",
        "retry: invalid\n\nFix the errors and try again.",
        "retry: no item is filed by incident/9; file one first\n\nFix the errors and try again.",
        "Done.",
        "retry: invalid\n\nFix the errors and try again.",
    ]
    read = json.loads(rest[6])
    assert (read["title"], read["state"], read["priority"]) == (
        "Payments down",
        "started",
        "urgent",
    )
    assert rest[7:] == [
        "retry: invalid\n\nFix the errors and try again.",
        "retry: the item incident/7 filed was deleted\n\nFix the errors and try again.",
        "A person deleted the item incident/7 filed; it isn't filed again.",
    ]
    assert capability.get_instructions().startswith("You can file items")


async def test_an_agent_whose_rule_may_not_write_is_told(
    runs: Runs, ledger: Ledger, tracker: FakeTracker, tenant: Tenant, clock: FakeClock
) -> None:
    model, returned = script([call("file_item", key="k", title="t")])
    capability = TrackerCapability(connector(ledger, tracker, tenant, clock, allowlists={}))
    agent = Agent(model, deps_type=r.Reaction[None], capabilities=[capability], retries=5)
    await agent.run("A deploy failed.", deps=await runs.reaction())
    assert returned == [
        "retry: ops:file may not write to its tracker\n\nFix the errors and try again."
    ]
    assert tracker.created == 0


async def test_an_agent_refused_may_file_by_the_same_key_again(
    runs: Runs, tracker: FakeTracker
) -> None:
    model, returned = script(
        [
            refused(tracker, "file_item", key="incident/7", title="Payments down"),
            call("file_item", key="incident/7", title="Payments down"),
        ]
    )
    capability = TrackerCapability(runs.trackers)
    agent = Agent(model, deps_type=r.Reaction[None], capabilities=[capability], retries=5)
    await agent.run("A deploy failed.", deps=await runs.reaction())
    assert returned == [
        "retry: invalid\n\nFix the errors and try again.",
        "Filed as OPS-1: https://tracker.test/ops/1",
    ]
