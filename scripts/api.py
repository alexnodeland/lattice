"""Fail on a break in a package's public API that a change adds, unless the change marks it.

Usage: scripts/api.py BASE   (TITLE and BODY are the pull request's, when there is one)

Each package that ships a wheel is compared with its last release (its newest `<name>-v*` tag
in BASE) by griffe, as `griffe check` does: once as the working tree has it, and once as BASE
has it. A break the working tree has and BASE doesn't is the change's own, and it must be
marked as release-please reads it: `!` after the title's type or scope, or a `BREAKING CHANGE:`
footer in the body. A package with no release yet has no public API to keep, and is skipped.

griffe compares an attribute's value as text, so a union with a new member, or an edited
string, reads as a break. Those (`Attribute value was changed`) aren't counted.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import griffe

ROOT = Path(__file__).resolve().parent.parent
MARKED_TITLE = re.compile(r"^\w+(\([^)]*\))?!: ")
MARKED_BODY = re.compile(r"^BREAKING[ -]CHANGE: ", re.MULTILINE)
UNCOUNTED = {griffe.BreakageKind.ATTRIBUTE_CHANGED_VALUE}

type Key = tuple[griffe.BreakageKind, str, str, str]


def _last_release(name: str, base: str) -> str | None:
    """The package's newest release tag that BASE contains, if it has one."""
    tags = subprocess.run(
        ["git", "tag", "--merged", base, "--list", f"{name}-v*", "--sort=-version:refname"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return tags[0] if tags else None


def _breaks(
    old: griffe.Object | griffe.Alias, new: griffe.Object | griffe.Alias
) -> dict[Key, griffe.Breakage]:
    """The breaks griffe finds from old to new, keyed by what broke rather than by line."""
    return {
        (b.kind, b.obj.path, str(b.old_value), str(b.new_value)): b
        for b in griffe.find_breaking_changes(old, new)
        if b.kind not in UNCOUNTED
    }


def _added(name: str, base: str) -> list[griffe.Breakage]:
    """The breaks against the package's last release that the working tree adds to BASE's."""
    release = _last_release(name, base)
    if release is None:
        sys.stdout.write(f"api: {name} has no release yet, so it has no public API to keep\n")
        return []
    # load_git finds the package in a checkout of the ref, so its search path is relative.
    source = Path("packages", name, "src")
    released = griffe.load_git(name, ref=release, repo=ROOT, search_paths=[source])
    before = _breaks(released, griffe.load_git(name, ref=base, repo=ROOT, search_paths=[source]))
    after = _breaks(released, griffe.load(name, search_paths=[ROOT / source]))
    added = [breakage for key, breakage in after.items() if key not in before]
    sys.stdout.write(f"api: {name} against {release}: {len(added)} new break(s)\n")
    return added


def main() -> int:
    """Report the change's breaks, and fail if any is unmarked."""
    base = sys.argv[1]
    names = sorted(
        path.name for path in ROOT.glob("packages/*/src/*") if path.name == path.parents[1].name
    )
    added = [breakage for name in names for breakage in _added(name, base)]
    for breakage in added:
        sys.stdout.write(breakage.explain(style=griffe.ExplanationStyle.GITHUB) + "\n")
    if not added:
        return 0
    if MARKED_TITLE.match(os.environ.get("TITLE", "")) or MARKED_BODY.search(
        os.environ.get("BODY", "")
    ):
        sys.stdout.write("api: the change is marked as breaking\n")
        return 0
    sys.stdout.write(
        "api: mark the break with `!` in the title, as in `feat(core)!: ...`, "
        "or a `BREAKING CHANGE:` footer in the description\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
