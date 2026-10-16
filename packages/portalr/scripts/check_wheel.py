"""Fail unless portalr's wheel carries both UIs, their typefaces, and what they hold's licences.

That includes each UI's third-party notices, written by its build from the packages in its
bundle (web/notices): present, and an entry for each package, with its licence's text.

The app's styles must hold ui's own classes too.

An application installs the wheel to serve the UIs.

Usage: scripts/check_wheel.py   (from portalr's directory, after its `build` task)
"""

import sys
import tomllib
import zipfile
from pathlib import Path

UIS = ("app", "admin")
LICENCES = ("OFL-schibsted-grotesk.txt", "OFL-fragment-mono.txt", "tremor.txt", "NOTICE")
"""The typefaces' licences, and Tremor's, whose charts ``ui`` adapts, and the notice saying so."""

NOTICES = "THIRD-PARTY-NOTICES.txt"
"""Written beside each UI's index.html by its build, from the bundle; never by hand."""

SEPARATOR = "=" * 80
"""What precedes each package's entry in the notices (web/notices/src/render.ts)."""

BUNDLED = {"app": "@tanstack/react-router", "admin": "recharts"}
"""A package each UI certainly bundles, whose entry the notices must have."""

STYLED = ".bg-accent"
"""A class of ui's own components: an app's styles without it lack the kit's (portalr ADR-0018)."""


def notices_problems(ui: str, text: str) -> list[str]:
    """What is wrong with a UI's notices: no entries, an entry with neither text nor a reason."""
    entries = text.split(f"\n{SEPARATOR}\n")[1:]
    if not entries:
        return [f"the {ui} UI's {NOTICES} has no packages"]
    problems: list[str] = []
    names: list[str] = []
    for entry in entries:
        heading, _, rest = entry.partition("\n")
        names.append(heading.removeprefix("## ").rpartition("@")[0])
        if "\n--- " not in entry and "ships no licence text." not in rest:
            problems.append(f"the {ui} UI's notices have no licence text for {heading[3:]}")
    if BUNDLED[ui] not in names:
        problems.append(f"the {ui} UI's notices lack {BUNDLED[ui]}, which it bundles")
    return problems


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
    for ui in UIS:
        name = f"portalr/static/{ui}/{NOTICES}"
        if name not in names:
            sys.stderr.write(f"check_wheel: {wheel.name} lacks the {ui} UI's {NOTICES}\n")
            return 1
        with zipfile.ZipFile(wheel) as built:
            problems = notices_problems(ui, built.read(name).decode())
        if problems:
            sys.stderr.write("".join(f"check_wheel: {problem}\n" for problem in problems))
            return 1
    sys.stdout.write(
        f"check_wheel: {wheel.name} carries {' and '.join(UIS)}, with their typefaces and notices\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
