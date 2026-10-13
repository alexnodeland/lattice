from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from grantr.core import AuditEntry, Forbidden, Invalid, Member, Subject, User
from grantr.grants import Grants
from portalr.fastapi import portalr_router
from portalr.invites import Invite, InviteFailed
from portalr.readers import Readers
from tests.fastapi.conftest import ALICE, SITE, Stack, app_for, resolve_actor, seeded
from tests.tools import fails, json

WINDOW = {"start": "2026-10-12T00:00:00Z", "end": "2026-10-12T01:00:00Z"}


def headers(user: str, tenant: str | None = "acme") -> dict[str, str]:
    return {"x-user": user} | ({"x-tenant": tenant} if tenant else {})


async def test_a_tenant_admin_reads_their_tenants_traces(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    stack.tempo.paths["/api/search"] = json(
        {"traces": [{"traceID": "t1", "startTimeUnixNano": "1"}]}
    )
    response = await client.get(
        "/v1/traces", params={**WINDOW, "session": "thr_1"}, headers=headers("alice")
    )
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "data": [
            {
                "trace_id": "t1",
                "root_service": None,
                "root_name": None,
                "start_ns": 1,
                "duration_ms": None,
            }
        ],
    }
    assert stack.tempo.last.url.params["q"].startswith('{ span.tenant.id = "acme"')


