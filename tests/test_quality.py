"""Quality gates the linters cannot express, over every package, the examples and the root's own
Python: the gate each library's quality ADR records (artifactr ADR-0015, reflexr ADR-0013,
evalr ADR-0005 and relayr ADR-0009), and the same gate over portalr's TypeScript.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
FOLDERS = ("packages", "examples", "scripts", "tests")
SUPPRESSION = re.compile(r"#\s*(type:\s*ignore|pyright:\s*ignore|noqa|pragma:\s*no\s*cover)")
TS_SUPPRESSION = re.compile(r"@ts-(ignore|expect-error|nocheck)|biome-ignore")
WEB = ROOT / "packages" / "portalr" / "web"


def _is_python(path: Path) -> bool:
    """A Python file: a ``.py`` file, or a script without a suffix that Python runs."""
    if path.suffix:
        return path.suffix == ".py"
    with path.open("rb") as file:
        return file.readline().startswith(b"#!/usr/bin/env python")


def _sources() -> list[Path]:
    return sorted(
        path
        for folder in FOLDERS
        for path in (ROOT / folder).rglob("*")
        if path.is_file() and not {".venv", "node_modules"} & set(path.parts) and _is_python(path)
    )


def _web_sources() -> list[Path]:
    return sorted(
        path
        for path in WEB.rglob("*")
        if path.suffix in {".ts", ".tsx"} and "node_modules" not in path.parts
    )


def test_the_examples_and_the_roots_python_are_checked() -> None:
    checked = {path.relative_to(ROOT).parts[0] for path in _sources()}
    assert {"packages", "examples", "tests"} <= checked


@pytest.mark.parametrize("path", _sources(), ids=lambda path: str(path.relative_to(ROOT)))
def test_no_inline_suppressions(path: Path) -> None:
    # Restructure the code instead: suppressions hide the problems the gates exist to find.
    found = [
        f"{number}: {line.strip()}"
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if SUPPRESSION.search(line) and path.name != "test_quality.py"
    ]
    assert not found, "\n".join(found)


def test_the_web_packages_are_checked() -> None:
    assert _web_sources()


@pytest.mark.parametrize("path", _web_sources(), ids=lambda path: str(path.relative_to(ROOT)))
def test_no_inline_suppressions_in_typescript(path: Path) -> None:
    # The same gate over TypeScript: fix the type or the lint, never silence it.
    found = [
        f"{number}: {line.strip()}"
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if TS_SUPPRESSION.search(line)
    ]
    assert not found, "\n".join(found)
