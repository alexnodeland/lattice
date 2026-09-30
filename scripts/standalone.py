"""Install a package outside the workspace, as a user would, and import it.

Usage: scripts/standalone.py (from a package's directory, after moon's `build` tasks)

The package's wheel, from its dist/, goes into a fresh environment outside the workspace with
every extra it declares, and the siblings it needs go in as their wheels, by path. uv checks
every range between them, so a range that a sibling's version doesn't satisfy fails to resolve.
Then every module of the package is imported, and its version checked against pyproject.toml.
"""

import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CHECK = """
import importlib, pkgutil, sys

module, version = sys.argv[1:]
package = importlib.import_module(module)
names = [info.name for info in pkgutil.walk_packages(package.__path__, f"{module}.")]
for name in names:
    importlib.import_module(name)
assert package.__version__ == version, (package.__version__, version)
print(f"{module} {version}: every module imports ({len(names) + 1})")
"""
"""What runs in the environment: import every module, and compare the version."""

REQUIREMENT = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[([^\]]*)\])?")


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _pyproject(directory: Path) -> dict[str, Any]:
    return tomllib.loads((directory / "pyproject.toml").read_text())


def _distributions() -> dict[str, Path]:
    """Every package that ships a wheel, by its normalized distribution name."""
    found: dict[str, Path] = {}
    for path in sorted((ROOT / "packages").glob("*/pyproject.toml")):
        pyproject = tomllib.loads(path.read_text())
        if "build-system" in pyproject:
            found[_normalize(pyproject["project"]["name"])] = path.parent
    return found


def _requirements(directory: Path, extras: set[str]) -> list[tuple[str, set[str]]]:
    """The names a package requires, with their extras: always, and under the given extras."""
    project = _pyproject(directory)["project"]
    strings: list[str] = list(project.get("dependencies", []))
    for extra, more in project.get("optional-dependencies", {}).items():
        if extra in extras:
            strings += more
    found: list[tuple[str, set[str]]] = []
    for string in strings:
        match = REQUIREMENT.match(string)
        assert match, f"{directory.name}: can't read the requirement {string!r}"
        wanted = {extra.strip() for extra in (match[2] or "").split(",") if extra.strip()}
        found.append((_normalize(match[1]), wanted))
    return found


def _siblings(directory: Path, extras: set[str], members: dict[str, Path]) -> set[str]:
    """The siblings a package needs with these extras, and the siblings they need in turn."""
    needed: set[str] = set()
    pending = [(directory, extras)]
    while pending:
        current, current_extras = pending.pop()
        for name, wanted in _requirements(current, current_extras):
            if name in members and members[name] != directory and name not in needed:
                needed.add(name)
                pending.append((members[name], wanted))
    return needed


def _wheel(directory: Path) -> Path:
    project = _pyproject(directory)["project"]
    name = re.sub(r"[-_.]+", "_", project["name"]).lower()
    wheel = directory / "dist" / f"{name}-{project['version']}-py3-none-any.whl"
    if not wheel.exists():
        raise SystemExit(f"standalone: {wheel.relative_to(ROOT)} is missing; build it first")
    return wheel


def main() -> int:
    """Install the package in the current directory alone, and import every module."""
    directory = Path.cwd()
    pyproject = _pyproject(directory)
    project = pyproject["project"]
    extras = set(project.get("optional-dependencies", {}))
    members = _distributions()
    siblings = sorted(_siblings(directory, extras, members))
    backend = pyproject.get("tool", {}).get("uv", {}).get("build-backend", {})
    module = backend.get("module-name", project["name"].replace("-", "_"))

    wheel = _wheel(directory)
    requirement = f"{wheel}[{','.join(sorted(extras))}]" if extras else str(wheel)
    python = f"{sys.version_info.major}.{sys.version_info.minor}"
    with tempfile.TemporaryDirectory() as scratch:
        environment = Path(scratch) / "venv"
        uv = ["uv", "--quiet"]
        subprocess.run([*uv, "venv", "--python", python, environment], check=True)
        siblings_wheels = [_wheel(members[name]) for name in siblings]
        install = [*uv, "pip", "install", "--python", environment, requirement, *siblings_wheels]
        subprocess.run(install, check=True, cwd=scratch)
        done = subprocess.run(
            [environment / "bin" / "python", "-c", CHECK, module, project["version"]], cwd=scratch
        )
    return done.returncode


if __name__ == "__main__":
    sys.exit(main())