async def test_every_read_is_refused_without_the_tenants_grant(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    reads = ["/v1/traces", "/v1/traces/t1", "/v1/logs", "/v1/scores", "/v1/spend"]
    for path in reads:
        for who, tenant in (("bob", "acme"), ("carol", "acme"), ("alice", "globex")):
            response = await client.get(
                path, params={**WINDOW, "metric": "failed_turns"}, headers=headers(who, tenant)
            )
            assert response.status_code == 403, (path, who, tenant)
            assert response.json()["detail"]["type"] == "forbidden"
    assert not any(tool.requests for tool in vars(stack).values())


async def test_a_caller_bound_to_one_tenant_reads_only_it(client: httpx.AsyncClient) -> None:
    bound = {**headers("alice", "acme"), "x-key-tenant": "globex"}
    response = await client.get("/v1/logs", params=WINDOW, headers=bound)
    assert response.status_code == 403
    assert response.json()["detail"]["message"] == "this caller's key is for another tenant"


async def test_a_read_names_its_tenant(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/logs", params=WINDOW, headers=headers("alice", tenant=None))
    assert response.status_code == 400
    assert response.json()["detail"]["type"] == "tenant_required"


async def test_a_caller_must_be_known(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/logs", params=WINDOW)
    assert response.status_code == 401
    assert response.json()["detail"] == {"type": "unauthorized", "message": "no caller"}


async def test_each_tools_read(client: httpx.AsyncClient, stack: Stack) -> None:
    stack.tempo.paths["/api/v2/traces/t1"] = json({"trace": {"resourceSpans": []}})
    stack.loki.paths["/loki/api/v1/query_range"] = json({"data": {"result": []}})
    stack.prometheus.paths["/api/v1/query_range"] = json({"data": {"result": []}})
    stack.langfuse.paths["/api/public/v2/observations"] = json({"data": []})
    stack.litellm.paths["/team/info"] = json({"team_info": {"team_id": "tenant-acme", "spend": 2}})
    alice = headers("alice")
    assert (await client.get("/v1/traces/t1", headers=alice)).json() == {
        "status": "ok",
        "data": None,
    }
    assert (await client.get("/v1/logs", params=WINDOW, headers=alice)).json() == {
        "status": "ok",
        "data": [],
    }
    metrics = await client.get(
        "/v1/metrics", params={**WINDOW, "metric": "turn_latency"}, headers=alice
    )
    assert metrics.json() == {"status": "ok", "data": []}
    assert stack.prometheus.last.url.params["tenant_id"] == "acme"
    assert (await client.get("/v1/scores", params=WINDOW, headers=alice)).json() == {
        "status": "ok",
        "data": [],
    }
    assert (await client.get("/v1/spend", headers=alice)).json() == {
        "status": "ok",
        "data": {"spend": 2.0, "max_budget": None, "budget_duration": None},
    }


async def test_a_tool_that_is_down_fails_only_its_own_read(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    stack.loki.paths["/loki/api/v1/query_range"] = fails()
    stack.langfuse.paths["/api/public/v2/observations"] = json({"data": []})
    alice = headers("alice")
    assert (await client.get("/v1/logs", params=WINDOW, headers=alice)).json() == {
        "status": "unavailable",
        "reason": "loki didn't answer: ConnectError",
    }
    assert (await client.get("/v1/scores", params=WINDOW, headers=alice)).json()["status"] == "ok"


async def test_a_tool_the_application_doesnt_run_is_unconfigured(grants: Grants, ui: Path) -> None:
    transport = httpx.ASGITransport(app=app_for(grants, Readers(), None, ui))
    async with httpx.AsyncClient(transport=transport, base_url="http://app/portalr") as client:
        alice, ops = headers("alice"), headers("ops", tenant=None)
        for path in ("/v1/traces", "/v1/traces/t1", "/v1/logs", "/v1/scores", "/v1/spend"):
            response = await client.get(
                path, params={**WINDOW, "metric": "failed_turns"}, headers=alice
            )
            assert response.json() == {"status": "unconfigured"}, path
        metrics = await client.get(
            "/v1/metrics", params={**WINDOW, "metric": "failed_turns"}, headers=alice
        )
        assert metrics.json() == {"status": "unconfigured"}
        tenants = (await client.get("/v1/deployment/tenants", headers=ops)).json()
        assert tenants["spend"] == {"status": "unconfigured"}
        assert (
            await client.get("/v1/deployment/links", params={"trace_id": "t1"}, headers=ops)
        ).json() == {
            "langfuse_trace": None,
            "langfuse_session": None,
            "grafana_trace": None,
            "grafana_logs": None,
        }
        # Without Supabase's admin API, there is no invitation.
        invite = await client.post("/v1/invites", json={"email": "dan@acme.com"}, headers=alice)
        assert invite.status_code in (404, 405)
        assert (await client.get("/config.json")).json()["readers"] == dict.fromkeys(
            ("tempo", "loki", "prometheus", "langfuse", "litellm", "grafana"), False
        )


async def test_an_operator_reads_every_tenant_and_its_spend(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    stack.litellm.paths["/team/list"] = json([{"team_id": "tenant-acme", "spend": 3}])
    response = await client.get("/v1/deployment/tenants", headers=headers("ops", tenant=None))
    assert response.json() == {
        "tenants": ["acme", "globex"],
        "spend": {
            "status": "ok",
            "data": [{"tenant": "acme", "spend": 3.0, "max_budget": None, "budget_duration": None}],
        },
    }


async def test_an_operator_gets_deep_links(client: httpx.AsyncClient) -> None:
    params = {"trace_id": "t1", "session_id": "thr_1", "run_id": "run_1"}
    links = (
        await client.get("/v1/deployment/links", params=params, headers=headers("ops", None))
    ).json()
    assert links["langfuse_trace"] == "http://langfuse/project/p1/traces/t1"
    assert links["langfuse_session"] == "http://langfuse/project/p1/sessions/thr_1"
    assert links["grafana_trace"].startswith("http://grafana/explore?left=")
    assert links["grafana_logs"].startswith("http://grafana/explore?left=")


@pytest.mark.parametrize("path", ["/v1/deployment/tenants", "/v1/deployment/links"])
async def test_only_operators_read_across_tenants(client: httpx.AsyncClient, path: str) -> None:
    for who in ("alice", "bob", "carol"):
        response = await client.get(path, headers=headers(who))
        assert response.status_code == 403, who


async def test_an_admin_invites_someone_who_becomes_a_member(
    client: httpx.AsyncClient, grants: Grants, invited: list[str]
) -> None:
    response = await client.post(
        "/v1/invites", json={"email": "dan@acme.com"}, headers=headers("alice")
    )
    assert response.status_code == 201
    assert response.json() == {"tenant": "acme", "user": "dan"}
    assert invited == ["dan@acme.com"]
    assert [m.user for m in await grants.memberships("dan")] == ["dan"]


async def test_inviting_is_checked_before_supabase_is_asked(
    client: httpx.AsyncClient, invited: list[str]
) -> None:
    for who, tenant in (("bob", "acme"), ("carol", "acme")):
        response = await client.post(
            "/v1/invites", json={"email": "eve@x.com"}, headers=headers(who, tenant)
        )
        assert response.status_code == 403
    response = await client.post(
        "/v1/invites", json={"email": "eve@x.com"}, headers=headers("alice", None)
    )
    assert response.status_code == 400
    assert invited == []


async def test_inviting_a_member_again_succeeds_and_changes_nothing(
    client: httpx.AsyncClient, grants: Grants
) -> None:
    response = await client.post(
        "/v1/invites", json={"email": "bob@acme.com"}, headers=headers("alice")
    )
    assert response.status_code == 201
    assert response.json() == {"tenant": "acme", "user": "bob"}
    assert len(await grants.members("acme", by=ALICE)) == 2


async def test_a_caller_bound_to_another_tenant_invites_no_one(
    client: httpx.AsyncClient, invited: list[str]
) -> None:
    bound = {**headers("alice", "acme"), "x-key-tenant": "globex"}
    response = await client.post("/v1/invites", json={"email": "eve@x.com"}, headers=bound)
    assert response.status_code == 403
    assert invited == []


@pytest.mark.parametrize(("error", "status"), [(Forbidden("no"), 403), (Invalid("no"), 422)])
async def test_grantr_refusing_the_member_refuses_the_invitation(
    stack: Stack, invite: Invite, ui: Path, error: Exception, status: int
) -> None:
    class Refusing(Grants):
        """grantr, refusing dan, whom the invitation is for."""

        async def add_member(self, tenant: str, member: Member, *, by: Subject) -> AuditEntry:
            if member == User(id="dan"):
                raise error
            return await super().add_member(tenant, member, by=by)

    app = FastAPI()
    router = portalr_router(
        resolve_actor=resolve_actor,
        grants=await seeded(Refusing),
        readers=stack.readers(),
        invite=invite,
        site=SITE,
        ui=ui,
    )
    app.include_router(router, prefix="/portalr")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://app/portalr") as client:
        response = await client.post(
            "/v1/invites", json={"email": "dan@acme.com"}, headers=headers("alice")
        )
    assert response.status_code == status


async def test_an_invitation_supabase_refuses_is_a_bad_gateway(
    grants: Grants, stack: Stack, ui: Path
) -> None:
    async def refusing(_email: str) -> str:
        raise InviteFailed("supabase answered 500")

    transport = httpx.ASGITransport(app=app_for(grants, stack.readers(), refusing, ui))
    async with httpx.AsyncClient(transport=transport, base_url="http://app/portalr") as client:
        response = await client.post(
            "/v1/invites", json={"email": "dan@acme.com"}, headers=headers("alice")
        )
    assert response.status_code == 502
    assert response.json()["detail"] == {
        "type": "invite_failed",
        "message": "supabase answered 500",
    }
