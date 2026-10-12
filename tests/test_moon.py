"""moon's edges agree with the workspaces.

moon infers no edge from a requirement with a range, so each project's moon.yml states its
dependsOn, and this test holds it to the siblings its pyproject.toml requires, or, for a web
package, to the workspace packages its package.json depends on.
"""

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).parent.parent
WORKSPACE: dict[str, str] = yaml.safe_load((ROOT / ".moon" / "workspace.yml").read_text())[
    "projects"
]
SOURCES = {
    project: path
    for project, path in WORKSPACE.items()
    if (ROOT / path / "pyproject.toml").exists()
}
"""The uv workspace's members."""
WEB = {
    project: path for project, path in WORKSPACE.items() if (ROOT / path / "package.json").exists()
}
"""The Bun workspace's packages."""
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


def _depends_on(project: str) -> set[str]:
    config = yaml.safe_load((ROOT / WORKSPACE[project] / "moon.yml").read_text()) or {}
    return set(config.get("dependsOn", []))


@pytest.mark.parametrize("project", sorted(SOURCES))
def test_depends_on_matches_the_pyproject(project: str) -> None:
    assert _depends_on(project) == _siblings(project) | NOT_IN_PYPROJECT.get(project, set())


def _package(project: str) -> dict[str, Any]:
    return json.loads((ROOT / WEB[project] / "package.json").read_text())


PACKAGES = {_package(project)["name"]: project for project in WEB}
"""Each web package's moon project, by its package name."""


@pytest.mark.parametrize("project", sorted(WEB))
def test_depends_on_matches_the_package_json(project: str) -> None:
    package = _package(project)
    workspace = {
        name
        for field in ("dependencies", "devDependencies")
        for name, version in package.get(field, {}).items()
        if version.startswith("workspace:")
    }
    assert workspace <= PACKAGES.keys()
    assert _depends_on(project) == {PACKAGES[name] for name in workspace}


@pytest.mark.parametrize("project", sorted(SOURCES))
def test_siblings_come_from_the_workspace(project: str) -> None:
    # Without { workspace = true }, uv would look for a sibling on PyPI.
    sources = _pyproject(project).get("tool", {}).get("uv", {}).get("sources", {})
    distributions = {name for name, member in PROJECTS.items() if member in _siblings(project)}
    assert {
        _normalize(name) for name, source in sources.items() if source == {"workspace": True}
    } == distributions
