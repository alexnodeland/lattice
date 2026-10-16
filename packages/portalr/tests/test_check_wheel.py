"""The wheel check (scripts/check_wheel.py): its reading of a UI's third-party notices, and a
fabricated wheel through ``main``."""

import importlib.util
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

SEPARATOR = "=" * 80


def _script() -> ModuleType:
    path = Path(__file__).parent.parent / "scripts" / "check_wheel.py"
    spec = importlib.util.spec_from_file_location("check_wheel", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_wheel = _script()

REACT = "## react@19.3.0\nLicence: MIT\n\n--- LICENSE\n\nMIT text"
SHIM = "## shim@2.0.0\nLicence: MIT\n\nThis package ships no licence text. Why."


def _notices(*entries: str) -> str:
    return "Third-party notices\n\n" + "".join(f"\n{SEPARATOR}\n{entry}\n" for entry in entries)


def test_notices_with_an_entry_and_text_for_each_package_are_in_order() -> None:
    assert check_wheel.notices_problems("app", _notices(REACT, SHIM)) == []


def test_notices_without_packages_fail() -> None:
    assert check_wheel.notices_problems("app", "Third-party notices\n") == [
        "the app UI's THIRD-PARTY-NOTICES.txt has no packages"
    ]


def test_an_entry_with_neither_text_nor_a_reason_fails() -> None:
    bare = "## bare@1.0.0\nLicence: MIT"
    assert check_wheel.notices_problems("app", _notices(REACT, bare)) == [
        "the app UI's notices have no licence text for bare@1.0.0"
    ]


def test_an_entry_with_only_a_notice_has_no_licence_text() -> None:
    noticed = "## noticed@1.0.0\nLicence: Apache-2.0\n\n--- NOTICE\n\nCopyright 2026"
    assert check_wheel.notices_problems("app", _notices(REACT, noticed)) == [
        "the app UI's notices have no licence text for noticed@1.0.0"
    ]


def test_notices_that_lack_a_package_the_uis_bundle_fail() -> None:
    other = "## other@1.0.0\nLicence: MIT\n\n--- LICENSE\n\nMIT text"
    assert check_wheel.notices_problems("admin", _notices(other)) == [
        "the admin UI's notices lack react, which it bundles"
    ]


def test_a_heading_that_isnt_one_fails() -> None:
    text = _notices(REACT) + f"\n{SEPARATOR}\n## no version here\nLicence: MIT\n"
    assert check_wheel.notices_problems("app", text) == [
        "the app UI's notices have an entry headed '## no version here'"
    ]


def test_a_licence_text_holding_an_equals_line_stays_in_its_entry() -> None:
    tricky = f"## tricky@1.0.0\nLicence: MIT\n\n--- LICENSE\n\nbefore\n{SEPARATOR}\nafter"
    assert check_wheel.notices_problems("app", _notices(REACT, tricky)) == []


def _wheel(directory: Path, notices: dict[str, str | None]) -> None:
    """A wheel of this version in dist/, with both UIs, and these notices (None: absent)."""
    (directory / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n')
    (directory / "dist").mkdir()
    with zipfile.ZipFile(directory / "dist" / "portalr-1.2.3-py3-none-any.whl", "w") as built:
        for ui in ("app", "admin"):
            built.writestr(f"portalr/static/{ui}/index.html", "")
            built.writestr(f"portalr/static/{ui}/assets/face.woff2", "")
            text = notices[ui]
            if text is not None:
                built.writestr(f"portalr/static/{ui}/{check_wheel.NOTICES}", text)
        built.writestr("portalr/static/app/assets/app.css", ".bg-accent{}")
        for licence in check_wheel.LICENCES:
            built.writestr(f"portalr-1.2.3.dist-info/licenses/{licence}", "")


def test_a_wheel_with_both_uis_notices_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _wheel(tmp_path, {"app": _notices(REACT), "admin": _notices(REACT)})
    monkeypatch.chdir(tmp_path)
    assert check_wheel.main() == 0
    assert "with their typefaces and notices" in capsys.readouterr().out


def test_a_wheel_without_a_uis_notices_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _wheel(tmp_path, {"app": _notices(REACT), "admin": None})
    monkeypatch.chdir(tmp_path)
    assert check_wheel.main() == 1
    assert "lacks the admin UI's THIRD-PARTY-NOTICES.txt" in capsys.readouterr().err


def test_a_wheel_with_a_bad_entry_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bare = "## bare@1.0.0\nLicence: MIT"
    _wheel(tmp_path, {"app": _notices(REACT), "admin": _notices(REACT, bare)})
    monkeypatch.chdir(tmp_path)
    assert check_wheel.main() == 1
    assert "no licence text for bare@1.0.0" in capsys.readouterr().err
