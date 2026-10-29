"""The chat agent drafts rules: `draft_rule` checks a draft, previews it, and proposes it."""

import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from pydantic_ai import Agent, ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.messages import RetryPromptPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo

import artifactr
import artifactr.agent
import artifactr.core as a
import reflexr
import reflexr.workspace as r
from artifactr.workspace import direct_writes
from relayr.events import BRIDGED
from relayr.rules import RuleDraft, RuleDrafting
from tests.app_types import Deployed
from tests.rules.drafts import STORED, draft
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
    readers: list[reflexr.Actor] = []

    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: reflexr.Actor, access: r.Access
    ) -> bool:
        if access.action == "reflexr:read_events":
            readers.append(actor)
        return True

    events = {t.event_type: t for t in (*BRIDGED, Deployed)}
    automation = r.Workspaces(
        r.InMemoryStorage(), events=list(events.values()), stored_rules=STORED, authorize=authorize
    )
    reflexr_ = await automation.open(*KEY, actor=reflexr.SystemActor())
    await reflexr_.publish(Deployed(service="auth"))
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
                draft("chat:existing", service="billing"),
                rationale="Billing too.",
                artifact_id=existing.artifact_id,
            ),
            drafting(draft(), rationale="Rename it.", artifact_id=existing.artifact_id),
        ]
    )
    capability = RuleDrafting(automation, events)
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

    refused, created, missing, edited, renamed = returned
    assert refused.startswith("retry: The rule can't be installed: ")
    assert "shell" in refused
    assert created.startswith("Proposed as ")
    assert missing.startswith("retry: rule art_missing")
    assert renamed.startswith("retry: A rule's name can't change: keep chat:existing")
    assert edited.startswith("Proposed as ")
    new, change = await alice.proposals()
    assert new.rationale is not None
    assert new.rationale.startswith("Tell me of deploys.\n\nIt would have fired 1 time since ")
    assert isinstance(change.change, a.EditArtifact)
    assert change.change.artifact_id == existing.artifact_id
    assert readers, "the preview reads the log"
    assert all(reader == reflexr.UserActor(id="alice") for reader in readers), "as the person"
    assert "draft_rule" in capability.get_instructions()
    assert len(await reflexr_.read()) == 1, "the preview wrote nothing"
    assert await reflexr_.runs() == []


@pytest.mark.parametrize(
    ("actor", "previewed"),
    [
        (a.ExternalAgentActor(client_id="mcp", on_behalf_of=ALICE), True),
        (a.ExternalAgentActor(client_id="service"), False),
    ],
    ids=["a person's client", "a client for no one"],
)
async def test_a_draft_is_previewed_for_a_person(actor: a.Actor, previewed: bool) -> None:
    events = {t.event_type: t for t in (*BRIDGED, Deployed)}
    automation = r.Workspaces(
        r.InMemoryStorage(), events=list(events.values()), stored_rules=STORED
    )
    client = await artifactr.Workspaces(artifactr.InMemoryStorage()).open(*KEY, actor=actor)
    thread = await client.create_thread()
    respond, returned = script([drafting(draft(), rationale="Tell me.")])
    agent = Agent(
        artifactr.agent.function_model(respond),
        deps_type=artifactr.agent.Session[None],
        capabilities=[RuleDrafting(automation, events)],
    )
    runner = artifactr.agent.Runner(agent, app=None)
    try:
        sent = await runner.send(client, thread.id, "Tell me whenever auth deploys.")
        assert sent.run is not None
        await sent.run.wait()
    finally:
        await runner.aclose()
    [answer] = returned
    if previewed:
        assert answer.startswith("Proposed as ")
    else:
        assert answer.startswith("retry: Only a person can ask for a rule; this turn acts for no")


async def test_a_rule_refused_three_times_is_still_drafted() -> None:
    events = {t.event_type: t for t in (*BRIDGED, Deployed)}
    automation = r.Workspaces(
        r.InMemoryStorage(), events=list(events.values()), stored_rules=STORED
    )
    alice = await artifactr.Workspaces(artifactr.InMemoryStorage()).open(*KEY, actor=ALICE)
    thread = await alice.create_thread()

    def not_a_rule(returned: list[str]) -> tuple[str, dict[str, Any]]:
        return "draft_rule", {"rule": {"name": "x"}, "rationale": "?"}  # its arguments refused

    shell = drafting(draft(action="shell"), rationale="Tell me.")  # the draft refused
    respond, returned = script(
        [not_a_rule, not_a_rule, shell, drafting(draft(), rationale="Tell me.")]
    )
    agent = Agent(
        artifactr.agent.function_model(respond),
        deps_type=artifactr.agent.Session[None],
        capabilities=[RuleDrafting(automation, events)],
    )
    runner = artifactr.agent.Runner(agent, app=None)
    try:
        sent = await runner.send(alice, thread.id, "Tell me whenever auth deploys.")
        assert sent.run is not None
        await sent.run.wait()
    finally:
        await runner.aclose()
    *refused, drafted = returned
    assert [answer.split(":")[0] for answer in refused] == ["retry"] * 3
    assert drafted.startswith("Proposed as "), "within the tool's retries"


async def test_a_rule_sent_as_a_string_of_json_is_read_as_its_object() -> None:
    events = {t.event_type: t for t in (*BRIDGED, Deployed)}
    automation = r.Workspaces(
        r.InMemoryStorage(), events=list(events.values()), stored_rules=STORED
    )
    alice = await artifactr.Workspaces(artifactr.InMemoryStorage()).open(*KEY, actor=ALICE)
    thread = await alice.create_thread()
    rule = json.dumps(draft().rule.model_dump(mode="json"))

    def as_text(returned: list[str]) -> tuple[str, dict[str, Any]]:
        return "draft_rule", {"rule": rule, "rationale": "Tell me."}

    def not_json(returned: list[str]) -> tuple[str, dict[str, Any]]:
        return "draft_rule", {"rule": "a rule", "rationale": "Tell me."}

    def too_deep(returned: list[str]) -> tuple[str, dict[str, Any]]:
        return "draft_rule", {"rule": "[" * 100_000, "rationale": "Tell me."}

    respond, returned = script([not_json, too_deep, as_text])
    agent = Agent(
        artifactr.agent.function_model(respond),
        deps_type=artifactr.agent.Session[None],
        capabilities=[RuleDrafting(automation, events)],
    )
    runner = artifactr.agent.Runner(agent, app=None)
    try:
        sent = await runner.send(alice, thread.id, "Tell me whenever auth deploys.")
        assert sent.run is not None
        await sent.run.wait()
    finally:
        await runner.aclose()
    *refused, drafted = returned
    assert [answer[:7] for answer in refused] == ["retry: "] * 2, "a string that isn't JSON is none"
    assert drafted.startswith("Proposed as ")


def test_drafting_needs_stored_rules() -> None:
    with pytest.raises(ValueError, match="no stored rules"):
        RuleDrafting(r.Workspaces(r.InMemoryStorage()), {})


def test_a_rule_draft_waits_for_review_in_auto_by_default() -> None:
    assert direct_writes((RuleDraft,)).default == ()
