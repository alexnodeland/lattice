"""Whether a pull request's diff is only a release: what release-please changes, and nothing else.

Usage: python3 -I release_pr_diff.py BASE REPOSITORY   (the diff is BASE...HEAD, in REPOSITORY)

release-please's pull request changes, for each package it releases, its CHANGELOG.md, the version
in its pyproject.toml and in uv.lock, and its line in .release-please-manifest.json. CI runs the
base's copy of this on those pull requests (ci.yml), and skips its other jobs only if it exits 0:
their code is main's, which passed CI, and a release queued with Mergify runs all of CI on its batch
(the ruleset doesn't require the queue, so one merged directly ships on this check alone). Anything
else exits 1, and all of CI runs, so a refusal costs time, not a check.

It refuses another file, a file added, deleted or renamed, a mode or a binary, and in those files
anything but: each package's version, the same in all three, a release, and higher than before; and
changelog lines of release-please's own shapes. Each file is compared whole, at the merge base and
at HEAD, not by parsing the patch.
"""

import json
import re
import subprocess
import sys
import tomllib
import unicodedata
from pathlib import Path
from typing import Any

PACKAGE = r"packages/([a-z0-9-]+)"
CHANGELOG = re.compile(PACKAGE + r"/CHANGELOG\.md")
PYPROJECT = re.compile(PACKAGE + r"/pyproject\.toml")
LOCK = "uv.lock"
MANIFEST = ".release-please-manifest.json"
RELEASE = re.compile(r"([0-9]+)\.([0-9]+)\.([0-9]+)")
VERSION_LINE = re.compile(r'version = "[0-9]+\.[0-9]+\.[0-9]+"')
REPOSITORY = "https://github.com/alexnodeland/lattice/"

DATE = r"\([0-9]{4}-[0-9]{2}-[0-9]{2}\)"
HEADINGS = (
    re.compile(
        r"## \[[0-9]+\.[0-9]+\.[0-9]+\]\("
        + re.escape(REPOSITORY)
        + r"compare/[a-z0-9.-]+\) "
        + DATE
    ),
    re.compile(r"## [0-9]+\.[0-9]+\.[0-9]+ " + DATE),
    re.compile(r"### (⚠ )?[A-Z][A-Za-z ]+"),
)
BULLET = re.compile(r"\* .+")
LINK = re.compile(r"\]\(([^)]*)\)")
OURS = re.compile(re.escape(REPOSITORY) + r"[^\s()]*")
ELSEWHERE = re.compile(r"://|www\.|\]:|\[\^|\*\[|\b[A-Za-z][A-Za-z0-9+.-]*:(?![\s*]|$)")
"""What, once the repository's own URLs are taken out, would link elsewhere: any URL, a reference
definition, a footnote, an abbreviation, or a scheme (`**scope:**` and `text: more` aren't)."""
INVISIBLE = {"Cc", "Cf", "Zl", "Zp"}
"""Control and format characters, bidi and zero-width among them, and line and paragraph
separators."""
NEVER = ("<", ">", "{", "}", "8<", "!!!", "\\")
"""What no changelog line may hold: HTML, attributes, includes, admonitions, escapes. The docs
include each changelog (pymdownx.snippets), so these would reach the site's build. A release whose
notes hold one runs all of CI."""

Bumps = dict[str, tuple[object, object]]
"""Each package's version before and after, by its directory, as one file says."""


def git(repository: Path, *args: str) -> str:
    """Git's output, as text."""
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True, cwd=repository
    ).stdout


def release(version: object) -> tuple[int, ...] | None:
    """A release's version as numbers, or None if it isn't one."""
    match = RELEASE.fullmatch(version) if isinstance(version, str) else None
    return tuple(map(int, match.groups())) if match else None


def changed_lines(before: str, after: str) -> list[tuple[str, str]] | None:
    """Each line replaced, and its replacement, or None if any were added or removed."""
    old, new = before.splitlines(), after.splitlines()
    if len(old) != len(new):
        return None
    return [(a, b) for a, b in zip(old, new, strict=True) if a != b]


def only_versions(before: str, after: str) -> bool:
    """Whether every line changed is a version line, on both sides, and none added or removed."""
    lines = changed_lines(before, after)
    return lines is not None and all(
        VERSION_LINE.fullmatch(a) and VERSION_LINE.fullmatch(b) for a, b in lines
    )


def without_version(table: dict[str, Any]) -> dict[str, Any]:
    """A table without its version."""
    return {k: v for k, v in table.items() if k != "version"}


def pyproject(package: str, before: str, after: str) -> tuple[list[str], Bumps]:
    """One line changed, [project]'s version."""
    lines = changed_lines(before, after)
    if lines is None or len(lines) != 1 or not only_versions(before, after):
        return ["a change but one version line"], {}
    old, new = tomllib.loads(before), tomllib.loads(after)
    old_project, new_project = old.pop("project", {}), new.pop("project", {})
    if old != new or without_version(old_project) != without_version(new_project):
        return ["a change but [project]'s version"], {}
    return [], {package: (old_project.get("version"), new_project.get("version"))}


