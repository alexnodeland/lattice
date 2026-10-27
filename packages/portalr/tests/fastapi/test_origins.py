"""Several portal origins (portalr ADR-0084): aliases, the places beside them, and a union policy.

A deployment reached at its loopback address and at its tailnet name is two portal origins; mini
apps and the editors are framed from each, so each has an apps origin and editors beside it, the
sandbox answers them all and is framed by every portal, and the portal's policy frames them all.
"""

from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from starlette.types import Message, Receive, Scope, Send

from artifactr.files.fastapi.shim import SCRIPT
from grantr.grants import Grants
from portalr.fastapi import Place, SandboxOrigin, Site, beside
from portalr.fastapi.sandbox import APP_POLICY, sandbox_policy
from portalr.fastapi.ui import policy
from tests.fastapi.conftest import Stack, app_for

LOOPBACK = "http://127.0.0.1:8800"
TAILNET = "https://my-machine.my-tailnet.ts.net"
APPS = "http://127.0.0.1:8801"
EDITORS = {"files:gridcraft": "http://127.0.0.1:8802/", "files:pdfcraft": "http://127.0.0.1:8803/"}
TAILNET_APPS = "https://my-machine.my-tailnet.ts.net:8801"
TAILNET_EDITORS = {
    "files:gridcraft": "https://my-machine.my-tailnet.ts.net:8802/",
    "files:pdfcraft": "https://my-machine.my-tailnet.ts.net:8803/",
}
KEY = "sb_publishable_x"
PAGE = "<!doctype html><title>Sandbox</title><script>relay()</script>"


def site(supabase_url: str = "/", **given: Any) -> Site:
    return Site(supabase_url=supabase_url, supabase_key=KEY, **given)


# beside: the port-sibling rule


def test_beside_moves_the_apps_and_each_editor_to_the_extra_origins_host_on_their_ports() -> None:
    place = beside(LOOPBACK, TAILNET, apps=APPS, editors=EDITORS)
    assert place == Place(apps=TAILNET_APPS, editors=TAILNET_EDITORS)
    # The extra's scheme, and an editor's path, are kept; a bracketed IPv6 host too.
    moved = beside(
        TAILNET, "http://[::1]:8800", apps=APPS, editors={"files:cadcraft": f"{LOOPBACK}/cad/"}
    )
    assert moved == Place(
        apps="http://[::1]:8801", editors={"files:cadcraft": "http://[::1]:8800/cad/"}
    )
    assert beside(LOOPBACK, TAILNET, apps=None, editors={}) == Place()


@pytest.mark.parametrize(
    ("extra", "apps", "editors", "said"),
    [
        (LOOPBACK, APPS, {}, "the portal's own origin, not another address of it"),
        ("http://127.0.0.1:8800/", APPS, {}, "the portal's own origin"),
        (
            TAILNET,
            "https://apps.example.com",
            {},
            "mini apps is at https://apps.example.com, with no port",
        ),
        (
            TAILNET,
            None,
            {"files:gridcraft": "https://grid.example.com/"},
            "files:gridcraft's editor is at",
        ),
        ("http://lan.local:8800", APPS, {}, "give it https, or http on loopback"),
        (TAILNET, "http://apps.lan", {}, "mini apps is an origin"),
    ],
)
def test_beside_refuses_what_it_cannot_derive(
    extra: str, apps: str | None, editors: dict[str, str], said: str
) -> None:
    with pytest.raises(ValueError, match=said):
        beside(LOOPBACK, extra, apps=apps, editors=editors)


# Site's aliases


def test_aliases_are_kept_by_the_portal_origin_as_a_browser_compares_it() -> None:
    made = site(
        apps=APPS,
        editors=EDITORS,
        origin="HTTP://127.0.0.1:8800/",
        aliases={
            "HTTPS://My-Machine.my-tailnet.ts.net:443/": {
                "apps": TAILNET_APPS,
                "editors": TAILNET_EDITORS,
            }
        },
    )
    assert made.origin == LOOPBACK
    assert made.aliases == {TAILNET: Place(apps=TAILNET_APPS, editors=TAILNET_EDITORS)}


