"""The editor's shim: lattice's page beside a build, framed by the portal, framing the build."""

import base64
import hashlib
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from artifactr.files.craft import CRAFTS
from artifactr.files.fastapi import editor_app, editor_policy
from artifactr.files.fastapi.shim import PATH, SCRIPT, STYLE, shim_page, shim_policy

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
        '<html lang="en" data-app="gridcraft" data-portal="https://portal.example" '
        'data-surface="parent" data-methods="">'
    ) in page
    assert f"<script>{SCRIPT}</script>" in page
    assert f"<style>{STYLE}</style>" in page
    assert "<title>GridCraft</title>" in page


def test_a_javascript_apis_shim_calls_only_the_methods_allowed() -> None:
    page = shim_page(CRAFTS["filmcraft"], PORTAL, ["inspect", "openProject"])
    assert 'data-surface="global" data-methods="inspect openProject"' in page


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
        ("wordcraft", PORTAL, [], "WordCraft's build has no host surface"),
        ("gridcraft", "https://portal.example/app", [], "the portal is an origin"),
        ("gridcraft", "javascript:alert(1)", [], "the portal is an origin"),
        ("gridcraft", PORTAL, ["open"], "GridCraft's build has no JavaScript API"),
    ],
)
def test_a_shim_that_cant_reach_or_be_reached_is_refused(
    app: str, portal: str, methods: list[str], refused: str
) -> None:
    with pytest.raises(ValueError, match=refused):
        shim_page(CRAFTS[app], portal, methods)


def test_the_editor_serves_the_shim_beside_the_build_and_lets_it_frame_the_build(
    build: Path,
) -> None:
    client = TestClient(editor_app(build, bridge=CRAFTS["pdfcraft"], portal=PORTAL))
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
    assert TestClient(editor_app(build)).get(PATH).status_code == 404


def test_a_shim_needs_its_app_and_its_portal(build: Path) -> None:
    with pytest.raises(ValueError, match="a shim needs both"):
        editor_app(build, bridge=CRAFTS["gridcraft"])
    with pytest.raises(ValueError, match="a shim needs both"):
        editor_app(build, portal=PORTAL)


def test_a_build_with_files_where_the_shim_goes_is_refused(build: Path) -> None:
    (build / ".lattice").mkdir()
    with pytest.raises(ValueError, match="the build has files where the shim is served"):
        editor_app(build, bridge=CRAFTS["gridcraft"], portal=PORTAL)
