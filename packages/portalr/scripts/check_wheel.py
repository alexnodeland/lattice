"""Fail unless portalr's built wheel carries both UIs, and the app's styles hold ui's classes.

An application installs the wheel to serve the UIs.

Usage: scripts/check_wheel.py   (from portalr's directory, after its `build` task)
"""

import sys
import tomllib
import zipfile
from pathlib import Path

UIS = ("app", "admin")

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
    sys.stdout.write(f"check_wheel: {wheel.name} carries {' and '.join(UIS)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
