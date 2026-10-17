"""The editor: an app's browser build, served as released, under a policy that reaches nowhere."""

import base64
import hashlib
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from artifactr.files.fastapi import editor_app, editor_policy

SCRIPT = "\nimport init from './app-1a2b.js';\nawait init();\n"
INDEX = f"""<!DOCTYPE html><html><head>
<script type="module">{SCRIPT}</script>
<style>body {{ margin: 0; }}</style></head><body><canvas></canvas></body></html>"""


def sha256(text: str) -> str:
    return base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()


@pytest.fixture
def build(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text(INDEX)
    (tmp_path / "app-1a2b.js").write_text("export default async function init() {}")
    (tmp_path / "app-1a2b_bg.wasm").write_bytes(b"\0asm\1\0\0\0")
    return tmp_path


def test_the_policy_runs_the_pages_own_script_by_its_hash_and_reaches_nowhere() -> None:
    policy = dict(d.split(" ", 1) for d in editor_policy(INDEX).split("; "))
    assert policy == {
        "default-src": "'self' blob:",
        "script-src": f"'self' 'sha256-{sha256(SCRIPT)}' 'wasm-unsafe-eval'",
        "style-src": "'self' 'unsafe-inline'",
        "img-src": "'self' blob: data:",
        "worker-src": "'self'",
        "object-src": "'none'",
        "base-uri": "'none'",
        "form-action": "'none'",
        "frame-ancestors": "'none'",
    }


def test_a_script_loaded_by_its_url_adds_no_hash() -> None:
    page = '<script type="module" src="./app.js"></script>'
    assert "sha256" not in editor_policy(page)


def test_the_page_is_served_unchanged_and_revalidated(build: Path) -> None:
    client = TestClient(editor_app(build))
    page = client.get("/")
    assert page.text == INDEX
    assert page.headers["content-security-policy"] == editor_policy(INDEX)
    assert page.headers["cache-control"] == "no-cache"
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["referrer-policy"] == "no-referrer"
    assert page.headers["cross-origin-resource-policy"] == "same-origin"
    assert page.headers["cross-origin-opener-policy"] == "same-origin"


def test_hashed_files_are_cached_for_good_and_typed(build: Path) -> None:
    client = TestClient(editor_app(build))
    wasm = client.get("/app-1a2b_bg.wasm")
    assert wasm.headers["content-type"] == "application/wasm"
    assert wasm.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert client.get("/app-1a2b.js").headers["cache-control"].endswith("immutable")
    missing = client.get("/elsewhere.js")
    assert missing.status_code == 404
    assert missing.headers["cache-control"] == "no-cache", "a miss is never kept for good"
    assert "content-security-policy" in missing.headers


def test_a_directory_without_a_page_is_no_build(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        editor_app(tmp_path)
