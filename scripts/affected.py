"""Run a task in every project a change affects, and in every project that depends on one.

Usage: scripts/affected.py TASK [--language LANGUAGE]   (MOON_BASE and MOON_HEAD name the change)

With --language, only the projects of that language run the task, as their moon.yml declares it:
the jobs that repeat one language's tests, such as `python`, leave the others to those that don't.

`moon ci --downstream deep` follows the task graph, so it reaches a dependent's task only
through that task's own dependencies: a change to evalr alone would run evalr's checks and no
one else's. So this asks moon which projects the change touches, both by their files and by
their tasks' inputs, which cover the root's files (uv.lock, pyproject.toml, .moon/), then adds
every project that depends on one, all the way down, from moon's project graph, and runs the
task in each that has it.

A task in ONE_AT_A_TIME runs in one project after another, rather than all at once. Otherwise
the projects tagged BROWSER run theirs first, in a `moon run` of their own, and then the rest.
"""

import argparse
import json
import subprocess
import sys
from collections.abc import Collection
from typing import Any

# Tasks whose projects run one after another, each its own `moon run`. app's and admin's
# scenarios each start and stop a compose stack: in CI, one stack's network coming down while
# the other's Chromium navigates fails it with ERR_NETWORK_CHANGED (ADR-0002).
ONE_AT_A_TIME = frozenset({"bdd"})

# The projects whose tests run in Chromium. Chromium fails every request it has in flight when a
# network interface comes or goes, as a container's does when another project's tests start or
# stop one, and a test file's import failed with ERR_NETWORK_CHANGED (#254). So they run apart.
BROWSER = "browser"


def query(*arguments: str) -> dict[str, Any]:
    """What `moon query` answers, as JSON."""
    done = subprocess.run(
        ["moon", "query", *arguments],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(done.stdout)


def batches(task: str, targets: list[str], browser: Collection[str] = ()) -> list[list[str]]:
    """How a task's targets run, each batch its own `moon run`, one after another.

    Each alone if the task is in ONE_AT_A_TIME; otherwise those of the projects in `browser`
    first, and then the rest.
    """
    if task in ONE_AT_A_TIME:
        return [[target] for target in targets]
    first = [target for target in targets if target.split(":")[0] in browser]
    rest = [target for target in targets if target not in first]
    return [batch for batch in (first, rest) if batch]


def targets_of(
    task: str, affected: Collection[str], projects: dict[str, Any], language: str | None = None
) -> list[str]:
    """The tasks to run, in the affected projects that have one, of `language` if it is given."""
    return [
        f"{name}:{task}"
        for name in sorted(affected)
        if task in projects[name]["tasks"] and language in (None, projects[name]["language"])
    ]


def main() -> int:
    """Run the task in the affected projects and their dependents; nothing if there are none."""
    arguments = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    arguments.add_argument("task")
    arguments.add_argument("--language")
    given = arguments.parse_args()
    task: str = given.task
    projects = {project["id"]: project for project in query("projects")["projects"]}
    dependents: dict[str, set[str]] = {name: set() for name in projects}
    for name, project in projects.items():
        for dependency in project.get("dependencies", []):
            dependents[dependency["id"]].add(name)

    changed = {project["id"] for project in query("projects", "--affected")["projects"]}
    changed |= set(query("tasks", "--affected")["tasks"])
    affected, pending = set(changed), list(changed)
    while pending:
        for dependent in dependents[pending.pop()] - affected:
            affected.add(dependent)
            pending.append(dependent)

    targets = targets_of(task, affected, projects, given.language)
    if not targets:
        sys.stdout.write(f"affected: no affected project has a {task} task\n")
        return 0
    sys.stdout.write(f"affected: {' '.join(targets)}\n")
    sys.stdout.flush()
    browser = {name for name in affected if BROWSER in (projects[name]["config"].get("tags") or [])}
    codes = [
        subprocess.run(["moon", "run", *batch], check=False).returncode
        for batch in batches(task, targets, browser)
    ]
    return max(codes)


if __name__ == "__main__":
    sys.exit(main())
