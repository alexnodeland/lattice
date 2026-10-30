"""Nightly's fidelity job installs the libraries each app's worker image installs (#783).

A crafting app whose CLI links system libraries, such as Blender's X11 and GL, lists them under
`packages` in stackr's copier.yml, which its worker's image installs. Nightly runs the same CLI on
a bare runner, so its fidelity job installs them too, in a step only that app's run takes: without
libEGL, Blender started, read a scene, and died drawing it.
"""

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).parent.parent


def _steps() -> list[dict[str, Any]]:
    nightly = yaml.safe_load((ROOT / ".github" / "workflows" / "nightly.yml").read_text())
    return nightly["jobs"]["fidelity"]["steps"]


def test_each_apps_packages_are_installed_in_its_fidelity_run() -> None:
    crafts = yaml.safe_load((ROOT / "packages" / "stackr" / "copier.yml").read_text())["crafts"]
    needing = {name: c["packages"] for name, c in crafts["default"].items() if c.get("packages")}
    assert needing, "an app's packages are found where copier.yml lists them"
    steps = _steps()
    for name, packages in needing.items():
        [step] = [s for s in steps if s.get("if") == f"matrix.app == '{name}'"]
        installed = set(step["run"].split())
        assert set(packages) <= installed, f"{name}'s fidelity run misses its libraries"


def test_the_packages_are_installed_before_the_fidelity_runs() -> None:
    steps = _steps()
    runs = [i for i, s in enumerate(steps) if s.get("run") == "moon run artifactr:fidelity"]
    installs = [i for i, s in enumerate(steps) if "apt-get install" in s.get("run", "")]
    assert runs
    assert installs
    assert max(installs) < min(runs)
