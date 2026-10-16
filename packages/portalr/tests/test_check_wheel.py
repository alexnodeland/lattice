"""The wheel check's reading of a UI's third-party notices (scripts/check_wheel.py)."""

import importlib.util
from pathlib import Path
from types import ModuleType

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


def _notices(*entries: str) -> str:
    return "Third-party notices\n\n" + "".join(f"\n{SEPARATOR}\n{entry}\n" for entry in entries)


def test_notices_with_an_entry_and_text_for_each_package_are_in_order() -> None:
    text = _notices(
        "## @tanstack/react-router@1.0.0\nLicence: MIT\n\n--- LICENSE\n\nMIT text",
        "## shim@2.0.0\nLicence: MIT\n\nThis package ships no licence text. Why.",
    )
    assert check_wheel.notices_problems("app", text) == []


def test_notices_without_packages_fail() -> None:
    assert check_wheel.notices_problems("app", "Third-party notices\n") == [
        "the app UI's THIRD-PARTY-NOTICES.txt has no packages"
    ]


def test_an_entry_with_neither_text_nor_a_reason_fails() -> None:
    text = _notices(
        "## @tanstack/react-router@1.0.0\nLicence: MIT\n\n--- LICENSE\n\nMIT text",
        "## bare@1.0.0\nLicence: MIT",
    )
    assert check_wheel.notices_problems("app", text) == [
        "the app UI's notices have no licence text for bare@1.0.0"
    ]


def test_notices_that_lack_a_package_the_ui_bundles_fail() -> None:
    text = _notices("## other@1.0.0\nLicence: MIT\n\n--- LICENSE\n\nMIT text")
    assert check_wheel.notices_problems("admin", text) == [
        "the admin UI's notices lack recharts, which it bundles"
    ]