def lock(before: str, after: str) -> tuple[list[str], Bumps]:
    """Only version lines changed, each a workspace package's: editable, or virtual (stackr)."""
    if not only_versions(before, after):
        return ["a change but version lines"], {}
    old, new = tomllib.loads(before), tomllib.loads(after)
    olds, news = old.pop("package", []), new.pop("package", [])
    if old != new or len(olds) != len(news):
        return ["a change but packages' versions"], {}
    found: list[str] = []
    bumps: Bumps = {}
    for a, b in zip(olds, news, strict=True):
        if a == b:
            continue
        source = a.get("source", {})
        editable = re.fullmatch(PACKAGE, str(source.get("editable", source.get("virtual", ""))))
        if without_version(a) != without_version(b) or editable is None:
            found.append(f"a version not of a workspace package's: {a.get('name')}")
        else:
            bumps[editable.group(1)] = (a.get("version"), b.get("version"))
    return found, bumps


def manifest(before: str, after: str) -> tuple[list[str], Bumps]:
    """The same packages, on the same lines."""
    old, new = json.loads(before), json.loads(after)
    if changed_lines(before, after) is None or old.keys() != new.keys():
        return ["a package added or removed"], {}
    bumps: Bumps = {}
    for key in old:
        package = re.fullmatch(PACKAGE, key)
        if package is None:
            return [f"not a package: {key}"], {}
        if old[key] != new[key]:
            bumps[package.group(1)] = (old[key], new[key])
    return [], bumps


def changelog(before: str, after: str) -> list[str]:
    """Lines added at one place, each of release-please's shapes."""
    old, new = before.splitlines(), after.splitlines()
    start = next((i for i, (a, b) in enumerate(zip(old, new, strict=False)) if a != b), len(old))
    added = len(new) - len(old)
    if added <= 0 or new[:start] + new[start + added :] != old:
        return ["not lines added at one place"]
    found: list[str] = []
    for line in new[start : start + added]:
        if any(each in line for each in NEVER) or (
            line and not BULLET.fullmatch(line) and not any(h.fullmatch(line) for h in HEADINGS)
        ):
            found.append(f"not release-please's: {line}")
        elif any(unicodedata.category(c) in INVISIBLE for c in line):
            found.append(f"a control or format character: {line!r}")
        elif any(not url.startswith(REPOSITORY) for url in LINK.findall(line)) or (
            ELSEWHERE.search(OURS.sub("", line))
        ):
            found.append(f"a link outside the repository: {line}")
    return found


def agreement(bumps: dict[str, Bumps]) -> list[str]:
    """Each package's version the same in all three files, a release, and higher than before.

    One release pull request may release several packages, each at its own version.
    """
    packages = sorted({p for each in bumps.values() for p in each})
    if not packages:
        return ["no package's version changed"]
    found: list[str] = []
    for package in packages:
        files = (MANIFEST, LOCK, "pyproject.toml")
        missing = [f for f in files if package not in bumps.get(f, {})]
        found += [f"no version of {package} changed in {f}" for f in missing]
        pairs = {each[package] for each in bumps.values() if package in each}
        if len(pairs) != 1:
            found.append(f"{package}'s versions don't agree: {sorted(map(str, pairs))}")
            continue
        old, new = next(iter(pairs))
        old_release, new_release = release(old), release(new)
        if old_release is None or new_release is None or new_release <= old_release:
            found.append(f"{package}: not a release higher than before: {old} to {new}")
    return found


def check(base: str, repository: Path) -> list[str]:
    """What, in base...HEAD, isn't release-please's."""
    since = f"{base}...HEAD"
    merge_base = git(repository, "merge-base", base, "HEAD").strip()
    raw = git(repository, "diff", "--raw", "-z", "--no-renames", "--no-abbrev", since).split("\0")
    numstat = git(repository, "diff", "--numstat", "-z", "--no-renames", since).split("\0")
    binary = {n.split("\t", 2)[2] for n in numstat if n.startswith("-\t-\t")}
    entries = list(zip(raw[0::2], raw[1::2], strict=False))
    if not entries:
        return ["the diff is empty: not a release"]
    found: list[str] = []
    bumps: dict[str, Bumps] = {}
    for meta, path in entries:
        old_mode, new_mode, _, _, status = meta.lstrip(":").split(" ")
        pyproject_of, changelog_of = PYPROJECT.fullmatch(path), CHANGELOG.fullmatch(path)
        if path not in (LOCK, MANIFEST) and not pyproject_of and not changelog_of:
            found.append(f"{path}: not a file a release changes")
            continue
        if status != "M" or old_mode != "100644" or new_mode != "100644" or path in binary:
            found.append(f"{path}: {status}, {old_mode} to {new_mode}: not a text file's change")
            continue
        before = git(repository, "show", f"{merge_base}:{path}")
        after = git(repository, "show", f"HEAD:{path}")
        if "\0" in before + after:
            found.append(f"{path}: binary")
            continue
        bumped: Bumps = {}
        try:
            if changelog_of:
                problems = changelog(before, after)
            elif pyproject_of:
                problems, bumped = pyproject(pyproject_of.group(1), before, after)
            else:
                problems, bumped = (lock if path == LOCK else manifest)(before, after)
        except (ValueError, AttributeError, TypeError) as error:
            problems = [f"unreadable: {error}"]
        found += [f"{path}: {each}" for each in problems]
        if bumped:
            bumps.setdefault("pyproject.toml" if pyproject_of else path, {}).update(bumped)
    return found or agreement(bumps)


def main() -> int:
    """Check BASE...HEAD in REPOSITORY; print what isn't a release's."""
    found = check(sys.argv[1], Path(sys.argv[2]))
    for each in found:
        sys.stdout.write(each + "\n")
    if not found:
        sys.stdout.write("Only a release's changes: a version and a changelog\n")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
