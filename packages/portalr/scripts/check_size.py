"""Fail when a UI's built bundle is larger than its budget (size-budget.json).

Three measures per UI, each the gzip size in bytes of the JavaScript and CSS Vite wrote (the
typefaces and the notices are not counted):

- ``initial``: what a first visit loads before it renders: the entry script, the chunks index.html
  preloads, and its stylesheets;
- ``total``: every script and stylesheet, which a visit loads in pieces, as it opens routes;
- ``largest``: the largest single file, which is Streamdown's chunk (the chat's markdown), shared
  by both UIs (portalr ADR-0015), so a second large dependency shows up here.

A budget is a ceiling set a little above the size at the time, not a target: raise it in the same
change that grows a bundle, and say why in the change.

Usage: scripts/check_size.py   (from portalr's directory, after app's and admin's builds)
"""

import gzip
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
STATIC = ROOT / "src" / "portalr" / "static"
BUDGET = ROOT / "size-budget.json"
UIS = ("app", "admin")
MEASURES = ("initial", "total", "largest")
LOADED = re.compile(r'<(?:script|link)\b[^>]*?\b(?:src|href)="([^"]+\.(?:js|css))"')
"""A script or a stylesheet or a preload that index.html names."""


def gzipped(path: Path) -> int:
    """The gzip size of a file, in bytes."""
    return len(gzip.compress(path.read_bytes(), compresslevel=9, mtime=0))


def measure(ui: str, static: Path | None = None) -> dict[str, int]:
    """The three measures of a built UI, in `static` (default: the package's own)."""
    root = (static or STATIC) / ui
    files = [p for p in root.rglob("*") if p.suffix in {".js", ".css"}]
    sizes = {p: gzipped(p) for p in files}
    prefix = f"/portalr/{ui}/"
    loaded = {
        root / name.removeprefix(prefix)
        for name in LOADED.findall((root / "index.html").read_text())
        if name.startswith(prefix)
    }
    if missing := [p for p in loaded if p not in sizes]:
        raise SystemExit(
            f"check_size: {ui}'s index.html names {missing[0].name}, which isn't built"
        )
    return {
        "initial": sum(sizes[p] for p in loaded),
        "total": sum(sizes.values()),
        "largest": max(sizes.values()),
    }


def problems(ui: str, measured: dict[str, int], budget: dict[str, int]) -> list[str]:
    """What is over budget, or has none."""
    found: list[str] = []
    for measure_ in MEASURES:
        if measure_ not in budget:
            found.append(f"{ui} has no {measure_} budget in size-budget.json")
        elif measured[measure_] > budget[measure_]:
            found.append(
                f"{ui}'s {measure_} is {measured[measure_]:,} bytes gzipped, over its budget of "
                f"{budget[measure_]:,}"
            )
    return found


def main() -> int:
    """Print each UI's sizes against its budget; return 1 if any is over."""
    budgets = json.loads(BUDGET.read_text())
    failed: list[str] = []
    for ui in UIS:
        measured = measure(ui)
        sys.stdout.write(
            f"check_size: {ui}: "
            + ", ".join(f"{m} {measured[m]:,}/{budgets[ui].get(m, 0):,}" for m in MEASURES)
            + "\n"
        )
        failed += problems(ui, measured, budgets[ui])
    sys.stderr.write("".join(f"check_size: {problem}\n" for problem in failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
