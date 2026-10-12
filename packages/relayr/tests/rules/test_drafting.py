"""The chat agent drafts rules: `draft_rule` checks a draft, previews it, and proposes it."""

from collections.abc import Callable, Iterator
from typing import Any

from pydantic_ai import Agent, ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.messages import RetryPromptPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo

import artifactr
import artifactr.agent
import artifactr.core as a
import reflexr
import reflexr.workspace as r
from relayr.events import BRIDGED
from relayr.rules import RuleDraft, RuleDrafting
from tests.app_types import Deployed
from tests.rules.test_installer import STORED, draft
from tests.stack import ALICE, KEY

type Step = Callable[[list[str]], tuple[str, dict[str, Any]]]


def script(steps: list[Step]) -> tuple[Callable[..., ModelResponse], list[str]]:
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

    return respond, returned


def drafting(rule: RuleDraft, **args: Any) -> Step:
    return lambda returned: ("draft_rule", {"rule": rule.rule.model_dump(mode="json"), **args})


async def test_the_agent_drafts_rules_as_proposals_with_a_preview() -> None:
    events = {t.event_type: t for t in (*BRIDGED, Deployed)}
    automation = r.Workspaces(
        r.InMemoryStorage(), events=list(events.values()), stored_rules=STORED
    )
    await (await automation.open(*KEY, actor=reflexr.SystemActor())).publish(
        Deployed(service="auth")
    )
    collaboration = artifactr.Workspaces(artifactr.InMemoryStorage())
    alice = await collaboration.open(*KEY, actor=ALICE)
    thread = await alice.create_thread()
    existing = await alice.create(draft("chat:existing"), thread_id=thread.id)
    assert isinstance(existing, a.Applied), "a person creates it directly"
    respond, returned = script(
        [
            drafting(draft(action="shell"), rationale="Tell me."),
            drafting(draft(), rationale="Tell me of deploys."),
            drafting(draft(), rationale="Change it.", artifact_id="art_missing"),
            drafting(
                draft(service="billing"), rationale="Billing too.", artifact_id=existing.artifact_id
            ),
        ]
    )
    capability = RuleDrafting(automation, events, STORED)
    agent = Agent(
        artifactr.agent.function_model(respond),
        deps_type=artifactr.agent.Session[None],
        capabilities=[artifactr.agent.ArtifactWorkspace(types=[RuleDraft]), capability],
    )
    runner = artifactr.agent.Runner(agent, app=None)
    try:
        sent = await runner.send(alice, thread.id, "Tell me whenever auth deploys.")
        assert sent.run is not None
        await sent.run.wait()
    finally:
        await runner.aclose()

    refused, created, missing, edited = returned
    assert refused.startswith("retry: The rule can't be installed: ")
    assert "shell" in refused
    assert created.startswith("Proposed as ")
    assert missing.startswith("retry: rule art_missing")
    assert edited.startswith("Proposed as ")
    new, change = await alice.proposals()
    assert new.rationale is not None
    assert new.rationale.startswith("Tell me of deploys.\n\nIt would have fired 1 times since ")
    assert isinstance(change.change, a.EditArtifact)
    assert change.change.artifact_id == existing.artifact_id
    assert "draft_rule" in capability.get_instructions()
