"""stackr's scripts/tracker-check: a tenant's tracker, checked step by step, with GETs only."""

import functools
import importlib.machinery
import importlib.util
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import httpx
import pytest

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "packages" / "stackr" / "scripts"
NOW = datetime(2026, 10, 17, tzinfo=UTC)
PROMETHEUS = "http://prometheus.test"


def load() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    loader = importlib.machinery.SourceFileLoader("tracker_check", str(SCRIPTS / "tracker-check"))
    spec = importlib.util.spec_from_loader("tracker_check", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["tracker_check"] = module  # its dataclasses look their module up
    loader.exec_module(module)
    return module


script = load()

type Route = Callable[[httpx.Request], httpx.Response]


def answering(routes: dict[str, Any], asked: list[httpx.Request]) -> httpx.MockTransport:
    """A tracker and a Prometheus that answer each path from `routes`, recording what they are
    asked: a value is its JSON, a callable answers the request, and a path that isn't there is
    404."""

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        route = routes.get(f"{request.url.host}{request.url.path}")
        if route is None:
            return httpx.Response(404, json={"error": "Page not found."})
        if callable(route):
            return cast("Route", route)(request)
        return httpx.Response(200, json=route)

    return httpx.MockTransport(answer)


def serving(routes: dict[str, Any], asked: list[httpx.Request]) -> httpx.Client:
    return httpx.Client(transport=answering(routes, asked))


def status(code: int) -> Route:
    return lambda _: httpx.Response(code, json={"detail": "no"})


def nudges(value: str | None) -> dict[str, Any]:
    result = [] if value is None else [{"metric": {}, "value": [0, value]}]
    return {"prometheus.test/api/v1/query": {"status": "success", "data": {"result": result}}}


def levels(found: list[Any]) -> list[tuple[str, str]]:
    return [(finding.level, finding.text) for finding in found]


# ─── Plane ────────────────────────────────────────────────────────────────────

BOT = "u-relayr"


@dataclass
class Plane:
    """A Plane whose tenant acme has a workspace, `acme`, with projects in it."""

    role: int = 15
    projects: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"id": "p-ops", "name": "Ops", "is_member": True},
            {"id": "p-other", "name": "Other", "is_member": False},
        ]
    )
    me: str = "relayr-acme"
    elsewhere: int = 403

    def routes(self) -> dict[str, Any]:
        api = "plane.test/api/v1"
        return {
            f"{api}/users/me/": {"id": BOT, "display_name": self.me, "email": f"{self.me}@x"},
            f"{api}/workspaces/acme/members/": [
                {"id": "u-owner", "role": 20},
                {"id": BOT, "role": self.role},
            ],
            f"{api}/workspaces/acme/projects/": self.page,
            f"{api}/workspaces/globex/members/": status(self.elsewhere),
        }

    def page(self, request: httpx.Request) -> httpx.Response:
        """The projects, one to a page, by Plane's cursors."""
        assert request.url.params["per_page"] == "1000"
        at = int(request.url.params.get("cursor", "0:0:0").split(":")[1])
        more = at + 1 < len(self.projects)
        body = {
            "results": self.projects[at : at + 1],
            "next_cursor": f"1000:{at + 1}:0",
            "next_page_results": more,
        }
        return httpx.Response(200, json=body)


def plane_tenant(projects: tuple[str, ...] = ("p-ops",)) -> Any:
    credentials = {"base_url": "http://plane.test/", "api_key": "plane_api_k", "workspace": "acme"}
    return script.Tenant("acme", credentials, projects, {"globex": "globex"})


def check_plane(plane: Plane, tenant: Any = None, asked: list[httpx.Request] | None = None) -> Any:
    asked = [] if asked is None else asked
    with serving({**plane.routes(), **nudges("0")}, asked) as client:
        return script.run(tenant or plane_tenant(), "plane", client, PROMETHEUS, NOW)


def test_a_provisioned_plane_tenant_passes_every_step_with_gets_alone() -> None:
    asked: list[httpx.Request] = []
    found = check_plane(Plane(), asked=asked)
    assert [level for level, _ in levels(found)] == ["ok", "ok", "ok", "ok", "skip", "ok"]
    assert "can't read webhooks" in found[4].text
    assert {request.method for request in asked} == {"GET"}
    tracker = [r for r in asked if r.url.host == "plane.test"]
    assert {r.headers["x-api-key"] for r in tracker} == {"plane_api_k"}
    assert [r.url.params.get("cursor") for r in asked if r.url.path.endswith("projects/")] == [
        None,
        "1000:1:0",
    ]


