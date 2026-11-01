"""reflexr's provider (lattice RFC-0014, reflexr ADR-0068): its catalog bound to its workspaces,
each call run in the call's workspace as the call's actor, as reflexr's own surfaces run it."""

import json
from datetime import timedelta
from typing import Any, Literal

import pytest
from pydantic import ValidationError

from lattice_core.capabilities import (
    CallContext,
    Capability,
    PersonCaller,
    Provider,
    RunCaller,
    Scope,
    SessionCaller,
    Via,
)
from lattice_core.commands import Commands
from lattice_core.taint import Clean
from reflexr import Actor, F, Feedback, Rule, by, on, run
from reflexr.commands import (
    CATALOG,
    READ_LIMIT,
    CommandRejected,
    ReflexrProvider,
    actor_for,
    provider,
)
from reflexr.core import ExternalAgentActor, Forbidden, NotFound, StoredRules, UserActor
from reflexr.workspace import Access, InMemoryStorage, Reaction, Reactor, Workspaces
from tests.event_types import Deploy, ServiceError

deploys = Rule(name="app:deploys", when=on(Deploy), scope=by(F.service), then=run("note"))
CHAT = StoredRules(actions={"note": None}, namespaces={"chat"})
ALICE = PersonCaller(id="alice")


class ProviderUseful(Feedback, name="provider_useful", targets={"run"}):
    useful: bool


async def note(reaction: Reaction[None]) -> Literal["noted"]:
    if reaction.scope["service"] == "billing":
        raise RuntimeError("billing is down")
    return "noted"


def context(caller: Any = ALICE, workspace: str = "prod", via: Via | None = None) -> CallContext:
    return CallContext(
        scope=Scope(tenant_id="acme", workspace_id=workspace),
        caller=caller,
        taint=Clean(),
        correlation_id="corr",
        surface="portalr",
        via=via,
    )


def capability(name: str) -> Capability:
    [found] = [c.capability for c in CATALOG.commands() if c.name == name]
    return found


@pytest.fixture
def workspaces() -> Workspaces:
    return Workspaces(
        InMemoryStorage(), events=[Deploy, ServiceError], rules=[deploys], stored_rules=CHAT
    )


async def call(bound: ReflexrProvider, name: str, **arguments: Any) -> Any:
    result = await bound.call(capability(name), arguments, context())
    assert isinstance(result.output, str)
    return json.loads(result.output)


def chat_rule(service: str = "auth") -> dict[str, Any]:
    rule = Rule(
        name="chat:deploys",
        when=on(Deploy).where(service=service).at_most(10, per=timedelta(hours=1)),
        then=run("note"),
        ordering="none",
        timeout=timedelta(minutes=1),
    )
    return rule.model_dump(mode="json")


def test_a_call_acts_as_its_client_or_its_caller() -> None:
    assert actor_for(context()) == UserActor(id="alice")
    claude = Via(connection_id="conn_1", client_name="Claude", surface="mcp")
    assert actor_for(context(via=claude)) == ExternalAgentActor(
        client_id="conn_1", name="Claude", on_behalf_of=UserActor(id="alice")
    )
    triage = RunCaller(id="run_1", agent="triage", on_behalf_of="bob")
    assert actor_for(context(triage)) == ExternalAgentActor(
        client_id="agent:triage", name="triage", on_behalf_of=UserActor(id="bob")
    )
    session = SessionCaller(id="s1")
    assert actor_for(context(session)) == ExternalAgentActor(
        client_id="session:s1", name="code session", on_behalf_of=None
    )


def test_the_provider_offers_every_command(workspaces: Workspaces) -> None:
    bound = provider(workspaces)
    assert isinstance(bound, Provider)
    assert isinstance(bound, Commands)
    assert bound.kind == "command"
    offered = [c.name for c in bound.capabilities(Scope(tenant_id="acme", workspace_id="prod"))]
    assert offered == [c.name for c in CATALOG.commands()]


