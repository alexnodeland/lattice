"""portalr's provider (lattice RFC-0014, portalr ADR-0097): a tenant's commands, each checked as
portalr's routes check it before a reader is asked, answering what the routes answer."""

import json
from dataclasses import replace
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from grantr.core import Forbidden, User
from grantr.grants import Grants
from lattice_core.capabilities import CallContext, PersonCaller, Scope
from lattice_core.taint import Clean
from portalr.capabilities import OPERATORS, PortalrProvider
from portalr.commands import CATALOG
from portalr.invites import Invite
from portalr.readers import Readers
from portalr.readers.analytics import Analytics
from tests.fastapi.conftest import Stack
from tests.fastapi.test_router import SESSION, _stamped_trace
from tests.tools import json as answer

ACME = Scope(tenant_id="acme")
WINDOW = {"start": "2026-10-12T00:00:00Z", "end": "2026-10-12T01:00:00Z"}
DAYS = {"start": "2026-10-01T00:00:00Z", "end": "2026-10-12T00:00:00Z"}
READS: dict[str, dict[str, Any]] = {
    "portalr.list_traces": WINDOW,
    "portalr.read_trace": {"trace_id": "t1"},
    "portalr.read_logs": WINDOW,
    "portalr.read_log_line": {"record_id": "1792800000-0123456789abcdef-0"},
    "portalr.read_metrics": {**WINDOW, "metric": "turn_latency"},
    "portalr.read_scores": WINDOW,
    "portalr.read_feedback": DAYS,
    "portalr.read_adoption": DAYS,
    "portalr.read_spend": {},
    "portalr.read_usage": DAYS,
}


def context(person: str = "alice") -> CallContext:
    return CallContext(
        scope=ACME,
        caller=PersonCaller(id=person),
        taint=Clean(),
        correlation_id="c1",
        surface="mcp",
    )


async def call(bound: PortalrProvider, name: str, person: str = "alice", **arguments: Any) -> Any:
    [capability] = [c for c in bound.capabilities(ACME) if c.name == name]
    output = (await bound.call(capability, arguments, context(person))).output
    assert isinstance(output, str)
    return json.loads(output)


def unreachable() -> Analytics:
    refuse = httpx.MockTransport(lambda _request: httpx.Response(503))
    return Analytics("http://clickhouse", b"k" * 32, reader=httpx.AsyncClient(transport=refuse))


def test_it_offers_a_tenants_commands_and_inviting_only_with_an_invite(
    grants: Grants, invite: Invite
) -> None:
    tenants = {c.name for c in CATALOG.commands()} - OPERATORS
    with_invite = PortalrProvider(grants, Readers(), invite=invite)
    assert {c.name for c in with_invite.capabilities(ACME)} == tenants
    without = PortalrProvider(grants, Readers())
    assert {c.name for c in without.capabilities(ACME)} == tenants - {"portalr.invite_member"}
    assert list(without.commands()) == list(CATALOG.commands()), "it is the catalog too"


@pytest.mark.parametrize("name", sorted(READS))
async def test_each_read_answers_unconfigured_without_its_reader(grants: Grants, name: str) -> None:
    bound = PortalrProvider(grants, Readers())
    assert await call(bound, name, **READS[name]) == {"status": "unconfigured"}


@pytest.mark.parametrize("name", sorted(READS))
async def test_each_read_asks_its_reader_where_there_is_one(
    grants: Grants, stack: Stack, name: str
) -> None:
    readers = replace(stack.readers(), analytics=unreachable())
    bound = PortalrProvider(grants, readers)
    assert (await call(bound, name, **READS[name]))["status"] != "unconfigured"


async def test_a_read_is_refused_to_whoever_lacks_its_action_on_the_tenant(grants: Grants) -> None:
    bound = PortalrProvider(grants, Readers())
    with pytest.raises(Forbidden, match="may not portalr:read_telemetry in acme"):
        await call(bound, "portalr.read_logs", person="bob", **WINDOW)


async def test_an_analytics_session_is_the_operators_alone(grants: Grants, stack: Stack) -> None:
    stack.tempo.paths["/api/v2/traces/t1"] = answer(_stamped_trace())
    stack.tempo.paths["/api/search"] = answer({"traces": []})
    bound = PortalrProvider(grants, stack.readers())
    read = await call(bound, "portalr.read_trace", trace_id="t1")
    assert SESSION not in json.dumps(read)
    with pytest.raises(Forbidden, match="only operators"):
        await call(bound, "portalr.list_traces", **WINDOW, analytics_session=SESSION)
    await grants.grant_operator("alice", by=User(id="ops"))
    assert SESSION in json.dumps(await call(bound, "portalr.read_trace", trace_id="t1"))
    searched = await call(bound, "portalr.list_traces", **WINDOW, analytics_session=SESSION)
    assert searched == {"status": "ok", "data": []}


async def test_a_member_is_invited_once_and_again_changes_nothing(
    grants: Grants, invite: Invite, invited: list[str]
) -> None:
    bound = PortalrProvider(grants, Readers(), invite=invite)
    made = await call(bound, "portalr.invite_member", email="dana@acme.test")
    assert made == {"tenant": "acme", "user": "dana"}
    assert await grants.member("acme", "dana") is not None
    again = await call(bound, "portalr.invite_member", email="dana@acme.test")
    assert again == made
    assert invited == ["dana@acme.test", "dana@acme.test"]


async def test_a_call_is_refused_unless_offered_well_formed_and_its_record_an_id(
    grants: Grants,
) -> None:
    bound = PortalrProvider(grants, Readers())
    commands = {c.name: c.capability for c in CATALOG.commands()}
    for name in ("portalr.create_tenant", "portalr.invite_member"):
        with pytest.raises(ValueError, match=f"{name} isn't a command this provider offers"):
            await bound.call(commands[name], {}, context())
    with pytest.raises(ValidationError):
        await call(bound, "portalr.read_spend", limit=3)
    with pytest.raises(ValueError, match="isn't a log record's id"):
        await call(bound, "portalr.read_log_line", record_id="nope")
