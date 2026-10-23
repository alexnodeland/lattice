import json as jsonlib
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import FastAPI

from grantr.core import TENANT, AuditEntry, Forbidden, Invalid, Member, Resource, Subject, User
from grantr.grants import Grants
from portalr.fastapi import portalr_router
from portalr.invites import Invite, InviteFailed
from portalr.readers import Langfuse, LiteLLM, Readers
from portalr.readers.loki import _identify
from tests.fastapi.conftest import ALICE, OPS, SITE, Stack, app_for, resolve_actor, seeded
from tests.tools import Tool, fails, json

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


def _trace(*spans: tuple[str, str, dict[str, str]]) -> dict[str, Any]:
    """A trace as Tempo gives it: each span with its tenant and some content."""
    return {
        "trace": {
            "resourceSpans": [
                {
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "spanId": span_id,
                                    "name": span_id,
                                    "startTimeUnixNano": "1",
                                    "endTimeUnixNano": "2",
                                    "attributes": [
                                        {"key": "tenant.id", "value": {"stringValue": tenant}},
                                        *(
                                            {"key": key, "value": {"stringValue": value}}
                                            for key, value in content.items()
                                        ),
                                    ],
                                }
                                for span_id, tenant, content in spans
                            ]
                        }
                    ]
                }
            ]
        }
    }


