from pathlib import Path

import httpx

from portalr.fastapi import Site
from portalr.fastapi.ui import IMMUTABLE, NO_CACHE, policy


async def test_a_hashed_asset_is_cached_for_good(client: httpx.AsyncClient) -> None:
    response = await client.get("/app/assets/index-abc123.js")
    assert response.status_code == 200
    assert response.text == "console.log('app')"
    assert response.headers["cache-control"] == IMMUTABLE


async def test_a_client_side_route_gets_the_index_which_is_never_cached(
    client: httpx.AsyncClient,
) -> None:
    for path in ("/app/", "/app/threads/thr_1", "/app/index.html"):
        response = await client.get(path)
        assert response.status_code == 200, path
        assert response.text.startswith("<!doctype html>")
        assert response.headers["cache-control"] == NO_CACHE


POLICY = (
    "default-src 'self'",
    # First-party WebAssembly, in either UI (portalr ADR-0041); never 'unsafe-eval'.
    "script-src 'self' 'wasm-unsafe-eval'",
    "style-src 'self'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self' https://project.supabase.co",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
)
"""The policy both UIs share, directive by directive, so a widening is a visible change."""


async def test_both_uis_share_one_policy_on_the_index_and_on_a_hashed_script(
    client: httpx.AsyncClient, ui: Path
) -> None:
    # admin built beside app; a worker script takes its policy from its own response.
    (ui / "admin" / "assets").mkdir(parents=True)
    (ui / "admin" / "index.html").write_text("<!doctype html><title>admin</title>")
    (ui / "admin" / "assets" / "worker-def456.js").write_text("self.onmessage = () => {}")
    for path in (
        "/app/",
        "/app/assets/index-abc123.js",
        "/admin/",
        "/admin/assets/worker-def456.js",
    ):
        headers = (await client.get(path)).headers
        assert tuple(headers["content-security-policy"].split("; ")) == POLICY, path
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["referrer-policy"] == "no-referrer"


def test_supabase_on_the_applications_own_origin_is_already_self() -> None:
    on_a_path = policy(Site(supabase_url="/", supabase_key="sb_publishable_x"))
    assert "connect-src 'self';" in on_a_path
    assert " /" not in on_a_path


async def test_a_path_out_of_the_ui_gets_the_index_not_the_file(client: httpx.AsyncClient) -> None:
    response = await client.get("/app/..%2Fsecret.txt")
    assert "outside the UI" not in response.text


async def test_a_ui_without_its_slash_is_redirected(client: httpx.AsyncClient) -> None:
    response = await client.get("/app")
    assert response.status_code == 308
    assert response.headers["location"] == "app/"


async def test_a_ui_that_isnt_built_is_not_found(client: httpx.AsyncClient) -> None:
    assert (await client.get("/admin/")).status_code == 404


async def test_config_names_supabase_the_surfaces_and_the_tools(client: httpx.AsyncClient) -> None:
    config = (await client.get("/config.json")).json()
    assert config == {
        "supabase": {"url": "https://project.supabase.co", "key": "sb_publishable_x"},
        "surfaces": {
            "artifactr": "/artifactr/v1",
            "reflexr": "/reflexr/v1",
            "grantr": "",
            "portalr": "/portalr/v1",
            "relayr": None,
        },
        "readers": dict.fromkeys(
            ("tempo", "loki", "prometheus", "langfuse", "litellm", "grafana"), True
        ),
        "people": False,
        "editors": {},
    }


async def test_a_missing_asset_is_not_found(client: httpx.AsyncClient) -> None:
    response = await client.get("/app/assets/index-old.js")
    assert response.status_code == 404


async def test_a_path_with_a_nul_gets_the_index(client: httpx.AsyncClient) -> None:
    response = await client.get("/app/a%00b")
    assert response.status_code == 200
    assert response.text.startswith("<!doctype html>")


def test_the_markdown_csp_tests_serve_the_routers_own_policy() -> None:
    # ui's CSP tests serve its Markdown with this policy (web/ui/csp): the router's, for an
    # application with Supabase on a path of its own origin, so `connect-src` is `'self'` alone.
    harness = Path(__file__).parents[2] / "web" / "ui" / "csp" / "policy.txt"
    site = Site(supabase_url="/", supabase_key="sb_publishable_x")
    assert harness.read_text().strip() == policy(site)
