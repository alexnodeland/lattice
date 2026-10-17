"""Fail when a UI's built bundle is larger than its budget (size-budget.json).

Three measures per UI, each the gzip size in bytes of the JavaScript and CSS Vite wrote (the
typefaces and the notices are not counted):

- ``initial``: what a first visit loads before it renders: the entry script, the chunks index.html
  preloads, and its stylesheets;
- ``total``: every script and stylesheet that loads without an add-on, which a visit loads in
  pieces, as it opens routes;
- ``largest``: the largest single file of those, which is Streamdown's chunk (the chat's markdown),
  shared by both UIs (portalr ADR-0015), so a second large dependency shows up here.

An add-on is a module of ui's ``src/on-demand/``, which Markdown imports only when a message needs
it (portalr ADR-0044). What an add-on's import reaches that the UI doesn't load without add-ons, as
Vite's manifest says, is that add-on's: what its first use loads. It has a ``total`` and a
``largest`` of its own, under the UI's ``addons``, and counts toward neither of the UI's; a chunk
two add-ons share counts in each. Every add-on a UI holds has a budget, and every budget an add-on.

A budget is a ceiling set a little above the size at the time, not a target: raise it in the same
change that grows a bundle, and say why in the change.

Usage: scripts/check_size.py   (from portalr's directory, after app's and admin's builds)
"""

import gzip
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
STATIC = ROOT / "src" / "portalr" / "static"
BUDGET = ROOT / "size-budget.json"
UIS = ("app", "admin")
MEASURES = ("initial", "total", "largest")
ADDON_MEASURES = ("total", "largest")
LOADED = re.compile(r'<(?:script|link)\b[^>]*?\b(?:src|href)="([^"]+\.(?:js|css))"')
"""A script or a stylesheet or a preload that index.html names."""
MANIFEST = Path(".vite") / "manifest.json"
"""Where Vite writes its manifest, in each UI's directory; the wheel leaves it out."""
ADDON = re.compile(r"(?:^|/)ui/src/on-demand/([a-z][a-z-]*)\.tsx?$")
"""An add-on's module, by the path of its source, as the manifest keys it, and its name."""

type Manifest = dict[str, dict[str, Any]]
type Sizes = dict[str, int]


def gzipped(path: Path) -> int:
    """The gzip size of a file, in bytes."""
    return len(gzip.compress(path.read_bytes(), compresslevel=9, mtime=0))


def reached(manifest: Manifest, starts: Iterable[str], stop: frozenset[str]) -> set[str]:
    """The chunks `starts` import, statically or dynamically, all the way down, but `stop`."""
    seen: set[str] = set()
    todo = list(starts)
    while todo:
        key = todo.pop()
        if key in seen:
            continue
        seen.add(key)
        chunk = manifest[key]
        imported = (*chunk.get("imports", ()), *chunk.get("dynamicImports", ()))
        todo += [name for name in imported if name not in stop]
    return seen


def files_of(manifest: Manifest, keys: Iterable[str]) -> set[str]:
    """The files that the chunks `keys` are, with their stylesheets."""
    return {name for key in keys for name in (manifest[key]["file"], *manifest[key].get("css", ()))}


def addon_files(manifest: Manifest) -> dict[str, set[str]]:
    """Each add-on's files: what its import reaches that the UI's entry doesn't without add-ons."""
    addons = {found[1]: key for key in manifest if (found := ADDON.search(key))}
    entries = [key for key, chunk in manifest.items() if chunk.get("isEntry")]
    base = files_of(manifest, reached(manifest, entries, frozenset(addons.values())))
    return {
        name: files_of(manifest, reached(manifest, [key], frozenset())) - base
        for name, key in addons.items()
    }


def measured(sizes: dict[Path, int], files: Iterable[Path]) -> Sizes:
    """The total and the largest of `files`."""
    counted = [sizes[path] for path in files]
    return {"total": sum(counted), "largest": max(counted, default=0)}


