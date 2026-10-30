"""Run a task in every project a change affects, and in every project that depends on one.

Usage: scripts/affected.py TASK [--language LANGUAGE | --except-language LANGUAGE] [--all]
       scripts/affected.py --projects        (MOON_BASE and MOON_HEAD name the change)

With --language, only the projects of that language run the task, as their moon.yml declares it:
the jobs that repeat one language's tests, such as `python`, leave the others to those that don't.
With --except-language, every project but those of that language does: CI's Check job runs the
web packages' checks (`typescript`) in a job of its own, and the rest in another.
With --projects, it runs nothing, and prints the affected projects, dependents included, as a JSON
list: CI starts its heavy jobs only when a project other than the root, `lattice`, is in it.
With --all, every project runs the task, whatever changed, batched as a change's are: Nightly's.

`moon ci --downstream deep` follows the task graph, so it reaches a dependent's task only
through that task's own dependencies: a change to evalr alone would run evalr's checks and no
one else's. So this asks moon which projects the change touches, both by their files and by
their tasks' inputs, which cover the root's files (uv.lock, pyproject.toml, .moon/), then adds
every project that depends on one, all the way down, from moon's project graph, and runs the
task in each that has it. Files that no task reads (INERT, the instructions for coding agents)
are left out of the change first, so a change to them alone affects no project.

A task in ONE_AT_A_TIME runs in one project after another, rather than all at once. Otherwise
the projects tagged BROWSER run theirs first, each in a `moon run` of its own, one after
another, and then the rest together.
"""

import argparse
import json
import re
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
# stop one, and a test file's import failed with ERR_NETWORK_CHANGED (#254). So they run apart:
# and one at a time, as three Chromium suites on one runner made every browser test two to four
# times slower, and a phone test past its 15 s (#875).
BROWSER = "browser"

# Files no task reads: the AGENTS.md beside the code, for coding agents. moon counts a project
# affected by any file in it, so a change to these alone would run every check of each package.
INERT = re.compile(r"(^|/)AGENTS\.md$")


def query(*arguments: str, given: str | None = None) -> dict[str, Any]:
    """What `moon query` answers, as JSON, given `given` on its standard input if there is one."""
    done = subprocess.run(
        ["moon", "query", *arguments],
        input=given,
        stdin=None if given is not None else subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(done.stdout)


def batches(task: str, targets: list[str], browser: Collection[str] = ()) -> list[list[str]]:
    """How a task's targets run, each batch its own `moon run`, one after another.

    Each alone if the task is in ONE_AT_A_TIME; otherwise those of the projects in `browser`
    first, each alone, and then the rest together.
    """
    if task in ONE_AT_A_TIME:
        return [[target] for target in targets]
    first = [target for target in targets if target.split(":")[0] in browser]
    rest = [target for target in targets if target not in first]
    return [[target] for target in first] + ([rest] if rest else [])


def targets_of(
    task: str,
    affected: Collection[str],
    projects: dict[str, Any],
    language: str | None = None,
    except_language: str | None = None,
) -> list[str]:
    """The tasks to run, in the affected projects that have one.

    Only those of `language` if it is given, and none of `except_language` if that is.
    """
    return [
        f"{name}:{task}"
        for name in sorted(affected)
        if task in projects[name]["tasks"]
        and (language is None or projects[name].get("language") == language)
        and (except_language is None or projects[name].get("language") != except_language)
    ]


def without_inert(changed: dict[str, Any]) -> dict[str, Any]:
    """`moon query changed-files`'s answer, without the files no task reads (INERT)."""
    return {**changed, "files": [file for file in changed["files"] if not INERT.search(file)]}


def affected_projects(projects: dict[str, Any]) -> set[str]:
    """The projects the change touches, by their files or their tasks' inputs, and dependents."""
    dependents: dict[str, set[str]] = {name: set() for name in projects}
    for name, project in projects.items():
        for dependency in project.get("dependencies", []):
            dependents[dependency["id"]].add(name)

    files = json.dumps(without_inert(query("changed-files")))
    touched = query("projects", "--affected", given=files)["projects"]
    changed = {project["id"] for project in touched}
    changed |= set(query("tasks", "--affected", given=files)["tasks"])
    affected, pending = set(changed), list(changed)
    while pending:
        for dependent in dependents[pending.pop()] - affected:
            affected.add(dependent)
            pending.append(dependent)
    return affected


def main() -> int:
    """Run the task in the affected projects and their dependents; nothing if there are none."""
    arguments = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    arguments.add_argument("task", nargs="?")
    languages = arguments.add_mutually_exclusive_group()
    languages.add_argument("--language")
    languages.add_argument("--except-language")
    arguments.add_argument("--projects", action="store_true")
    arguments.add_argument("--all", action="store_true")
    given = arguments.parse_args()
    if given.projects == (given.task is not None):
        arguments.error("give a task, or --projects")
    projects = {project["id"]: project for project in query("projects")["projects"]}
    affected = set(projects) if given.all else affected_projects(projects)
    if given.projects:
        sys.stdout.write(json.dumps(sorted(affected)) + "\n")
        return 0
    task: str = given.task
    targets = targets_of(task, affected, projects, given.language, given.except_language)
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
