"""Install each wheel at the lowest versions its pyproject allows, from PyPI, and import it.

Usage: scripts/lowest_direct.py [PACKAGE...]   (default: every package that ships a wheel)

Each package goes into a fresh environment with every extra it declares, its own direct
dependencies at the lowest versions its ranges allow (`--resolution lowest-direct`), and its
lattice siblings from PyPI, not the workspace (`--no-sources`): what a user who pins the floors
gets. Then every module of the package is imported. A floor below what the code needs, such as
`artifactr-ai>=0.2.0` for code that imports what only 0.3.0 has, fails here.

EXPECTED lists the packages known to fail until their floors are raised, as each package's release
does (the owner's step): each must still fail, so a package that starts passing is flagged, and
must come off the list. The others must pass, as every package does now. It exits 1 if any package
does other than expected.
"""

import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = {
    "lattice-core": "lattice_core",
    "evalr": "evalr",
    "artifactr": "artifactr",
    "grantr": "grantr",
    "reflexr": "reflexr",
    "relayr": "relayr",
    "portalr": "portalr",
}
"""Each package that ships a wheel, by its directory, and the module it installs, in release order.
stackr ships none."""
EXPECTED: dict[str, tuple[str, str]] = {
    "artifactr": (
        "its provider and connected apps' tiers import lattice_core.capabilities, which"
        " lattice-core-ai 0.2.0, the newest on PyPI, lacks: its floor rises to 0.3.0 once that"
        " is published",
        "No module named 'lattice_core.capabilities'",
    ),
    "grantr": (
        "its store of approvals imports lattice_core.approvals, which lattice-core-ai 0.2.0, the"
        " newest on PyPI, lacks: its floor rises to 0.3.0 once that is published",
        "No module named 'lattice_core.approvals'",
    ),
}
"""The packages whose floors are known to be too low: why, and what the import says when it fails
so. A package goes on it, and comes off as its floor is raised (lattice ADR-0029)."""
CHECK = """
import importlib, pkgutil, sys

module = sys.argv[1]
package = importlib.import_module(module)
names = [info.name for info in pkgutil.walk_packages(package.__path__, f"{module}.")]
for name in names:
    importlib.import_module(name)
print(f"{module}: every module imports ({len(names) + 1})")
"""


def checked(directory: str, module: str) -> str | None:
    """Install the package at its lowest direct versions and import every module.

    Returns:
        None if every module imports; otherwise what the import printed to stderr.

    Raises:
        RuntimeError: If the environment couldn't be made or the package couldn't be installed,
            as when PyPI can't be reached or nothing satisfies the ranges: never a floor's fault
            that EXPECTED names.
    """
    path = ROOT / "packages" / directory
    project = tomllib.loads((path / "pyproject.toml").read_text())["project"]
    extras = sorted(project.get("optional-dependencies", {}))
    requirement = f"{path}[{','.join(extras)}]" if extras else str(path)
    python_version = f"{sys.version_info[0]}.{sys.version_info[1]}"
    with tempfile.TemporaryDirectory() as scratch:
        python = Path(scratch) / "bin" / "python"
        install = [
            ["uv", "venv", "--quiet", "--python", python_version, scratch],
            [
                *("uv", "pip", "install", "--quiet", "--no-sources"),
                *("--resolution", "lowest-direct", "--python", str(python), requirement),
            ],
        ]
        for step in install:
            if subprocess.run(step, cwd=scratch, check=False).returncode != 0:
                raise RuntimeError(f"{' '.join(step[:3])} failed")
        done = subprocess.run(
            [str(python), "-I", "-c", CHECK, module],
            cwd=scratch,
            check=False,
            capture_output=True,
            text=True,
        )
        sys.stdout.write(done.stdout + done.stderr)
        return None if done.returncode == 0 else done.stderr


def say(line: str) -> None:
    """Write a line of the job's log."""
    sys.stdout.write(f"{line}\n")
    sys.stdout.flush()


def main(names: list[str]) -> int:
    """Check each package named, or every one, against EXPECTED; return 1 if any differs."""
    unexpected: list[str] = []
    for directory in names or list(PACKAGES):
        say(f"::group::{directory}")
        try:
            failed = checked(directory, PACKAGES[directory])
        except RuntimeError as error:
            failed, broke = None, str(error)
        else:
            broke = None
        say("::endgroup::")
        known = EXPECTED.get(directory)
        if broke is not None:
            verdict = f"FAIL: {directory} couldn't be installed ({broke}), so nothing was checked"
        elif failed is None and known is None:
            verdict = f"ok: {directory} passes"
        elif failed is None:
            verdict = f"FAIL: {directory} passes now: take it off EXPECTED"
        elif known is not None and known[1] in failed:
            verdict = f"ok: {directory} fails, as expected: {known[0]}"
        else:
            verdict = f"FAIL: {directory} doesn't import at its lowest direct versions"
            if known is not None:
                verdict += f", and not as EXPECTED says ({known[1]!r})"
        if verdict.startswith("FAIL"):
            unexpected.append(directory)
        say(verdict)
    return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
