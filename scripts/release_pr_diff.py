"""Whether a pull request's diff is only a release: what release-please changes, and nothing else.

Usage: git show BASE:scripts/release_pr_diff.py | python3 - BASE   (the diff is BASE...HEAD)

release-please's pull request for a package changes its CHANGELOG.md, the version in its
pyproject.toml and in uv.lock, and its line in .release-please-manifest.json. CI runs this, and not
its other jobs, on those pull requests (ci.yml), from the base, so the pull request can't change
it: their code is main's, which passed CI, and the merge queue runs all of CI again on a release
before it is merged. It exits 1, failing CI, on anything else: another file, a file added, deleted
or renamed, a mode or a binary, or a change to those files but a version or a changelog's entry.

Each file is compared whole, at the merge base and at HEAD, not by parsing the patch.
"""

import difflib
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

CHANGELOG = re.compile(r"packages/[a-z0-9-]+/CHANGELOG\.md")
PYPROJECT = re.compile(r"packages/[a-z0-9-]+/pyproject\.toml")
LOCK = "uv.lock"
MANIFEST = ".release-please-manifest.json"
VERSION = re.compile(r'version = "[^"]+"')
DOCS_SYNTAX = ("--8<--", "<script", "{%", "{{")
"""What a changelog's new lines may not hold: the docs include each changelog (pymdownx.snippets),
so these would reach the site's build."""


def git(cwd: Path | None, *args: str) -> str:
    """Git's output, as text."""
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True, cwd=cwd
    ).stdout


def changed_lines(before: str, after: str) -> tuple[list[str], list[str]] | None:
    """The lines replaced and their replacements, or None if any were added or removed."""
    old, new = before.splitlines(), after.splitlines()
    if len(old) != len(new):
        return None
    pairs = [(a, b) for a, b in zip(old, new, strict=True) if a != b]
    return [a for a, _ in pairs], [b for _, b in pairs]


def only_versions(before: str, after: str) -> bool:
    """Whether every line changed, on either side, is a version line, and none added or removed."""
    lines = changed_lines(before, after)
    return lines is not None and all(VERSION.fullmatch(each) for each in lines[0] + lines[1])


def without_version(data: dict[str, Any]) -> dict[str, Any]:
    """A table without its version."""
    return {k: v for k, v in data.items() if k != "version"}


def pyproject(before: str, after: str) -> Iterator[str]:
    """One line changed, [project]'s version, and nothing else."""
    lines = changed_lines(before, after)
    if lines is None or len(lines[0]) != 1 or not only_versions(before, after):
        yield "a change but one version line"
        return
    old, new = tomllib.loads(before), tomllib.loads(after)
    old_project, new_project = old.pop("project", {}), new.pop("project", {})
    if old_project.get("version") == new_project.get("version"):
        yield "the version changed isn't [project]'s"
    elif old != new or without_version(old_project) != without_version(new_project):
        yield "a change but [project]'s version"


def lock(before: str, after: str) -> Iterator[str]:
    """Only version lines changed, each a workspace package's."""
    if not only_versions(before, after):
        yield "a change but version lines"
        return
    old, new = tomllib.loads(before), tomllib.loads(after)
    olds, news = old.pop("package", []), new.pop("package", [])
    if old != new or len(olds) != len(news):
        yield "a change but packages' versions"
        return
    for a, b in zip(olds, news, strict=True):
        if a != b and (
            without_version(a) != without_version(b) or "editable" not in a.get("source", {})
        ):
            yield f"a version not of a workspace package's: {a.get('name')}"


def manifest(before: str, after: str) -> Iterator[str]:
    """The same packages, their versions changed, on the same lines."""
    old, new = json.loads(before), json.loads(after)
    if changed_lines(before, after) is None or old.keys() != new.keys():
        yield "a package added or removed"
    elif not all(isinstance(v, str) for v in new.values()):
        yield "a version that isn't a string"


def changelog(before: str, after: str) -> Iterator[str]:
    """New lines only, none of them the docs' syntax."""
    for line in difflib.ndiff(before.splitlines(), after.splitlines()):
        if line.startswith("- "):
            yield "a line removed"
        elif line.startswith("+ ") and any(s in line for s in DOCS_SYNTAX):
            yield f"the docs' syntax: {line[2:]}"


def rule(path: str) -> Callable[[str, str], Iterator[str]] | None:
    """How a release may change this file, or None if it may not."""
    if path == LOCK:
        return lock
    if path == MANIFEST:
        return manifest
    if CHANGELOG.fullmatch(path):
        return changelog
    if PYPROJECT.fullmatch(path):
        return pyproject
    return None


def check(base: str, cwd: Path | None = None) -> list[str]:
    """What, in base...HEAD, isn't release-please's."""
    found: list[str] = []
    since = f"{base}...HEAD"
    merge_base = git(cwd, "merge-base", base, "HEAD").strip()
    raw = git(cwd, "diff", "--raw", "-z", "--no-renames", "--no-abbrev", since).split("\0")
    numstat = git(cwd, "diff", "--numstat", "-z", "--no-renames", since).split("\0")
    binary = {n.split("\t", 2)[2] for n in numstat if n.startswith("-\t-\t")}
    entries = list(zip(raw[0::2], raw[1::2], strict=False))
    if not entries:
        return ["the diff is empty: not a release"]
    for meta, path in entries:
        old_mode, new_mode, _, _, status = meta.lstrip(":").split(" ")
        compare = rule(path)
        if compare is None:
            found.append(f"{path}: not a file a release changes")
            continue
        if status != "M" or old_mode != "100644" or new_mode != "100644" or path in binary:
            found.append(f"{path}: {status}, {old_mode} to {new_mode}: not a text file's change")
            continue
        before = git(cwd, "show", f"{merge_base}:{path}")
        after = git(cwd, "show", f"HEAD:{path}")
        if "\0" in before + after:
            found.append(f"{path}: binary")
            continue
        try:
            found += [f"{path}: {each}" for each in compare(before, after)]
        except (ValueError, AttributeError, TypeError) as error:
            found.append(f"{path}: unreadable: {error}")
    return found


def main() -> int:
    """Check BASE...HEAD; print what isn't a release's."""
    found = check(sys.argv[1])
    for each in found:
        sys.stdout.write(each + "\n")
    if not found:
        sys.stdout.write("Only a release's changes: versions and changelogs\n")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
