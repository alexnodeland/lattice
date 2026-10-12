"""Fail unless portalr's built wheel carries both UIs: an application installs it to serve them.

Usage: scripts/check_wheel.py   (from portalr's directory, after its `build` task)
"""

import sys
import tomllib
import zipfile
from pathlib import Path

UIS = ("app", "admin")


def main() -> int:
    """Check this version's wheel in dist/ for each UI's index; an older one there is no matter."""
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    wheel = Path("dist") / f"portalr-{version}-py3-none-any.whl"
    if not wheel.exists():
        sys.stderr.write(f"check_wheel: no {wheel.name} in dist/; run portalr's build first\n")
        return 1
    names = set(zipfile.ZipFile(wheel).namelist())
    if missing := [ui for ui in UIS if f"portalr/static/{ui}/index.html" not in names]:
        sys.stderr.write(f"check_wheel: {wheel.name} lacks the {', '.join(missing)} UI\n")
        return 1
    sys.stdout.write(f"check_wheel: {wheel.name} carries {' and '.join(UIS)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