def test_a_key_plane_refuses_stops_the_check_there() -> None:
    plane = Plane()
    routes = {**plane.routes(), "plane.test/api/v1/users/me/": status(403)}
    with serving({**routes, **nudges(None)}, []) as client:
        [refused, _nudges] = script.run(plane_tenant(), "plane", client, PROMETHEUS, NOW)
    assert refused.level == "missing"
    assert "refused with 403" in refused.text


def test_a_key_of_another_user_is_missing_the_tenants_own() -> None:
    [wrong, _nudges] = check_plane(Plane(me="the-operator"))
    assert (wrong.level, wrong.text) == ("missing", "the key is the-operator's, not relayr-acme's")


@pytest.mark.parametrize("role", [20, 5])
def test_the_user_is_an_ordinary_member_of_the_workspace(role: int) -> None:
    found = check_plane(Plane(role=role))
    assert ("missing", f"relayr-acme is role {role} in acme, not a member (15)") in levels(found)


def test_a_user_outside_the_workspace_is_missing_it() -> None:
    plane = Plane()
    routes = {**plane.routes(), "plane.test/api/v1/workspaces/acme/members/": status(403)}
    with serving({**routes, **nudges(None)}, []) as client:
        found = script.check_plane(client, plane_tenant())
    assert levels(found)[-1] == ("missing", "relayr-acme in workspace 'acme': refused with 403")


def test_bound_projects_must_be_joined_and_others_not() -> None:
    projects = [
        {"id": "p-ops", "name": "Ops", "is_member": False},
        {"id": "p-other", "name": "Other", "is_member": True},
    ]
    found = levels(check_plane(Plane(projects=projects), plane_tenant(("p-ops", "p-gone"))))
    assert ("missing", "relayr-acme is not a member of bound project p-ops") in found
    assert ("missing", "bound project p-gone isn't in workspace acme") in found
    assert ("isolation", "relayr-acme is a member of Other, which isn't bound") in found


def test_a_tenant_with_no_binding_is_missing_one() -> None:
    found = levels(check_plane(Plane(), plane_tenant(())))
    assert ("missing", "TRACKER_BINDINGS binds none of acme's workspaces") in found


def test_plane_projects_that_cannot_be_listed_are_missing() -> None:
    plane = Plane()
    routes = {**plane.routes(), "plane.test/api/v1/workspaces/acme/projects/": status(500)}
    with serving({**routes, **nudges(None)}, []) as client:
        found = levels(script.check_plane(client, plane_tenant()))
    assert ("missing", "the projects of acme: refused with 500") in found


def test_another_tenants_workspace_the_key_reaches_breaks_isolation() -> None:
    found = levels(check_plane(Plane(elsewhere=200)))
    assert ("isolation", "relayr-acme is in globex's workspace, globex") in found


def test_a_plane_that_does_not_answer_is_said_so() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with httpx.Client(transport=httpx.MockTransport(down)) as client:
        [unreachable, nudged] = script.run(plane_tenant(), "plane", client, PROMETHEUS, NOW)
    assert "http://plane.test didn't answer (ConnectError)" in unreachable.text
    assert (nudged.level, "ConnectError" in nudged.text) == ("skip", True)


# ─── Vikunja ──────────────────────────────────────────────────────────────────

HOOK = {
    "target_url": "http://app:8000/relayr/v1/trackers/acme/vikunja",
    "events": ["task.created", "task.updated", "task.deleted", "task.comment.created", "x"],
}


def owned(number: int, owner: str = "relayr-acme") -> dict[str, Any]:
    return {"id": number, "title": f"project {number}", "owner": {"username": owner}}


@dataclass
class Vikunja:
    """A Vikunja where relayr-acme has its projects, and webhooks on them."""

    projects: list[dict[str, Any]] = field(default_factory=lambda: [owned(1), owned(2)])
    hooks: list[dict[str, Any]] = field(default_factory=lambda: [HOOK])
    user: str = "relayr-acme"

    def routes(self) -> dict[str, Any]:
        api = "vikunja.test/api/v1"
        return {
            f"{api}/user": {"username": self.user},
            f"{api}/projects": self.page,
            f"{api}/projects/2/webhooks": self.hooks,
        }

    def page(self, request: httpx.Request) -> httpx.Response:
        """Fifty projects a page, as Vikunja lists them."""
        assert request.url.params["per_page"] == "50"
        at = (int(request.url.params["page"]) - 1) * 50
        return httpx.Response(200, json=self.projects[at : at + 50])


