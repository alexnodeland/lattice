"""Mini apps' sandbox, served on the apps' origin alone, under its policy."""

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from starlette.types import Message, Receive, Scope, Send

from portalr.fastapi import SandboxOrigin, Site
from portalr.fastapi.sandbox import APP_POLICY, sandbox_policy
from portalr.fastapi.ui import policy

PORTAL = "https://app.example.com"
APPS = "https://apps.example.com"
PAGE = "<!doctype html><title>Sandbox</title><script>relay()</script>"


@pytest.fixture
def built(tmp_path: Path) -> Path:
    (tmp_path / "sandbox").mkdir()
    (tmp_path / "sandbox" / "index.html").write_text(PAGE)
    return tmp_path


def _client(root: Path, apps: str = APPS) -> httpx.AsyncClient:
    application = FastAPI()

    @application.get("/{path:path}")
    async def anything(path: str) -> dict[str, str]:
        return {"application": path}

    application.add_middleware(SandboxOrigin, apps=apps, portal=PORTAL, root=root)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url=PORTAL)


async def test_the_sandbox_is_served_on_its_origin_under_its_policy(built: Path) -> None:
    async with _client(built) as client:
        for host in ("apps.example.com", "APPS.example.com:443"):
            response = await client.get("/", headers={"host": host})
            assert response.status_code == 200, host
            assert response.text == PAGE
            assert response.headers["content-type"].startswith("text/html")
            assert response.headers["content-security-policy"] == sandbox_policy(PORTAL)
            assert response.headers["cache-control"] == "no-cache"
            assert response.headers["x-dns-prefetch-control"] == "off"
            assert response.headers["referrer-policy"] == "no-referrer"
            assert "camera=()" in response.headers["permissions-policy"]
            assert "set-cookie" not in response.headers


async def test_the_apps_origin_serves_nothing_else_and_sets_no_cookie(built: Path) -> None:
    async with _client(built) as client:
        apps = {"host": "apps.example.com"}
        for path in ("/portalr/app/", "/index.html", "/sandbox/index.html", "/config.json"):
            response = await client.get(path, headers=apps)
            assert response.status_code == 404, path
            assert response.headers["content-security-policy"] == sandbox_policy(PORTAL)
        assert (await client.post("/", headers=apps)).status_code == 405
        assert (await client.head("/", headers=apps)).status_code == 200


async def test_every_other_host_reaches_the_application(built: Path) -> None:
    async with _client(built) as client:
        for host in ("app.example.com", "apps.example.com.evil.net", "apps.example.com:8443"):
            response = await client.get("/", headers={"host": host})
            assert response.json() == {"application": ""}, host


async def test_a_sandbox_not_built_is_not_found(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        response = await client.get("/", headers={"host": "apps.example.com"})
        assert (response.status_code, response.text) == (404, "The sandbox isn't built.")


async def test_on_loopback_the_apps_origin_is_another_port(built: Path) -> None:
    async with _client(built, apps="http://127.0.0.1:8001") as client:
        assert (await client.get("/", headers={"host": "127.0.0.1:8001"})).text == PAGE
        response = await client.get("/", headers={"host": "127.0.0.1:8000"})
        assert response.json() == {"application": ""}


async def _received() -> Message:
    return {"type": "websocket.connect"}


async def test_a_websocket_to_the_apps_origin_is_closed(built: Path) -> None:
    sent: list[Message] = []

    async def application(scope: Scope, receive: Receive, send: Send) -> None:
        raise AssertionError("the application never hears the apps' origin")

    async def send(message: Message) -> None:
        sent.append(message)

    sandbox = SandboxOrigin(application, apps=APPS, portal=PORTAL, root=built)
    scope: Scope = {"type": "websocket", "path": "/", "headers": [(b"host", b"apps.example.com")]}
    await sandbox(scope, _received, send)
    assert sent == [{"type": "websocket.close", "code": 1008}]


async def test_the_lifespan_reaches_the_application(built: Path) -> None:
    heard: list[str] = []

    async def application(scope: Scope, receive: Receive, send: Send) -> None:
        heard.append(scope["type"])

    async def send(message: Message) -> None:
        raise AssertionError("the sandbox says nothing of a lifespan")

    await SandboxOrigin(application, apps=APPS, portal=PORTAL, root=built)(
        {"type": "lifespan"}, _received, send
    )
    assert heard == ["lifespan"]


@pytest.mark.parametrize("apps", [PORTAL, f"{PORTAL}:443"])
def test_apps_never_share_the_portals_origin(apps: str) -> None:
    with pytest.raises(ValueError, match="share a portal's origin"):
        SandboxOrigin(FastAPI(), apps=apps, portal=PORTAL)


def test_the_portal_frames_the_apps_origin_alone() -> None:
    site = Site(supabase_url="/", supabase_key="sb_publishable_x", apps=APPS)
    assert f"; frame-src {APPS};" in policy(site)
    assert policy(site).endswith("frame-ancestors 'none'")
    assert "frame-src" not in policy(Site(supabase_url="/", supabase_key="sb_publishable_x"))


def test_the_portal_frames_each_editors_origin_beside_the_apps() -> None:
    editors = {
        "files:gridcraft": "https://grid.example.com/editor/",
        "files:pdfcraft": "https://pdf.example.com",
        "files:cadcraft": "https://grid.example.com/other",
    }
    site = Site(supabase_url="/", supabase_key="sb_publishable_x", apps=APPS, editors=editors)
    expected = f"; frame-src {APPS} https://grid.example.com https://pdf.example.com;"
    assert expected in policy(site)
    alone = Site(supabase_url="/", supabase_key="sb_publishable_x", editors=editors)
    assert "; frame-src https://grid.example.com https://pdf.example.com;" in policy(alone)


def test_the_app_policy_reaches_nothing_and_runs_no_webassembly() -> None:
    directives = APP_POLICY.split("; ")
    assert directives[0] == "default-src 'none'"
    assert not any("wasm" in d or "eval" in d or "http" in d or "'self'" in d for d in directives)


def test_the_sandbox_and_the_csp_tests_share_the_app_policy() -> None:
    # ui's sandbox writes it into the app's own document, and its CSP tests serve it.
    harness = Path(__file__).parents[2] / "web" / "ui" / "csp" / "app-policy.txt"
    assert harness.read_text().strip() == APP_POLICY