async def test_what_a_span_withheld_is_given_for_that_span_alone_and_never_kept(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    said = {"gen_ai.input.messages": "[secret prompt]"}
    stack.tempo.paths["/api/v2/traces/f1"] = json(
        _trace(("1", "acme", said), ("2", "acme", {"gen_ai.output.messages": "[other]"}))
    )
    alice = headers("alice")
    plain = await client.get("/v1/traces/f1", headers=alice)
    assert "[secret prompt]" not in plain.text
    assert "cache-control" not in plain.headers
    first, second = plain.json()["data"]["spans"]
    assert first["withheld"] == ["gen_ai.input.messages"]
    assert second["withheld"] == ["gen_ai.output.messages"]
    # A span named without `content` reveals nothing.
    named = await client.get("/v1/traces/f1", params={"span": "1"}, headers=alice)
    assert "[secret prompt]" not in named.text
    revealed = await client.get(
        "/v1/traces/f1", params={"content": "true", "span": "1"}, headers=alice
    )
    assert revealed.headers["cache-control"] == "no-store"
    one, two = revealed.json()["data"]["spans"]
    assert one["attributes"]["gen_ai.input.messages"] == "[secret prompt]"
    assert (two["attributes"].get("gen_ai.output.messages"), two["withheld"]) == (
        None,
        ["gen_ai.output.messages"],
    )
    assert "[other]" not in revealed.text
    # Content is asked for a span.
    unnamed = await client.get("/v1/traces/f1", params={"content": "true"}, headers=alice)
    assert unnamed.status_code == 422


async def test_what_a_span_withheld_needs_the_grant_and_the_tenants_own_trace(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    said = {"gen_ai.input.messages": "[secret prompt]"}
    stack.tempo.paths["/api/v2/traces/f1"] = json(_trace(("1", "acme", said)))
    stack.tempo.paths["/api/v2/traces/f2"] = json(
        _trace(("1", "acme", said), ("2", "globex", said))
    )
    asked = {"content": "true", "span": "1"}
    for who, tenant in (("bob", "acme"), ("carol", "acme"), ("alice", "globex")):
        refused = await client.get("/v1/traces/f1", params=asked, headers=headers(who, tenant))
        assert refused.status_code == 403, (who, tenant)
    assert not stack.tempo.requests
    # A trace with a span of another tenant's, or none of this one's, is none, content or not.
    mixed = await client.get("/v1/traces/f2", params=asked, headers=headers("alice"))
    assert mixed.json() == {"status": "ok", "data": None}
    stack.tempo.paths["/api/v2/traces/f3"] = json(_trace(("1", "globex", said)))
    other = await client.get("/v1/traces/f3", params=asked, headers=headers("alice"))
    assert other.json() == {"status": "ok", "data": None}
    assert "[secret prompt]" not in mixed.text + other.text


PHRASE = "alice@example.com said launch on Tuesday"


def _loki(*records: tuple[str, str, dict[str, str]]) -> dict[str, Any]:
    """Loki's answer: each record's time, line and labels."""
    return {
        "data": {
            "result": [
                {"stream": {"service_name": "docplan", **labels}, "values": [[time, line]]}
                for time, line, labels in records
            ]
        }
    }


async def test_a_logs_read_has_no_lines_and_one_records_line_is_asked_for_by_its_id(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    mine = {"tenant_id": "acme", "email": "a@b.c", "artifactr_run_id": "run_1"}
    stack.loki.paths["/loki/api/v1/query_range"] = json(_loki(("5", PHRASE, mine)))
    alice = headers("alice")
    listed = await client.get("/v1/logs", params=WINDOW, headers=alice)
    assert PHRASE not in listed.text
    assert "cache-control" not in listed.headers
    (record,) = listed.json()["data"]["records"]
    assert (record["length"], record["run"], record["withheld"], record["line"]) == (
        len(PHRASE),
        "run_1",
        ["email"],
        None,
    )
    line = await client.get(f"/v1/logs/{record['id']}", headers=alice)
    assert line.headers["cache-control"] == "no-store"
    assert line.json()["data"]["line"] == PHRASE
    # An id that names no record, or none at all, is none; the same is said of both.
    answer = await client.get(f"/v1/logs/5-{'0' * 16}-0", headers=alice)
    assert answer.json() == {"status": "ok", "data": None}
    # One past the largest time Loki takes names nothing, and isn't looked for.
    past = await client.get(f"/v1/logs/{2**63}-{'0' * 16}-0", headers=alice)
    assert past.json() == {"status": "ok", "data": None}
    # An id that isn't one is refused, and is not looked for.
    for wrong in ("nonsense", "5-0-0", f"\u0661-{'0' * 16}-0"):
        assert (await client.get(f"/v1/logs/{wrong}", headers=alice)).status_code == 422, wrong
    # A window of more than a day is refused.
    wide = {"start": "2026-10-12T00:00:00Z", "end": "2026-10-13T00:00:01Z"}
    assert (await client.get("/v1/logs", params=wide, headers=alice)).status_code == 422


async def test_a_logs_line_needs_the_grant_and_the_tenants_own_record(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    theirs = {"tenant_id": "globex"}
    stack.loki.paths["/loki/api/v1/query_range"] = json(_loki(("5", PHRASE, theirs)))
    for who, tenant in (("bob", "acme"), ("carol", "acme"), ("alice", "globex")):
        refused = await client.get(f"/v1/logs/5-{'a' * 16}-0", headers=headers(who, tenant))
        assert refused.status_code == 403, (who, tenant)
    assert not stack.loki.requests
    # A record of another tenant's that Loki gives all the same isn't shown, by list or by id.
    listed = await client.get("/v1/logs", params=WINDOW, headers=headers("alice"))
    assert listed.json()["data"]["records"] == []
    globex_id = _identify([(5, PHRASE, {"service_name": "docplan", "tenant_id": "globex"})])[0][
        0
    ].id
    asked = await client.get(f"/v1/logs/{globex_id}", headers=headers("alice"))
    assert asked.json() == {"status": "ok", "data": None}
    assert PHRASE not in listed.text + asked.text


async def test_every_read_is_refused_without_the_tenants_grant(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    reads = ["/v1/traces", "/v1/traces/t1", "/v1/logs", "/v1/scores", "/v1/feedback"]
    for path in [*reads, "/v1/spend", "/v1/usage", "/v1/adoption", f"/v1/logs/5-{'a' * 16}-0"]:
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
        "data": {"records": [], "complete": True},
    }
    metrics = await client.get(
        "/v1/metrics", params={**WINDOW, "metric": "turn_latency"}, headers=alice
    )
    assert metrics.json() == {"status": "ok", "data": []}
    assert stack.prometheus.last.url.params["tenant_id"] == "acme"
    assert (await client.get("/v1/scores", params=WINDOW, headers=alice)).json() == {
        "status": "ok",
        "data": {"scores": [], "complete": True, "known_from": None},
    }
    summary = await client.get(
        "/v1/feedback", params={**WINDOW, "workspace": "notes"}, headers=alice
    )
    assert summary.json()["status"] == "ok"
    assert summary.json()["data"]["complete"] is True
    assert '"workspace:notes"' in stack.langfuse.last.url.params["filter"]
    too_long = {"start": "2026-07-01T00:00:00Z", "end": "2026-10-12T00:00:00Z"}
    assert (await client.get("/v1/feedback", params=too_long, headers=alice)).status_code == 422
    backwards = {"start": WINDOW["end"], "end": WINDOW["start"]}
    assert (await client.get("/v1/feedback", params=backwards, headers=alice)).status_code == 422
    # A moment without its zone, a span from before 2000, or past 2200, is refused, not read.
    for wrong in (
        {"start": "2026-10-12T00:00:00", "end": WINDOW["end"]},
        {"start": "0001-01-01T00:00:00Z", "end": WINDOW["end"]},
        {"start": WINDOW["start"], "end": "9999-12-31T00:00:00Z"},
    ):
        for path in ("/v1/feedback", "/v1/traces", "/v1/logs", "/v1/scores", "/v1/metrics"):
            asked = {**wrong, "metric": "failed_turns"}
            assert (await client.get(path, params=asked, headers=alice)).status_code == 422, path
    assert (await client.get("/v1/spend", headers=alice)).json() == {
        "status": "ok",
        "data": {"spend": 2.0, "max_budget": None, "budget_duration": None},
    }
    stack.litellm.paths["/team/daily/activity"] = json({"results": []})
    stack.litellm.paths["/tag/daily/activity"] = json({"results": []})
    usage = await client.get(
        "/v1/usage", params={**WINDOW, "workspaces": ["notes", "plans"]}, headers=alice
    )
    assert usage.json()["status"] == "ok"
    assert usage.json()["data"]["complete"] is True
    tagged = [r for r in stack.litellm.requests if r.url.path == "/tag/daily/activity"]
    assert [r.url.params["tags"] for r in tagged] == [
        "tenant-workspace:acme/notes,tenant-workspace:acme/plans"
    ]


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
        for path in (
            "/v1/traces",
            "/v1/traces/t1",
            "/v1/logs",
            "/v1/scores",
            "/v1/feedback",
            "/v1/spend",
            "/v1/usage",
            "/v1/adoption",
            f"/v1/logs/5-{'a' * 16}-0",
        ):
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
            "langfuse_tenant": None,
            "grafana_trace": None,
            "grafana_logs": None,
            "grafana_tenant_logs": None,
            "grafana_tenant_traces": None,
        }
        # Without Supabase's admin API, there is no invitation.
        invite = await client.post("/v1/invites", json={"email": "dan@acme.com"}, headers=alice)
        assert invite.status_code in (404, 405)
        creating = await client.post(
            "/v1/deployment/tenants",
            json={"tenant": "initech", "owner_email": "dan@x.com"},
            headers=headers("ops", tenant=None),
        )
        assert creating.status_code in (404, 405)
        assert (await client.get("/config.json")).json()["readers"] == dict.fromkeys(
            ("tempo", "loki", "prometheus", "langfuse", "litellm", "grafana", "analytics"), False
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


OPS_ONLY = headers("ops", tenant=None)
NEW = {"tenant": "initech", "owner_email": "dan@initech.com"}


async def test_an_operator_creates_a_tenant_with_its_owner_invited_by_email(
    client: httpx.AsyncClient, grants: Grants, invited: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("DEBUG"):
        response = await client.post("/v1/deployment/tenants", json=NEW, headers=OPS_ONLY)
    assert response.status_code == 201
    assert response.json() == {"tenant": "initech", "owner": "dan"}
    assert invited == ["dan@initech.com"]
    assert "initech" in await grants.tenants(by=OPS)
    assert await grants.check("initech", User(id="dan"), "grantr:add_member", TENANT)
    # The email is neither in the answer nor in any log.
    assert "@" not in response.text
    assert "dan@initech.com" not in caplog.text


@pytest.mark.parametrize(
    ("who", "tenant"), [("alice", "acme"), ("alice", None), ("bob", "acme"), ("carol", "globex")]
)
async def test_nobody_but_an_operator_creates_a_tenant_or_invites_anyone(
    client: httpx.AsyncClient, grants: Grants, invited: list[str], who: str, tenant: str | None
) -> None:
    response = await client.post("/v1/deployment/tenants", json=NEW, headers=headers(who, tenant))
    assert response.status_code == 403
    assert invited == []
    assert "initech" not in await grants.tenants(by=OPS)


async def test_a_caller_who_may_not_create_tenants_invites_no_one(
    stack: Stack, invite: Invite, invited: list[str], ui: Path
) -> None:
    class Cautious(Grants):
        """grantr, where no one may create a tenant, though an operator may read the deployment."""

        async def check(self, tenant: str, subject: Subject, action: str, on: Resource) -> bool:
            return action != "grantr:create_tenant" and await super().check(
                tenant, subject, action, on
            )

    transport = httpx.ASGITransport(
        app=app_for(await seeded(Cautious), stack.readers(), invite, ui)
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://app/portalr") as client:
        response = await client.post("/v1/deployment/tenants", json=NEW, headers=OPS_ONLY)
    assert response.status_code == 403
    assert invited == []


async def test_a_tenant_that_exists_is_refused_before_anyone_is_invited(
    client: httpx.AsyncClient, invited: list[str]
) -> None:
    response = await client.post(
        "/v1/deployment/tenants", json={**NEW, "tenant": "acme"}, headers=OPS_ONLY
    )
    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "acme exists"
    assert invited == []


async def test_a_repeated_request_creates_nothing_twice_and_invites_no_one_again(
    client: httpx.AsyncClient, grants: Grants, invited: list[str]
) -> None:
    first = await client.post("/v1/deployment/tenants", json=NEW, headers=OPS_ONLY)
    again = await client.post("/v1/deployment/tenants", json=NEW, headers=OPS_ONLY)
    assert (first.status_code, again.status_code) == (201, 422)
    assert invited == ["dan@initech.com"]
    assert (await grants.tenants(by=OPS)).count("initech") == 1


@pytest.mark.parametrize(
    "email", ["", "dan", "dan@x", "d an@x.com", "a@b@c.com", "x" * 250 + "@y.com"]
)
async def test_an_owner_that_is_no_email_is_refused_without_being_echoed(
    client: httpx.AsyncClient, invited: list[str], email: str
) -> None:
    response = await client.post(
        "/v1/deployment/tenants", json={**NEW, "owner_email": email}, headers=OPS_ONLY
    )
    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "the owner's email isn't an email address"
    assert email not in response.text or email == ""
    assert invited == []


async def test_a_tenant_id_grantr_does_not_take_is_refused(
    client: httpx.AsyncClient, invited: list[str]
) -> None:
    for tenant in ("", "a~b"):
        response = await client.post(
            "/v1/deployment/tenants", json={**NEW, "tenant": tenant}, headers=OPS_ONLY
        )
        assert response.status_code == 422, tenant
    assert invited == []


async def test_an_owner_supabase_cannot_invite_leaves_no_tenant(
    grants: Grants, stack: Stack, ui: Path
) -> None:
    async def refusing(_email: str) -> str:
        raise InviteFailed("supabase answered 500")

    transport = httpx.ASGITransport(app=app_for(grants, stack.readers(), refusing, ui))
    async with httpx.AsyncClient(transport=transport, base_url="http://app/portalr") as client:
        response = await client.post("/v1/deployment/tenants", json=NEW, headers=OPS_ONLY)
    assert response.status_code == 502
    assert response.json()["detail"] == {
        "type": "invite_failed",
        "message": "supabase answered 500",
    }
    assert "initech" not in await grants.tenants(by=OPS)
    assert "dan@initech.com" not in response.text


@pytest.mark.parametrize(("error", "status"), [(Forbidden("no"), 403), (Invalid("no"), 422)])
async def test_grantr_refusing_the_creation_refuses_it(
    stack: Stack, invite: Invite, ui: Path, error: Exception, status: int
) -> None:
    class Refusing(Grants):
        """grantr, refusing to create the tenant after the checks before it."""

        async def create_tenant(self, tenant: str, *, owner: str, by: Subject) -> AuditEntry:
            if tenant == "initech":
                raise error
            return await super().create_tenant(tenant, owner=owner, by=by)

    transport = httpx.ASGITransport(
        app=app_for(await seeded(Refusing), stack.readers(), invite, ui)
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://app/portalr") as client:
        response = await client.post("/v1/deployment/tenants", json=NEW, headers=OPS_ONLY)
    assert response.status_code == status


async def test_a_storage_error_after_the_invitation_is_a_clean_503_that_says_nothing_of_it(
    stack: Stack, invite: Invite, invited: list[str], ui: Path
) -> None:
    class Failing(Grants):
        """grantr, whose storage fails creating the tenant, in words that name the owner."""

        async def create_tenant(self, tenant: str, *, owner: str, by: Subject) -> AuditEntry:
            if tenant == "initech":
                raise RuntimeError("insert failed for dan@initech.com")
            return await super().create_tenant(tenant, owner=owner, by=by)

    transport = httpx.ASGITransport(app=app_for(await seeded(Failing), stack.readers(), invite, ui))
    async with httpx.AsyncClient(transport=transport, base_url="http://app/portalr") as client:
        response = await client.post("/v1/deployment/tenants", json=NEW, headers=OPS_ONLY)
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "type": "unavailable",
        "message": "the tenant couldn't be created",
    }
    assert "dan" not in response.text
    # The owner was invited before it failed: an invitation can outlive a refused creation.
    assert invited == ["dan@initech.com"]


OPS_LINKS = headers("ops", None)


def _recorded(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    """The records of an operator's links, as the access log wrote them."""
    return [
        jsonlib.loads(each.getMessage()) for each in caplog.records if each.name == "portalr.access"
    ]


async def test_an_operator_gets_a_tenants_links_and_it_is_recorded_with_the_tenant(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO", logger="portalr.access"):
        links = (
            await client.get(
                "/v1/deployment/links", params={"tenant_id": "acme"}, headers=OPS_LINKS
            )
        ).json()
    assert links["langfuse_tenant"] == (
        "http://langfuse/project/p1/traces?filter="
        "traceTags%3BarrayOptions%3B%3Bany%20of%3Btenant%253Aacme"
    )
    loki = links["grafana_tenant_logs"]
    tempo = links["grafana_tenant_traces"]
    assert loki.startswith("http://grafana/explore?left=")
    assert "tenant_id+%3D+%5C%22acme%5C%22" in loki
    assert "span.tenant.id+%3D+%5C%22acme%5C%22" in tempo
    assert _recorded(caplog) == [
        {
            "event": "deployment_links",
            "by": {"kind": "user", "id": "ops"},
            "kinds": ["tenant"],
            "tenant": "acme",
            "tools": ["langfuse", "grafana"],
        }
    ]


async def test_the_record_holds_the_kinds_of_id_and_never_the_ids_or_a_url(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    params = {"trace_id": "trace-secret-1", "session_id": "thr_secret", "run_id": "run_secret"}
    with caplog.at_level("INFO", logger="portalr.access"):
        await client.get("/v1/deployment/links", params=params, headers=OPS_LINKS)
    (record,) = _recorded(caplog)
    assert record["kinds"] == ["trace", "session", "run"]
    assert record["tenant"] is None
    logged = " ".join(each.getMessage() for each in caplog.records)
    for secret in ("trace-secret-1", "thr_secret", "run_secret", "http://"):
        assert secret not in logged


async def test_nothing_is_recorded_for_a_refusal_or_for_no_ids(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO", logger="portalr.access"):
        for who, tenant in (("alice", "acme"), ("bob", "acme"), ("carol", "globex")):
            refused = await client.get(
                "/v1/deployment/links", params={"trace_id": "t1"}, headers=headers(who, tenant)
            )
            assert refused.status_code == 403
        unknown = await client.get(
            "/v1/deployment/links", params={"tenant_id": "nowhere"}, headers=OPS_LINKS
        )
        assert unknown.status_code == 422
        assert unknown.json()["detail"]["message"] == "no tenant nowhere"
        none = await client.get("/v1/deployment/links", headers=OPS_LINKS)
        assert none.status_code == 200
        bad = await client.get(
            "/v1/deployment/links", params={"trace_id": "a b"}, headers=OPS_LINKS
        )
        assert bad.status_code == 422
    assert _recorded(caplog) == []


async def test_no_key_of_a_tool_is_in_a_link_the_config_or_an_error(
    grants: Grants, invite: Invite, ui: Path
) -> None:
    keyed = Stack(Tool(), Tool(), Tool(), Tool(), Tool())
    readers = keyed.readers()
    secret = httpx.AsyncClient(auth=("visible-key-7f3a", "hidden-key-9c1e"))
    readers = Readers(
        tempo=readers.tempo,
        loki=readers.loki,
        prometheus=readers.prometheus,
        langfuse=Langfuse("http://langfuse", project="p1", client=secret),
        litellm=LiteLLM(
            "http://litellm",
            httpx.AsyncClient(headers={"authorization": "Bearer master-key-4b2d"}),
        ),
        grafana=readers.grafana,
    )
    transport = httpx.ASGITransport(app=app_for(grants, readers, invite, ui))
    async with httpx.AsyncClient(transport=transport, base_url="http://app/portalr") as client:
        seen = [
            (await client.get("/v1/deployment/links", params=params, headers=OPS_LINKS)).text
            for params in (
                {"trace_id": "t1", "session_id": "s1", "run_id": "r1", "tenant_id": "acme"},
                {"tenant_id": "nowhere"},
                {"trace_id": "a b"},
            )
        ]
        seen.append((await client.get("/config.json")).text)
        seen.append((await client.get("/v1/deployment/links", headers=headers("alice"))).text)
    for text in seen:
        for secret_value in ("visible-key-7f3a", "hidden-key-9c1e", "master-key-4b2d"):
            assert secret_value not in text.lower(), text


async def test_the_links_for_a_tenant_and_a_run_open_at_the_last_day(
    client: httpx.AsyncClient,
) -> None:
    params = {"run_id": "run_1", "tenant_id": "acme", "trace_id": "t1"}
    links = (await client.get("/v1/deployment/links", params=params, headers=OPS_LINKS)).json()
    ranges = {
        name: jsonlib.loads(parse_qs(urlparse(links[name]).query)["left"][0]).get("range")
        for name in (
            "grafana_logs",
            "grafana_tenant_logs",
            "grafana_tenant_traces",
            "grafana_trace",
        )
    }
    last_day = {"from": "now-24h", "to": "now"}
    assert ranges == {
        "grafana_logs": last_day,
        "grafana_tenant_logs": last_day,
        "grafana_tenant_traces": last_day,
        "grafana_trace": None,
    }


async def test_no_record_is_made_where_no_link_was(
    grants: Grants, invite: Invite, ui: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bare = Readers(
        tempo=None, loki=None, prometheus=None, langfuse=None, litellm=None, grafana=None
    )
    transport = httpx.ASGITransport(app=app_for(grants, bare, invite, ui))
    async with httpx.AsyncClient(transport=transport, base_url="http://app/portalr") as client:
        with caplog.at_level("INFO", logger="portalr.access"):
            made = await client.get(
                "/v1/deployment/links", params={"trace_id": "t1"}, headers=OPS_LINKS
            )
    assert made.status_code == 200
    assert _recorded(caplog) == []


async def test_a_session_link_is_recorded_for_langfuse_alone(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO", logger="portalr.access"):
        await client.get("/v1/deployment/links", params={"session_id": "thr_1"}, headers=OPS_LINKS)
    assert [record["tools"] for record in _recorded(caplog)] == [["langfuse"]]


async def test_an_analytics_sessions_traces_are_the_tenants_alone(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    stack.tempo.paths["/api/search"] = json({"traces": []})
    session = "1792800000-0123456789abcdef"
    response = await client.get(
        "/v1/traces", params={**WINDOW, "analytics_session": session}, headers=headers("alice")
    )
    assert response.json() == {"status": "ok", "data": []}
    assert stack.tempo.last.url.params["q"] == (
        f'{{ span.tenant.id = "acme" }} && {{ span.portalr.analytics.session = "{session}" }}'
    )
    forged = await client.get(
        "/v1/traces",
        params={**WINDOW, "analytics_session": 'x" } || { true'},
        headers=headers("alice"),
    )
    assert forged.status_code == 422