@pytest.mark.parametrize(
    ("given", "said"),
    [
        ({"origin": "http://portal.lan:8800"}, "the portal is an origin"),
        ({"aliases": {"https://*.ts.net": {}}}, "no wildcard"),
        ({"aliases": {TAILNET: {}, f"{TAILNET}:443": {}}}, "aliased twice"),
        (
            {"aliases": {TAILNET: {"apps": "http://10.0.0.5:8801"}}},
            "an IP address that isn't loopback",
        ),
        (
            {
                "origin": LOOPBACK,
                "aliases": {
                    TAILNET: {
                        "editors": {"files:gridcraft": "https://apps.example.com/x"},
                        "apps": "https://apps.example.com",
                    }
                },
            },
            "give it an origin of its own",
        ),
        (
            {"aliases": {TAILNET: {"editors": {"markdown:math": "https://e.example"}}}},
            "no native file's app",
        ),
    ],
)
def test_an_alias_is_held_to_what_the_canonical_place_is(given: dict[str, Any], said: str) -> None:
    with pytest.raises(ValidationError, match=said):
        site(**given)


@pytest.mark.parametrize(
    "given",
    [
        {"origin": LOOPBACK, "editors": {"files:gridcraft": f"{LOOPBACK}/editor/"}},
        {
            "origin": LOOPBACK,
            "aliases": {TAILNET: {"editors": {"files:gridcraft": f"{TAILNET}/editor/"}}},
        },
    ],
)
def test_an_editor_on_a_portals_own_origin_is_refused_where_that_origin_is_known(
    given: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError, match="give it an origin of its own"):
        site(**given)


def test_aliases_without_the_portals_own_origin_are_refused() -> None:
    with pytest.raises(ValidationError, match="name its own origin too"):
        site(aliases={TAILNET: {}})


def test_an_editor_is_kept_on_its_origin_as_a_browser_compares_it_its_path_kept() -> None:
    made = site(editors={"files:gridcraft": "HTTPS://Editor.Example:443/grid/"})
    assert made.editors == {"files:gridcraft": "https://editor.example/grid/"}


@pytest.mark.parametrize("url", ["https://editor.example/?x=1", "https://editor.example/#top"])
def test_an_editor_with_a_query_or_fragment_is_refused(url: str) -> None:
    with pytest.raises(ValidationError, match="no query or fragment"):
        site(editors={"files:gridcraft": url})


def test_without_aliases_or_an_origin_a_site_is_as_it_was() -> None:
    made = site(apps=APPS, editors=EDITORS)
    assert (made.origin, made.aliases) == (None, {})


# The portal's policy: a union


def test_the_portals_policy_frames_every_place_once_in_order_and_names_no_wildcard() -> None:
    made = site(
        origin=LOOPBACK,
        apps=APPS,
        editors=EDITORS,
        aliases={
            TAILNET: beside(LOOPBACK, TAILNET, apps=APPS, editors=EDITORS),
            # A second alias whose apps origin is the canonical one: named once.
            "https://other.example": {
                "apps": APPS,
                "editors": {"files:gridcraft": "http://127.0.0.1:8802/"},
            },
        },
    )
    expected = (
        f"; frame-src {APPS} http://127.0.0.1:8802 http://127.0.0.1:8803 {TAILNET_APPS} "
        "https://my-machine.my-tailnet.ts.net:8802 https://my-machine.my-tailnet.ts.net:8803;"
    )
    assert expected in policy(made)
    frames = policy(made).split("; frame-src ")[1].split(";")[0].split(" ")
    assert len(frames) == len(set(frames))
    assert "*" not in policy(made)
    assert policy(made) == policy(site(apps=APPS, editors=EDITORS)).replace(
        f"{APPS} http://127.0.0.1:8802 http://127.0.0.1:8803;", expected[len("; frame-src ") :]
    )


# config.json


async def test_config_carries_the_origin_and_each_alias(
    grants: Grants, stack: Stack, ui: Path
) -> None:
    made = site(
        supabase_url="https://project.supabase.co",
        apps=APPS,
        editors=EDITORS,
        origin=LOOPBACK,
        aliases={TAILNET: beside(LOOPBACK, TAILNET, apps=APPS, editors=EDITORS)},
    )
    app = app_for(grants, stack.readers(), None, ui, site=made)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app/portalr"
    ) as client:
        config = (await client.get("/config.json")).json()
        page = await client.get("/app/")
    assert config["origin"] == LOOPBACK
    assert config["aliases"] == {TAILNET: {"apps": TAILNET_APPS, "editors": TAILNET_EDITORS}}
    # The portal sets no cookie, and never may: cookies are host-scoped, not port-scoped, and
    # SameSite ignores the port, so on loopback or a tailnet, where the portal, the sandbox and
    # each editor share a host and differ by port alone, a cookie here would reach them all.
    assert "set-cookie" not in page.headers
    assert page.headers["content-security-policy"] == policy(made)


# The sandbox: every apps origin answered, every portal framing it


