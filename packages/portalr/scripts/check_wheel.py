"""Fail unless portalr's wheel carries both UIs, mini apps' sandbox, their typefaces and licences.

That includes each UI's third-party notices, written by its build from the packages in its
bundle (web/notices): present, and an entry for each package, with its licence's text.

The app's styles must hold ui's own classes too.

An application installs the wheel to serve the UIs.

Usage: scripts/check_wheel.py   (from portalr's directory, after its `build` task)
"""

import re
import sys
import tomllib
import zipfile
from pathlib import Path

UIS = ("app", "admin")
LICENCES = ("OFL-schibsted-grotesk.txt", "OFL-fragment-mono.txt", "tremor.txt", "NOTICE")
"""The typefaces' licences, and Tremor's, whose charts ``ui`` adapts, and the notice saying so."""

SANDBOX = "portalr/static/sandbox/index.html"
"""The page mini apps run in, which app's build writes beside the UIs (portalr ADR-0051)."""

NOTICES = "THIRD-PARTY-NOTICES.txt"
"""Written beside each UI's index.html by its build, from the bundle; never by hand."""

BETWEEN_ENTRIES = re.compile(r"\n={80}\n(?=## )")
"""Where one package's entry ends (web/notices/src/render.ts): the separator, and a heading."""

HEADING = re.compile(r"## .+@[^@\s]+")
"""An entry's heading, name and version."""

LICENCE_HEADING = re.compile(r"^--- (licen[cs]es?|copying|unlicense)", re.IGNORECASE | re.MULTILINE)
"""A licence text in an entry (LICENSE, LICENCE, LICENSES, COPYING, UNLICENSE), not a NOTICE or
COPYRIGHT alone, which can be only a statement. web/notices/src/collect.ts reads it the same way,
and both are held to web/notices/file-names.json."""

SENTINELS = ("react", "tailwindcss")
"""Packages both UIs bundle, whose entries the notices must have. Tailwind reaches them only
through a stylesheet's @import, which the plugin finds by reading the stylesheet: if that stops
working, its entry goes first."""

STYLED = ".bg-accent"
"""A class of ui's own components: an app's styles without it lack the kit's (portalr ADR-0018)."""


def notices_problems(ui: str, text: str) -> list[str]:
    """What is wrong with a UI's notices.

    No entries, a heading that isn't one, an entry with neither a licence text (LICENSE, COPYING
    and the like) nor a reason, or no entry for a package both UIs bundle.
    """
    entries = BETWEEN_ENTRIES.split(text)[1:]
    if not entries:
        return [f"the {ui} UI's {NOTICES} has no packages"]
    problems: list[str] = []
    names: list[str] = []
    for entry in entries:
        heading, _, rest = entry.partition("\n")
        if not HEADING.fullmatch(heading):
            problems.append(f"the {ui} UI's notices have an entry headed {heading!r}")
            continue
        name = heading.removeprefix("## ")
        names.append(name.rpartition("@")[0])
        if not LICENCE_HEADING.search(entry) and "ships no licence text." not in rest:
            problems.append(f"the {ui} UI's notices have no licence text for {name}")
    problems.extend(
        f"the {ui} UI's notices lack {sentinel}, which it bundles"
        for sentinel in SENTINELS
        if sentinel not in names
    )
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
        notices = {
            ui: built.read(name).decode()
            for ui in UIS
            if (name := f"portalr/static/{ui}/{NOTICES}") in names
        }
    if manifests := sorted(n for n in names if "/.vite/" in n and not n.endswith("/")):
        # Vite's manifest is the size check's, and not the UI's to serve (portalr ADR-0044).
        sys.stderr.write(f"check_wheel: {wheel.name} carries {', '.join(manifests)}\n")
        return 1
    if missing := [ui for ui in UIS if f"portalr/static/{ui}/index.html" not in names]:
        sys.stderr.write(f"check_wheel: {wheel.name} lacks the {', '.join(missing)} UI\n")
        return 1
    if SANDBOX not in names:
        sys.stderr.write(f"check_wheel: {wheel.name} lacks mini apps' sandbox, {SANDBOX}\n")
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
        if ui not in notices:
            sys.stderr.write(f"check_wheel: {wheel.name} lacks the {ui} UI's {NOTICES}\n")
            return 1
        problems = notices_problems(ui, notices[ui])
        if problems:
            sys.stderr.write("".join(f"check_wheel: {problem}\n" for problem in problems))
            return 1
    sys.stdout.write(
        f"check_wheel: {wheel.name} carries {' and '.join(UIS)}, with their typefaces and notices\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
