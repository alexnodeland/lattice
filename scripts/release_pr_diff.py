"""Whether a pull request's diff is only a release: what release-please changes, and nothing else.

Usage: scripts/release_pr_diff.py BASE   (the diff is BASE...HEAD)

release-please's pull request for a package changes its CHANGELOG.md, the version in its
pyproject.toml and in uv.lock, and its line in .release-please-manifest.json. CI runs this, and not
its other jobs, on those pull requests (ci.yml): their code is main's, which passed CI, and the
merge queue runs all of CI again on a release before it is merged. It exits 1, failing CI, if the
diff changes any other file, or any line of those but a version.
"""

import re
import subprocess
import sys
from collections.abc import Iterable

CHANGELOG = re.compile(r"packages/[a-z0-9-]+/CHANGELOG\.md")
VERSIONED = {
    re.compile(r"packages/[a-z0-9-]+/pyproject\.toml"): re.compile(r'version = "[^"]+"'),
    re.compile(r"uv\.lock"): re.compile(r'version = "[^"]+"'),
    re.compile(r"\.release-please-manifest\.json"): re.compile(
        r'\s*"packages/[a-z0-9-]+": "[^"]+",?'
    ),
}


EDITABLE = re.compile(r' source = \{ editable = "packages/[a-z0-9-]+" \}')
"""What follows a version uv.lock may change: a workspace package's, not a dependency's."""


def problems(diff: str) -> Iterable[str]:
    """What, in a `git diff --unified=1`, isn't release-please's."""
    path = ""
    changed = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            path = line.split(" b/", 1)[1]
            if not CHANGELOG.fullmatch(path) and not any(p.fullmatch(path) for p in VERSIONED):
                yield f"{path}: not a file a release changes"
        elif line.startswith(("+++", "---", "@@", "index ")) or CHANGELOG.fullmatch(path):
            continue
        elif line.startswith(("+", "-")):
            allowed = next((v for p, v in VERSIONED.items() if p.fullmatch(path)), None)
            if allowed is not None and not allowed.fullmatch(line[1:]):
                yield f"{path}: not a version: {line}"
            changed = True
        else:
            if changed and path == "uv.lock" and not EDITABLE.fullmatch(line):
                yield f"uv.lock: a version not of a workspace package's, before: {line}"
            changed = False


def main() -> int:
    """Check BASE...HEAD; print what isn't a release's."""
    diff = subprocess.run(
        ["git", "diff", "--unified=1", "--no-renames", f"{sys.argv[1]}...HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if not diff:
        sys.stdout.write("The diff is empty: not a release\n")
        return 1
    found = list(problems(diff))
    for each in found:
        sys.stdout.write(each + "\n")
    if not found:
        sys.stdout.write("Only a release's changes: versions and changelogs\n")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
