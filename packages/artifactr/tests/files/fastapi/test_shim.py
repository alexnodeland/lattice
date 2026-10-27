"""The editor's shim: lattice's page beside a build, framed by the portal, framing the build."""

import base64
import hashlib
import re
from pathlib import Path

import pytest

from artifactr.files.craft import CRAFTS
from artifactr.files.fastapi import editor_app, editor_policy
from artifactr.files.fastapi.shim import PATH, SCRIPT, STYLE, shim_page, shim_policy
from tests.clients import entered

PORTAL = "https://portal.example"
INDEX = "<!DOCTYPE html><html><body><script>start()</script></body></html>"


def sha256(text: str) -> str:
    return f"'sha256-{base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()}'"


@pytest.fixture
def build(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text(INDEX)
    return tmp_path


def test_the_shim_names_the_app_its_surface_and_the_portal() -> None:
    page = shim_page(CRAFTS["gridcraft"], PORTAL)
    assert (
        '<html lang="en" data-app="gridcraft" data-portals="https://portal.example" '
        'data-surface="parent" data-methods="">'
    ) in page
    assert f"<script>{SCRIPT}</script>" in page
    assert f"<style>{STYLE}</style>" in page
    assert "<title>GridCraft</title>" in page


def test_wordcrafts_shim_relays_its_parent_bridge() -> None:
    page = shim_page(CRAFTS["wordcraft"], PORTAL)
    assert 'data-app="wordcraft"' in page
    assert 'data-surface="parent"' in page
    assert "<title>WordCraft</title>" in page


def test_a_javascript_apis_shim_calls_only_the_methods_allowed() -> None:
    page = shim_page(CRAFTS["effectcraft"], PORTAL, ["info", "request"])
    assert 'data-surface="global" data-methods="info request"' in page


def test_the_shims_policy_runs_its_own_code_frames_its_origin_and_is_framed_by_the_portal() -> None:
    policy = dict(d.split(" ", 1) for d in shim_policy(PORTAL).split("; "))
    assert policy == {
        "default-src": "'none'",
        "script-src": sha256(SCRIPT),
        "style-src": sha256(STYLE),
        "frame-src": "'self'",
        "frame-ancestors": PORTAL,
        "base-uri": "'none'",
        "form-action": "'none'",
    }


@pytest.mark.parametrize(
    ("app", "portal", "methods", "refused"),
    [
        ("photocraft", PORTAL, [], "PhotoCraft's build has no host surface"),
        ("gridcraft", "https://portal.example/app", [], "the portal is an origin"),
        ("gridcraft", "javascript:alert(1)", [], "the portal is an origin"),
        ("gridcraft", "http://portal.example", [], "give it https, or http on loopback"),
        ("gridcraft", [], [], "the portal is an origin.*name one"),
        ("gridcraft", [PORTAL, "https://*.example"], [], "no wildcard"),
        ("gridcraft", PORTAL, ["open"], "GridCraft's build has no JavaScript API"),
        ("effectcraft", PORTAL, ["info request"], "a method is named as JavaScript names one"),
    ],
)
def test_a_shim_that_cant_reach_or_be_reached_is_refused(
    app: str, portal: str | list[str], methods: list[str], refused: str
) -> None:
    with pytest.raises(ValueError, match=refused):
        shim_page(CRAFTS[app], portal, methods)


def test_the_editor_serves_the_shim_beside_the_build_and_lets_it_frame_the_build(
    build: Path,
) -> None:
    client = entered(editor_app(build, craft=CRAFTS["pdfcraft"], portal=PORTAL))
    shim = client.get(PATH)
    assert shim.text == shim_page(CRAFTS["pdfcraft"], PORTAL)
    assert shim.headers["content-security-policy"] == shim_policy(PORTAL)
    assert shim.headers["x-content-type-options"] == "nosniff"
    assert shim.headers["cache-control"] == "no-cache"
    page = client.get("/")
    assert page.text == INDEX
    assert page.headers["content-security-policy"] == editor_policy(INDEX, portal=PORTAL)
    ancestors = re.search(r"frame-ancestors ([^;]+)", page.headers["content-security-policy"])
    assert ancestors is not None
    assert ancestors[1] == f"'self' {PORTAL}", "the shim, and the portal above it"


def test_without_a_bridge_there_is_no_shim(build: Path) -> None:
    assert entered(editor_app(build)).get(PATH).status_code == 404


def test_a_shim_needs_its_app_and_its_portal(build: Path) -> None:
    with pytest.raises(ValueError, match="a shim needs both"):
        editor_app(build, craft=CRAFTS["gridcraft"])
    with pytest.raises(ValueError, match="a shim needs both"):
        editor_app(build, portal=PORTAL)


def test_a_build_with_files_where_the_shim_goes_is_refused(build: Path) -> None:
    (build / ".lattice").mkdir()
    with pytest.raises(ValueError, match="the build has files where the shim is served"):
        editor_app(build, craft=CRAFTS["gridcraft"], portal=PORTAL)


TAILNET = "https://my-machine.my-tailnet.ts.net"
LOOPBACK = "http://127.0.0.1:8800"


def test_told_several_portals_the_shim_names_them_all_once_as_a_browser_compares_them() -> None:
    page = shim_page(
        CRAFTS["gridcraft"], [LOOPBACK, "HTTPS://My-Machine.my-tailnet.ts.net:443/", LOOPBACK]
    )
    assert f'data-portals="{LOOPBACK} {TAILNET}"' in page
    assert shim_page(CRAFTS["gridcraft"], [LOOPBACK]) == shim_page(CRAFTS["gridcraft"], LOOPBACK)


def test_every_policy_is_framed_by_each_portal_and_the_editor_serves_them(build: Path) -> None:
    both = [LOOPBACK, TAILNET]
    shim = dict(d.split(" ", 1) for d in shim_policy(both).split("; "))
    assert shim["frame-ancestors"] == f"{LOOPBACK} {TAILNET}"
    editor = dict(d.split(" ", 1) for d in editor_policy(INDEX, portal=both).split("; "))
    assert editor["frame-ancestors"] == f"'self' {LOOPBACK} {TAILNET}"
    client = entered(editor_app(build, craft=CRAFTS["gridcraft"], portal=both))
    assert client.get(PATH).headers["content-security-policy"] == shim_policy(both)
    assert client.get("/").headers["content-security-policy"] == editor_policy(INDEX, portal=both)


def test_one_portal_is_served_as_before(build: Path) -> None:
    # The default behaviour, a string: the same page and policies as a list of one.
    assert shim_policy(PORTAL) == shim_policy([PORTAL])
    assert editor_policy(INDEX, portal=PORTAL) == editor_policy(INDEX, portal=[PORTAL])
    assert f"frame-ancestors {PORTAL}" in shim_policy(PORTAL)
    assert f"frame-ancestors 'self' {PORTAL}" in editor_policy(INDEX, portal=PORTAL)


def test_the_editor_and_the_shim_set_no_cookie(build: Path) -> None:
    # Cookies are host-scoped, not port-scoped, and SameSite ignores the port: on a tailnet or
    # loopback, the portal, the sandbox and each editor share a host and differ by port alone, so
    # a cookie any of them set would be sent to the others. None sets one, and none ever may.
    client = entered(editor_app(build, craft=CRAFTS["gridcraft"], portal=[LOOPBACK, TAILNET]))
    for path in (PATH, "/", "/missing"):
        assert "set-cookie" not in client.get(path).headers, path