def vikunja_tenant(expires: str | None = "2027-01-01", projects: tuple[str, ...] = ("2",)) -> Any:
    credentials: dict[str, Any] = {"base_url": "http://vikunja.test", "api_key": "tk_k"}
    if expires is not None:
        credentials["expires_at"] = expires
    return script.Tenant("acme", credentials, projects, {})


def check_vikunja(
    vikunja: Vikunja, tenant: Any = None, asked: list[httpx.Request] | None = None
) -> Any:
    asked = [] if asked is None else asked
    with serving({**vikunja.routes(), **nudges(None)}, asked) as client:
        return script.run(tenant or vikunja_tenant(), "vikunja", client, PROMETHEUS, NOW)


def test_a_provisioned_vikunja_tenant_passes_every_step_with_gets_alone() -> None:
    asked: list[httpx.Request] = []
    found = levels(check_vikunja(Vikunja(), asked=asked))
    assert found[:4] == [
        ("ok", "the token expires on 2027-01-01"),
        ("ok", "the token is relayr-acme's"),
        ("ok", "relayr-acme has project project 2"),
        ("ok", "project 2's webhook goes to http://app:8000/relayr/v1/trackers/acme/vikunja"),
    ]
    assert found[4][0] == "skip", "no follower has counted a change yet"
    assert {request.method for request in asked} == {"GET"}
    tokens = {r.headers["authorization"] for r in asked if r.url.host == "vikunja.test"}
    assert tokens == {"Bearer tk_k"}


def test_every_page_of_projects_is_read() -> None:
    projects = [owned(number) for number in range(1, 52)]
    found = levels(check_vikunja(Vikunja(projects=projects), vikunja_tenant(projects=("51",))))
    assert ("ok", "relayr-acme has project project 51") in found


@pytest.mark.parametrize(
    ("expires", "level", "says"),
    [
        ("2026-10-24T00:00:00+00:00", "warn", "within 14 days"),
        ("2026-10-01", "missing", "expired on 2026-10-01"),
        (None, "warn", "keep no expires_at"),
        ("soon", "warn", "isn't a date"),
    ],
)
def test_the_tokens_expiry_is_warned_of_two_weeks_before(
    expires: str | None, level: str, says: str
) -> None:
    [expiry, *_] = check_vikunja(Vikunja(), vikunja_tenant(expires))
    assert expiry.level == level
    assert says in expiry.text


def test_a_token_vikunja_refuses_stops_the_check_there() -> None:
    vikunja = Vikunja()
    routes = {**vikunja.routes(), "vikunja.test/api/v1/user": status(401)}
    with serving(routes, []) as client:
        found = levels(script.check_vikunja(client, vikunja_tenant(), NOW))
    assert found[-1][0] == "missing"
    assert "refused with 401" in found[-1][1]


def test_a_token_of_another_user_is_missing_the_tenants_own() -> None:
    found = levels(check_vikunja(Vikunja(user="admin")))
    assert ("missing", "the token is admin's, not relayr-acme's") in found


def test_vikunja_projects_that_cannot_be_listed_are_missing() -> None:
    vikunja = Vikunja()
    routes = {**vikunja.routes(), "vikunja.test/api/v1/projects": status(401)}
    with serving(routes, []) as client:
        found = levels(script.check_vikunja(client, vikunja_tenant(), NOW))
    assert found[-1] == ("missing", "the user's projects: refused with 401")


def test_a_bound_project_that_is_not_the_users_is_missing() -> None:
    found = levels(check_vikunja(Vikunja(), vikunja_tenant(projects=("9",))))
    assert ("missing", "bound project 9 isn't relayr-acme's") in found
    found = levels(check_vikunja(Vikunja(), vikunja_tenant(projects=())))
    assert ("missing", "TRACKER_BINDINGS binds none of acme's workspaces") in found


@pytest.mark.parametrize(
    ("hooks", "says"),
    [
        ([], "project 2 has no webhook to <application>/relayr/v1/trackers/acme/vikunja"),
        (
            [{**HOOK, "target_url": "http://app:8000/relayr/v1/trackers/globex/vikunja"}],
            "project 2 has no webhook to <application>/relayr/v1/trackers/acme/vikunja",
        ),
        (
            [{**HOOK, "events": ["task.created"]}],
            "project 2's webhook sends no ['task.comment.created', 'task.deleted', 'task.updated']",
        ),
    ],
)
def test_each_bound_project_has_a_webhook_with_relayrs_events(
    hooks: list[dict[str, Any]], says: str
) -> None:
    assert ("missing", says) in levels(check_vikunja(Vikunja(hooks=hooks)))


