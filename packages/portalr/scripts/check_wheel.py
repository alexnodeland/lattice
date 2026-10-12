"""Fail unless portalr's wheel carries both UIs, their typefaces, and the typefaces' licence.

The app's styles must hold ui's own classes too.

An application installs the wheel to serve the UIs.

Usage: scripts/check_wheel.py   (from portalr's directory, after its `build` task)
"""

import sys
import tomllib
import zipfile
from pathlib import Path

UIS = ("app", "admin")
LICENCES = ("OFL-schibsted-grotesk.txt", "OFL-fragment-mono.txt")

STYLED = ".bg-accent"
"""A class of ui's own components: an app's styles without it lack the kit's (portalr ADR-0018)."""


def main() -> int:
    """Check this version's wheel in dist/ for each UI's index; an older one there is no matter."""
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    wheel = Path("dist") / f"portalr-{version}-py3-none-any.whl"
    if not wheel.exists():
        sys.stderr.write(f"check_wheel: no {wheel.name} in dist/; run portalr's build first\n")
        return 1
    with zipfile.ZipFile(wheel) as built:
        names = set(built.namelist())
        styles = "".join(
            built.read(name).decode()
            for name in names
            if name.startswith("portalr/static/app/assets/") and name.endswith(".css")
        )
    if missing := [ui for ui in UIS if f"portalr/static/{ui}/index.html" not in names]:
        sys.stderr.write(f"check_wheel: {wheel.name} lacks the {', '.join(missing)} UI\n")
        return 1
    if STYLED not in styles:
        sys.stderr.write(f"check_wheel: the app's styles in {wheel.name} lack ui's classes\n")
        return 1
    if unfaced := [
        ui
        for ui in UIS
        if not any(
            n.startswith(f"portalr/static/{ui}/assets/") and n.endswith(".woff2") for n in names
        )
    ]:
        sys.stderr.write(f"check_wheel: the {', '.join(unfaced)} UI has no typefaces\n")
        return 1
    licences = {Path(n).name for n in names if ".dist-info/licenses/" in n}
    if unlicensed := [licence for licence in LICENCES if licence not in licences]:
        sys.stderr.write(f"check_wheel: {wheel.name} lacks {', '.join(unlicensed)}\n")
        return 1
    sys.stdout.write(
        f"check_wheel: {wheel.name} carries {' and '.join(UIS)}, with their typefaces\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
