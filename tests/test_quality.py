"""Quality gates the linters cannot express, over every package, the examples and the root's own
Python: the gate each library's quality ADR records (artifactr ADR-0015, reflexr ADR-0013,
evalr ADR-0005 and relayr ADR-0009).
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
FOLDERS = ("packages", "examples", "scripts", "tests")
SUPPRESSION = re.compile(r"#\s*(type:\s*ignore|pyright:\s*ignore|noqa|pragma:\s*no\s*cover)")


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
        if path.is_file() and ".venv" not in path.parts and _is_python(path)
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