@pytest.fixture
def built(tmp_path: Path) -> Path:
    (tmp_path / "sandbox").mkdir()
    (tmp_path / "sandbox" / "index.html").write_text(PAGE)
    return tmp_path


def _client(root: Path, apps: list[str], portals: list[str]) -> httpx.AsyncClient:
    application = FastAPI()

    @application.get("/{path:path}")
    async def anything(path: str) -> dict[str, str]:
        return {"application": path}

    application.add_middleware(SandboxOrigin, apps=apps, portal=portals, root=root)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url=LOOPBACK)


async def test_the_sandbox_answers_each_apps_origin_under_a_policy_framed_by_each_portal(
    built: Path,
) -> None:
    both = [LOOPBACK, TAILNET]
    assert sandbox_policy(both) == f"{APP_POLICY}; frame-ancestors {LOOPBACK} {TAILNET}"
    assert (
        sandbox_policy(LOOPBACK)
        == sandbox_policy([LOOPBACK])
        == f"{APP_POLICY}; frame-ancestors {LOOPBACK}"
    )
    async with _client(built, [APPS, TAILNET_APPS, "https://apps.example.com"], both) as client:
        for host in (
            "127.0.0.1:8801",
            "my-machine.my-tailnet.ts.net:8801",
            "apps.example.com",
            "APPS.example.com:443",
        ):
            response = await client.get("/", headers={"host": host})
            assert (response.status_code, response.text) == (200, PAGE), host
            assert response.headers["content-security-policy"] == sandbox_policy(both)
            # No cookie, as the portal and the editors set none: see the config test above.
            assert "set-cookie" not in response.headers
            missing = await client.get("/portalr/app/", headers={"host": host})
            assert missing.status_code == 404, host
        for host in (
            "127.0.0.1:8800",
            "my-machine.my-tailnet.ts.net",
            "my-machine.my-tailnet.ts.net:8802",
        ):
            response = await client.get("/", headers={"host": host})
            assert response.json() == {"application": ""}, host


async def test_a_websocket_to_any_apps_origin_is_closed(built: Path) -> None:
    sent: list[Message] = []

    async def application(scope: Scope, receive: Receive, send: Send) -> None:
        raise AssertionError("the application never hears an apps' origin")

    async def received() -> Message:
        return {"type": "websocket.connect"}

    async def send(message: Message) -> None:
        sent.append(message)

    sandbox = SandboxOrigin(
        application, apps=[APPS, TAILNET_APPS], portal=[LOOPBACK, TAILNET], root=built
    )
    for host in (b"127.0.0.1:8801", b"my-machine.my-tailnet.ts.net:8801"):
        sent.clear()
        await sandbox(
            {"type": "websocket", "path": "/", "headers": [(b"host", host)]}, received, send
        )
        assert sent == [{"type": "websocket.close", "code": 1008}]


@pytest.mark.parametrize(
    ("apps", "portals"),
    [
        ([APPS, LOOPBACK], [LOOPBACK, TAILNET]),
        ([APPS, "https://my-machine.my-tailnet.ts.net:443"], [LOOPBACK, TAILNET]),
        ([TAILNET_APPS], [LOOPBACK, "https://my-machine.my-tailnet.ts.net:8801"]),
    ],
)
def test_no_apps_origin_may_be_any_portals(apps: list[str], portals: list[str]) -> None:
    with pytest.raises(ValueError, match="share the portal's origin"):
        SandboxOrigin(FastAPI(), apps=apps, portal=portals)


@pytest.mark.parametrize(
    ("apps", "portal", "said"),
    [
        ([], LOOPBACK, "mini apps is an origin.*name one"),
        (APPS, [], "the portal is an origin.*name one"),
        ("http://apps.lan:8801", LOOPBACK, "give it https, or http on loopback"),
        (APPS, "https://*.ts.net", "no wildcard"),
    ],
)
def test_the_sandbox_takes_only_web_origins(
    apps: str | list[str], portal: str | list[str], said: str
) -> None:
    with pytest.raises(ValueError, match=said):
        SandboxOrigin(FastAPI(), apps=apps, portal=portal)


def test_the_csp_tests_run_the_shim_as_artifactr_writes_it() -> None:
    # ui's CSP tests (web/ui/csp/shim.test.ts) frame the editor's shim from two portal origins,
    # in Chromium, with its script as artifactr serves it: the copy is held to the source.
    harness = Path(__file__).parents[2] / "web" / "ui" / "csp" / "shim-script.js"
    assert harness.read_text() == SCRIPT.strip() + "\n"
