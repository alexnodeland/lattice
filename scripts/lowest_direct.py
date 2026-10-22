"""Install each wheel at the lowest versions its pyproject allows, from PyPI, and import it.

Usage: scripts/lowest_direct.py [PACKAGE...]   (default: every package that ships a wheel)

Each package goes into a fresh environment with every extra it declares, its own direct
dependencies at the lowest versions its ranges allow (`--resolution lowest-direct`), and its
lattice siblings from PyPI, not the workspace (`--no-sources`): what a user who pins the floors
gets. Then every module of the package is imported. A floor below what the code needs, such as
`lattice-core-ai>=0.1.0` for code that imports what only 0.2.0 has, fails here.

EXPECTED lists the packages known to fail until their floors are raised, as each package's release
does (the owner's step): each must still fail, so a package that starts passing is flagged, and
must come off the list. The others must pass. It exits 1 if any package does other than expected.
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
EXPECTED: dict[str, str] = {
    "artifactr": (
        "needs lattice-core-ai>=0.2.0 (it imports lattice_core.integrations) and "
        "pydantic-ai-slim>=2.53 (agent/runner.py imports repair_messages, new in 2.53)"
    ),
    "grantr": "needs lattice-core-ai>=0.2.0: it imports lattice_core.integrations",
    "relayr": "needs artifactr-ai>=0.3.0, lattice-core-ai>=0.2.0 and pydantic-ai-slim>=2.53",
    "portalr": "needs lattice-core-ai>=0.2.0, and grantr[fastapi]>=0.2.0",
}
"""The packages whose floors are known to be too low (the v0.2 release audit), and why: each comes
off as its floor is raised (lattice ADR-0029)."""
CHECK = """
import importlib, pkgutil, sys

module = sys.argv[1]
package = importlib.import_module(module)
names = [info.name for info in pkgutil.walk_packages(package.__path__, f"{module}.")]
for name in names:
    importlib.import_module(name)
print(f"{module}: every module imports ({len(names) + 1})")
"""


def passes(directory: str, module: str) -> bool:
    """Whether the package, at its lowest direct versions, installs and imports every module."""
    path = ROOT / "packages" / directory
    extras = sorted(
        tomllib.loads((path / "pyproject.toml").read_text())["project"].get(
            "optional-dependencies", {}
        )
    )
    requirement = f"{path}[{','.join(extras)}]" if extras else str(path)
    with tempfile.TemporaryDirectory() as scratch:
        python = Path(scratch) / "bin" / "python"
        steps = [
            [
                "uv",
                "venv",
                "--quiet",
                "--python",
                f"{sys.version_info[0]}.{sys.version_info[1]}",
                scratch,
            ],
            [
                "uv",
                "pip",
                "install",
                "--quiet",
                "--no-sources",
                "--resolution",
                "lowest-direct",
                "--python",
                str(python),
                requirement,
            ],
            [str(python), "-I", "-c", CHECK, module],
        ]
        for step in steps:
            if subprocess.run(step, cwd=scratch, check=False).returncode != 0:
                return False
    return True


def say(line: str) -> None:
    """Write a line of the job's log."""
    sys.stdout.write(f"{line}\n")
    sys.stdout.flush()


def main(names: list[str]) -> int:
    """Check each package named, or every one, against EXPECTED; return 1 if any differs."""
    unexpected: list[str] = []
    for directory in names or list(PACKAGES):
        say(f"::group::{directory}")
        passed = passes(directory, PACKAGES[directory])
        say("::endgroup::")
        if passed == (directory not in EXPECTED):
            outcome = "passes" if passed else f"fails, as expected: {EXPECTED[directory]}"
            say(f"ok: {directory} {outcome}")
        elif passed:
            unexpected.append(directory)
            say(f"FAIL: {directory} passes now: take it off EXPECTED in scripts/lowest_direct.py")
        else:
            unexpected.append(directory)
            say(f"FAIL: {directory} doesn't install or import at its lowest direct versions")
    return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