def test_webhooks_the_token_cannot_read_are_missing() -> None:
    vikunja = Vikunja()
    routes = {**vikunja.routes(), "vikunja.test/api/v1/projects/2/webhooks": status(401)}
    with serving(routes, []) as client:
        found = levels(script.check_vikunja(client, vikunja_tenant(), NOW))
    assert ("missing", "project 2's webhooks: refused with 401") in found


def test_a_project_another_user_shared_breaks_isolation() -> None:
    found = levels(check_vikunja(Vikunja(projects=[owned(2), owned(7, "relayr-globex")])))
    assert ("isolation", "relayr-acme sees relayr-globex's project project 7") in found


# ─── the nudges ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "level", "says"),
    [
        ("0", "ok", "every change in the last hour came with its webhook"),
        ("3", "warn", "3 changes in the last hour came with no webhook"),
        (None, "skip", "no follower has counted"),
    ],
)
def test_the_unnudged_changes_are_read_from_prometheus(
    value: str | None, level: str, says: str
) -> None:
    asked: list[httpx.Request] = []
    with serving(nudges(value), asked) as client:
        found = script.check_nudges(client, PROMETHEUS, plane_tenant())
    assert found.level == level
    assert says in found.text
    [query] = [r.url.params["query"] for r in asked]
    assert query == 'sum(increase(relayr_trackers_unnudged_total{tenant_id="acme"}[1h]))'


def test_a_prometheus_that_is_not_there_is_skipped() -> None:
    with serving({}, []) as client:
        found = script.check_nudges(client, PROMETHEUS, plane_tenant())
    assert (found.level, "HTTPStatusError" in found.text) == ("skip", True)


# ─── the settings, and the command ────────────────────────────────────────────

CREDENTIALS = {
    "acme": {"base_url": "http://plane.test", "api_key": "k", "workspace": "acme"},
    "globex": {"base_url": "http://plane.test", "api_key": "k", "workspace": "globex"},
    "initech": {"base_url": "http://vikunja.test", "api_key": "k"},
}
BINDINGS = {
    "acme/main": {"project": "p-ops"},
    "acme/ops": {"project": "p-run"},
    "globex/main": {"project": "p-globex"},
}


def test_a_tenant_is_read_from_the_applications_settings() -> None:
    env = {"TRACKER_CREDENTIALS": json.dumps(CREDENTIALS), "TRACKER_BINDINGS": json.dumps(BINDINGS)}
    tenant = script.tenant_of(env, "acme")
    assert (tenant.projects, dict(tenant.others)) == (("p-ops", "p-run"), {"globex": "globex"})
    assert (tenant.user, tenant.route) == ("relayr-acme", "/relayr/v1/trackers/acme/")


@pytest.mark.parametrize(
    ("env", "says"),
    [
        ({}, "TRACKER_CREDENTIALS has nothing for acme"),
        ({"TRACKER_CREDENTIALS": "{"}, "TRACKER_CREDENTIALS isn't JSON"),
        ({"TRACKER_CREDENTIALS": "[]"}, "TRACKER_CREDENTIALS isn't a JSON object"),
    ],
)
def test_settings_without_the_tenant_stop_it(env: dict[str, str], says: str) -> None:
    with pytest.raises(SystemExit, match=says):
        script.tenant_of(env, "acme")


def test_the_command_reads_the_applications_env_and_fails_on_what_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    app_env = tmp_path / ".env"
    credentials = json.dumps({"acme": {**CREDENTIALS["acme"], "base_url": "http://plane.test"}})
    app_env.write_text(f"TRACKER_CREDENTIALS={credentials}\nTRACKER_BINDINGS={{}}\n")
    transport = answering({**Plane().routes(), **nudges("0")}, [])
    monkeypatch.setattr(
        script.httpx, "Client", functools.partial(httpx.Client, transport=transport)
    )
    argv = ["tracker-check", "acme", "--tracker", "plane", "--app-env", str(app_env)]
    monkeypatch.setattr(sys, "argv", argv)
    assert script.main() == 1, "no workspace of acme's is bound"
    printed = capsys.readouterr().out.splitlines()
    assert "missing: TRACKER_BINDINGS binds none of acme's workspaces" in printed
    assert printed[0] == "ok: the key is relayr-acme's"


def test_an_applications_env_that_is_not_there_stops_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing.env"
    argv = ["tracker-check", "acme", "--tracker", "plane", "--app-env", str(missing)]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit, match="is missing"):
        script.main()
