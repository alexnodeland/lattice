"""Fail unless portalr's built wheel carries both UIs: an application installs it to serve them.

Usage: scripts/check_wheel.py   (from portalr's directory, after its `build` task)
"""

import sys
import zipfile
from pathlib import Path

UIS = ("app", "admin")


def main() -> int:
    """Check every wheel in dist/ for each UI's index."""
    wheels = sorted(Path("dist").glob("portalr-*.whl"))
    if not wheels:
        sys.stderr.write("check_wheel: no wheel in dist/; run portalr's build first\n")
        return 1
    for wheel in wheels:
        names = set(zipfile.ZipFile(wheel).namelist())
        if missing := [ui for ui in UIS if f"portalr/static/{ui}/index.html" not in names]:
            sys.stderr.write(f"check_wheel: {wheel.name} lacks the {', '.join(missing)} UI\n")
            return 1
        sys.stdout.write(f"check_wheel: {wheel.name} carries {' and '.join(UIS)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
