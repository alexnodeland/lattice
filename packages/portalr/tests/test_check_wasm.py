"""The WebAssembly check (scripts/check_wasm.py): every module in a build, and what isn't listed."""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def _script() -> ModuleType:
    path = Path(__file__).parent.parent / "scripts" / "check_wasm.py"
    spec = importlib.util.spec_from_file_location("check_wasm", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_wasm = _script()

FILED = b"\0asm\x01\0\0\0\x01\x04\x01\x60\0\0"
"""A module built as a file of its own: its magic, version 1, and a type section."""
INLINED = b"\0asm\x01\0\0\0"
"""A module inlined in a chunk: the smallest there is, whose base64 ends in padding."""


def sha(module: bytes) -> str:
    return hashlib.sha256(module).hexdigest()


def built(root: Path, ui: str = "app", *, chunk: str = "") -> Path:
    """A built UI: an index, a chunk, and a font that holds no module."""
    assets = root / ui / "assets"
    assets.mkdir(parents=True)
    (root / ui / "index.html").write_text("<!doctype html>")
    (assets / "index-abc123.js").write_text(f"export const entry = 1;{chunk}")
    (assets / "face.woff2").write_bytes(b"wOF2" + bytes(range(256)))
    return root


def test_a_build_without_webassembly_holds_no_module(tmp_path: Path) -> None:
    assert check_wasm.modules("app", built(tmp_path)) == ({}, [])


def test_a_module_is_found_as_a_file_and_inlined_as_base64_padded_or_not(tmp_path: Path) -> None:
    padded = base64.b64encode(INLINED).decode()
    assert padded.endswith("=")
    unpadded = base64.b64encode(FILED).decode().rstrip("=")
    static = built(tmp_path, chunk=f'const a = "{padded}"; const b = "data:;base64,{unpadded}";')
    (static / "app" / "assets" / "x_bg-def456.wasm").write_bytes(FILED)
    assert check_wasm.modules("app", static) == (
        {sha(INLINED): "assets/index-abc123.js", sha(FILED): "assets/x_bg-def456.wasm"},
        [],
    )


def test_raw_magic_in_a_script_is_reported_and_in_a_font_is_chance(tmp_path: Path) -> None:
    static = built(tmp_path)
    (static / "app" / "assets" / "blob-abc.js").write_bytes(b"const a = '" + FILED + b"';")
    (static / "app" / "assets" / "face.woff2").write_bytes(b"wOF2" + FILED)
    assert check_wasm.modules("app", static) == ({}, ["assets/blob-abc.js"])


def test_the_magics_encoding_inside_another_base64_run_is_not_a_module(tmp_path: Path) -> None:
    other = base64.b64encode(b"\x89PNG" + bytes(5) + INLINED).decode()
    assert "AGFzbQ" in other
    assert check_wasm.modules("app", built(tmp_path, chunk=f'const png = "{other}";')) == ({}, [])


def test_a_ui_that_is_not_built_stops_the_check_with_a_message(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match=r"app isn't built: .*index.html is missing"):
        check_wasm.modules("app", tmp_path)


def test_a_module_not_listed_one_listed_but_absent_and_raw_magic_are_problems() -> None:
    found = {sha(FILED): "assets/x.wasm", sha(INLINED): "assets/fonts.js"}
    listed = [
        {"package": "@excalidraw/excalidraw", "sha256": sha(INLINED)},
        {"package": "gone", "sha256": "0" * 64},
    ]
    assert check_wasm.problems("app", found, ["assets/blob.js"], listed) == [
        f"app's assets/x.wasm holds a WebAssembly module (sha256 {sha(FILED)}) that "
        "web/wasm-allowlist.json doesn't list",
        f"web/wasm-allowlist.json lists gone's module (sha256 {'0' * 64}) for app, "
        "which app's build doesn't hold",
        "app's assets/blob.js holds WebAssembly's magic as raw bytes, not as base64",
    ]
    assert check_wasm.problems("app", {sha(INLINED): "assets/fonts.js"}, [], listed[:1]) == []


def test_the_committed_allowlist_names_both_uis_each_module_by_package_and_digest() -> None:
    allowlist = json.loads(check_wasm.ALLOWLIST.read_text())
    assert set(allowlist) == set(check_wasm.UIS)
    for listed in allowlist.values():
        for entry in listed:
            assert set(entry) == {"package", "sha256"}
            assert len(entry["sha256"]) == 64


def test_an_allowlist_without_a_ui_stops_the_check_with_a_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps({"app": []}))
    monkeypatch.setattr(check_wasm, "ALLOWLIST", allowlist)
    with pytest.raises(SystemExit, match=r"no list for admin"):
        check_wasm.main()


def test_main_reports_each_ui_and_fails_on_a_module_not_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    static = tmp_path / "static"
    for ui in check_wasm.UIS:
        built(static, ui)
    allowlist = tmp_path / "allowlist.json"
    monkeypatch.setattr(check_wasm, "STATIC", static)
    monkeypatch.setattr(check_wasm, "ALLOWLIST", allowlist)
    allowlist.write_text(json.dumps({"app": [], "admin": []}))
    assert check_wasm.main() == 0
    assert "check_wasm: app: 0 WebAssembly module(s)" in capsys.readouterr().out
    (static / "admin" / "assets" / "x.wasm").write_bytes(FILED)
    assert check_wasm.main() == 1
    assert "admin's assets/x.wasm holds a WebAssembly module" in capsys.readouterr().err
