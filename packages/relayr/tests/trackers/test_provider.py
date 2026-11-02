"""relayr's provider (lattice RFC-0014, relayr ADR-0043): its two reads, each asked of reflexr's
`authorize` in the call's workspace, as the call's actor, answering what relayr's routes do."""

import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic import ValidationError

import reflexr.workspace as r
from lattice_core.capabilities import CallContext, PersonCaller, Scope, Via
from lattice_core.taint import Clean
from reflexr.core import Actor, Forbidden
from relayr.capabilities import FILED, STATUS, RelayrProvider
from relayr.commands import CATALOG
from relayr.ledger import Ledger
from relayr.trackers.events import TRACKED
from tests.app_types import Deployed
from tests.clock import FakeClock
from tests.trackers.conftest import KEY, TENANT
from tests.trackers.following import Following, following

HERE = Scope(tenant_id=TENANT, workspace_id=KEY.workspace_id)


@dataclass
class Asked:
    """What reflexr's `authorize` was asked, by whom, and what it refuses."""

    refused: set[str] = field(default_factory=set[str])
    asked: list[tuple[str | None, Actor, str]] = field(
        default_factory=list[tuple[str | None, Actor, str]]
    )

    async def authorize(
        self, _tenant: str, workspace: str | None, actor: Actor, access: r.Access
    ) -> bool:
        self.asked.append((workspace, actor, access.action))
        return access.action not in self.refused


@pytest.fixture
def made(ledger: Ledger, clock: FakeClock) -> Following:
    return following(ledger, clock)


def provider(made: Following, asked: Asked) -> RelayrProvider:
    workspaces = r.Workspaces(
        made.storage, events=(Deployed, *TRACKED), clock=made.clock, authorize=asked.authorize
    )
    return RelayrProvider(made.trackers, workspaces)


def context(scope: Scope = HERE) -> CallContext:
    claude = Via(connection_id="con_1", client_name="Claude", surface="mcp")
    return CallContext(
        scope=scope,
        caller=PersonCaller(id="alice"),
        taint=Clean(),
        correlation_id="c1",
        surface="mcp",
        via=claude,
    )


async def call(bound: RelayrProvider, name: str, scope: Scope = HERE) -> Any:
    [capability] = [c for c in bound.capabilities(scope) if c.name == name]
    output = (await bound.call(capability, {}, context(scope))).output
    assert isinstance(output, str)
    return json.loads(output)


async def test_it_offers_relayrs_two_reads_and_is_the_catalog(made: Following) -> None:
    bound = provider(made, Asked())
    assert [c.name for c in bound.capabilities(HERE)] == [FILED, STATUS]
    assert list(bound.commands()) == list(CATALOG.commands())


async def test_each_read_answers_what_relayrs_routes_do_as_the_calls_actor(
    made: Following,
) -> None:
    asked = Asked()
    bound = provider(made, asked)
    filed = await made.filed("dead-letter/a", "a fails")
    items = await call(bound, FILED)
    assert items["tracker"] == "fake"
    assert [item["name"] for item in items["items"]] == [filed.name]
    status = await call(bound, STATUS)
    assert (status["integration"], status["filed"]) == ("tracker:fake", 1)
    actions = [action for _workspace, _actor, action in asked.asked]
    assert "reflexr:read_runs" in actions
    assert "reflexr:read_dead_letters" in actions
    [(_workspace, actor, _action), *_] = asked.asked
    assert actor.participant == "external_agent:con_1", "the client, acting for the person"


async def test_a_read_the_workspace_refuses_is_refused(made: Following) -> None:
    bound = provider(made, Asked(refused={"reflexr:read_dead_letters"}))
    with pytest.raises(Forbidden):
        await call(bound, STATUS)
    assert (await call(bound, FILED))["items"] == []


async def test_a_call_is_refused_unless_it_is_relayrs_in_a_workspace_with_no_arguments(
    made: Following,
) -> None:
    bound = provider(made, Asked())
    [filed, _status] = bound.capabilities(HERE)
    with pytest.raises(ValueError, match="is called in a workspace, and names none"):
        await bound.call(filed, {}, context(Scope(tenant_id=TENANT)))
    with pytest.raises(ValidationError):
        await bound.call(filed, {"limit": 3}, context())
    other = filed.model_copy(update={"name": "relayr.dance"})
    with pytest.raises(ValueError, match=r"relayr\.dance isn't one of relayr's commands"):
        await bound.call(other, {}, context())