async def test_events_runs_and_rules_through_the_provider(workspaces: Workspaces) -> None:
    bound = provider(workspaces)
    published = await call(
        bound, "reflexr.publish_event", event={"type": "app:deploy.finished", "service": "auth"}
    )
    assert published["seq"] == 1
    await call(
        bound, "reflexr.publish_event", event={"type": "app:deploy.finished", "service": "billing"}
    )
    await Reactor(workspaces, actions={"note": note}).settle()
    envelopes = await call(bound, "reflexr.read_events", types=["app:deploy.finished"])
    assert [e["seq"] for e in envelopes] == [1, 2]
    assert envelopes[0]["actor"] == {"kind": "user", "id": "alice", "name": None}
    assert len(await call(bound, "reflexr.read_events", last=1)) == 1
    assert READ_LIMIT == 50
    [rule] = await call(bound, "reflexr.list_rules")
    assert rule["name"] == "app:deploys"
    [status] = await call(bound, "reflexr.rule_status")
    assert status["rule"] == "app:deploys"
    assert await call(bound, "reflexr.schedule_status") == []
    failing, done = await call(bound, "reflexr.list_runs")
    assert (done["status"], failing["status"]) == ("succeeded", "retrying")
    [billing] = await call(bound, "reflexr.list_runs", scope_key=["billing"])
    assert billing["id"] == failing["id"]
    assert (await call(bound, "reflexr.get_run", run_id=done["id"]))["output"] == "noted"
    retried = await call(bound, "reflexr.retry_run", run_id=failing["id"])
    assert retried["run"]["status"] == "pending"
    skipped = await call(bound, "reflexr.skip_run", run_id=failing["id"], reason="dup")
    assert skipped["run"]["status"] == "skipped"
    with pytest.raises(CommandRejected, match="which is skipped") as refused:
        await call(bound, "reflexr.cancel_run", run_id=failing["id"])
    assert refused.value.payload()["type"] == "invalid_state"
    replayed = await call(bound, "reflexr.replay_rule", rule="app:deploys")
    assert replayed["progress"]["generation"] == 1
    feedback = await call(
        bound,
        "reflexr.give_feedback",
        feedback_type="provider_useful",
        target={"kind": "run", "run_id": done["id"]},
        value={"useful": True},
    )
    assert feedback["type"] == "recorded"
    assert await call(bound, "reflexr.list_dead_letters") == []


async def test_a_run_waiting_to_run_is_cancelled(workspaces: Workspaces) -> None:
    bound = provider(workspaces)
    await call(
        bound, "reflexr.publish_event", event={"type": "app:deploy.finished", "service": "auth"}
    )
    await Reactor(workspaces, actions={"note": note}).evaluate()
    [pending] = await call(bound, "reflexr.list_runs")
    cancelled = await call(bound, "reflexr.cancel_run", run_id=pending["id"], reason="not now")
    assert cancelled["run"]["status"] == "cancelled"


async def test_stored_rules_are_installed_updated_and_archived(workspaces: Workspaces) -> None:
    bound = provider(workspaces)
    installed = await call(bound, "reflexr.install_rule", rule=chat_rule(), provenance={"a": 1})
    assert (installed["rule"], installed["version"]) == ("chat:deploys", 1)
    updated = await call(
        bound, "reflexr.update_rule", rule=chat_rule("billing"), expected_version=1
    )
    assert updated["version"] == 2
    got = await call(bound, "reflexr.get_rule", rule="chat:deploys")
    assert got["version"] == 2
    history = await call(bound, "reflexr.rule_history", rule="chat:deploys")
    assert [e["event"]["type"] for e in history] == ["reflexr:rule_installed"] * 2
    archived = await call(
        bound, "reflexr.archive_rule", rule="chat:deploys", expected_version=2, reason="done"
    )
    assert archived["version"] == 3


async def test_what_the_workspace_refuses_is_raised(workspaces: Workspaces) -> None:
    bound = provider(workspaces)
    with pytest.raises(NotFound):
        await call(bound, "reflexr.get_rule", rule="chat:nope")
    with pytest.raises(CommandRejected) as refused:
        await call(bound, "reflexr.archive_rule", rule="chat:nope")
    assert refused.value.payload()["type"] == "not_found"
    with pytest.raises(ValidationError):
        await call(bound, "reflexr.get_run")
    unknown = capability("reflexr.get_run").model_copy(update={"name": "reflexr.dance"})
    with pytest.raises(ValueError, match=r"reflexr\.dance isn't one of reflexr's commands"):
        await bound.call(unknown, {}, context())


async def test_a_call_is_checked_as_its_actor() -> None:
    seen: list[tuple[Actor, str]] = []

    async def only_alice(
        _tenant: str, _workspace: str | None, actor: Actor, access: Access
    ) -> bool:
        seen.append((actor, access.action))
        return actor == UserActor(id="alice")

    guarded = Workspaces(InMemoryStorage(), events=[Deploy], rules=[deploys], authorize=only_alice)
    bound = provider(guarded)
    assert await call(bound, "reflexr.list_runs") == []
    assert (UserActor(id="alice"), "reflexr:read_runs") in seen
    with pytest.raises(Forbidden):
        await bound.call(capability("reflexr.list_runs"), {}, context(PersonCaller(id="bob")))
    elsewhere = provider(guarded, actor=lambda _context: UserActor(id="bob"))
    with pytest.raises(Forbidden):
        await elsewhere.call(capability("reflexr.list_rules"), {}, context())