def measure(ui: str, static: Path | None = None) -> dict[str, Any]:
    """A built UI's measures, in `static` (default: the package's own), and each add-on's."""
    root = (static or STATIC) / ui
    index = root / "index.html"
    if not index.is_file():
        raise SystemExit(f"check_size: {ui} isn't built: {index} is missing (run its build first)")
    manifest = root / MANIFEST
    if not manifest.is_file():
        raise SystemExit(f"check_size: {ui} has no manifest: {manifest} is missing")
    files = [p for p in root.rglob("*") if p.suffix in {".js", ".css"}]
    sizes = {p: gzipped(p) for p in files}
    prefix = f"/portalr/{ui}/"
    loaded = {
        root / name.removeprefix(prefix)
        for name in LOADED.findall(index.read_text())
        if name.startswith(prefix)
    }
    if missing := [p for p in loaded if p not in sizes]:
        raise SystemExit(
            f"check_size: {ui}'s index.html names {missing[0].name}, which isn't built"
        )
    addons = {
        name: {root / file for file in names}
        for name, names in addon_files(json.loads(manifest.read_text())).items()
    }
    if stale := sorted(p.name for paths in addons.values() for p in paths if p not in sizes):
        raise SystemExit(f"check_size: {ui}'s manifest names {stale[0]}, which isn't built")
    with_addons = {path for paths in addons.values() for path in paths}
    return {
        "initial": sum(sizes[p] for p in loaded),
        **measured(sizes, [p for p in files if p not in with_addons]),
        "addons": {name: measured(sizes, paths) for name, paths in addons.items()},
    }


def over(what: str, sizes: Sizes, budget: Sizes, measures: Iterable[str]) -> list[str]:
    """Each of `what`'s `measures` over its budget, or without one."""
    found: list[str] = []
    for name in measures:
        if name not in budget:
            found.append(f"{what} has no {name} budget in size-budget.json")
        elif sizes[name] > budget[name]:
            found.append(
                f"{what}'s {name} is {sizes[name]:,} bytes gzipped, over its budget of "
                f"{budget[name]:,}"
            )
    return found


def problems(ui: str, measured: dict[str, Any], budget: dict[str, Any]) -> list[str]:
    """What is over budget, or has none; and a budget for an add-on the UI doesn't hold."""
    addons: dict[str, Sizes] = measured["addons"]
    ceilings: dict[str, Sizes] = budget.get("addons", {})
    found = over(ui, measured, budget, MEASURES)
    for name, sizes in addons.items():
        if name in ceilings:
            found += over(f"{ui}'s add-on {name}", sizes, ceilings[name], ADDON_MEASURES)
        else:
            found.append(f"{ui}'s add-on {name} has no budget in size-budget.json")
    found += [
        f"size-budget.json has a budget for {ui}'s add-on {name}, which {ui} doesn't hold"
        for name in ceilings
        if name not in addons
    ]
    return found


def report(ui: str, measured: dict[str, Any], budget: dict[str, Any]) -> str:
    """A UI's sizes against its budget, and each add-on's, a line each."""
    ceilings: dict[str, Sizes] = budget.get("addons", {})
    lines = [
        f"{ui}: " + ", ".join(f"{m} {measured[m]:,}/{budget.get(m, 0):,}" for m in MEASURES),
        *(
            f"{ui}'s add-on {name}: "
            + ", ".join(
                f"{m} {sizes[m]:,}/{ceilings.get(name, {}).get(m, 0):,}" for m in ADDON_MEASURES
            )
            for name, sizes in measured["addons"].items()
        ),
    ]
    return "".join(f"check_size: {line}\n" for line in lines)


def main() -> int:
    """Print each UI's sizes against its budget; return 1 if any is over."""
    budgets = json.loads(BUDGET.read_text())
    if absent := [ui for ui in UIS if ui not in budgets]:
        raise SystemExit(f"check_size: size-budget.json has no budget for {', '.join(absent)}")
    failed: list[str] = []
    for ui in UIS:
        sizes = measure(ui)
        sys.stdout.write(report(ui, sizes, budgets[ui]))
        failed += problems(ui, sizes, budgets[ui])
    sys.stderr.write("".join(f"check_size: {problem}\n" for problem in failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
