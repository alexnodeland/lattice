"""moon's edges agree with the workspace.

moon infers no edge from a requirement with a range, so each project's moon.yml states its
dependsOn, and this test holds it to the siblings its pyproject.toml requires.
"""

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).parent.parent
SOURCES: dict[str, str] = yaml.safe_load((ROOT / ".moon" / "workspace.yml").read_text())["projects"]
REQUIREMENT = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)")

NOT_IN_PYPROJECT = {"stackr": {"artifactr", "reflexr", "evalr"}}
"""Edges no pyproject.toml records: stackr's template generates applications on the libraries."""


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _pyproject(project: str) -> dict[str, Any]:
    return tomllib.loads((ROOT / SOURCES[project] / "pyproject.toml").read_text())


PROJECTS = {_normalize(_pyproject(project)["project"]["name"]): project for project in SOURCES}
"""Each workspace member's moon project, by its distribution name."""


def _required(project: str) -> set[str]:
    """Every name a project requires: always, under an extra, or in a dependency group."""
    pyproject = _pyproject(project)
    metadata = pyproject["project"]
    strings: list[Any] = [
        *metadata.get("dependencies", []),
        *(item for extra in metadata.get("optional-dependencies", {}).values() for item in extra),
        *(item for group in pyproject.get("dependency-groups", {}).values() for item in group),
    ]
    names: set[str] = set()
    for string in strings:
        if isinstance(string, str):  # not an { include-group = ... }
            match = REQUIREMENT.match(string)
            assert match, string
            names.add(_normalize(match[1]))
    return names


def _siblings(project: str) -> set[str]:
    """The other projects a project's pyproject.toml requires."""
    return {PROJECTS[name] for name in _required(project) if name in PROJECTS} - {project}


@pytest.mark.parametrize("project", sorted(SOURCES))
def test_depends_on_matches_the_pyproject(project: str) -> None:
    config = yaml.safe_load((ROOT / SOURCES[project] / "moon.yml").read_text()) or {}
    declared = set(config.get("dependsOn", []))
    assert declared == _siblings(project) | NOT_IN_PYPROJECT.get(project, set())


@pytest.mark.parametrize("project", sorted(SOURCES))
def test_siblings_come_from_the_workspace(project: str) -> None:
    # Without { workspace = true }, uv would look for a sibling on PyPI.
    sources = _pyproject(project).get("tool", {}).get("uv", {}).get("sources", {})
    distributions = {name for name, member in PROJECTS.items() if member in _siblings(project)}
    assert {
        _normalize(name) for name, source in sources.items() if source == {"workspace": True}
    } == distributions
