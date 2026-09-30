"""Run a task in every project a change affects, and in every project that depends on one.

Usage: scripts/affected.py TASK   (MOON_BASE and MOON_HEAD name the change)

`moon ci --downstream deep` follows the task graph, so it reaches a dependent's task only
through that task's own dependencies: a change to evalr alone would run evalr's checks and no
one else's. So this asks moon which projects the change touches, both by their files and by
their tasks' inputs, which cover the root's files (uv.lock, pyproject.toml, .moon/), then adds
every project that depends on one, all the way down, from moon's project graph, and runs the
task in each that has it.
"""

import json
import subprocess
import sys
from typing import Any


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


def main() -> int:
    """Run the task in the affected projects and their dependents; nothing if there are none."""
    task = sys.argv[1]
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

    targets = [f"{name}:{task}" for name in sorted(affected) if task in projects[name]["tasks"]]
    if not targets:
        sys.stdout.write(f"affected: no affected project has a {task} task\n")
        return 0
    sys.stdout.write(f"affected: {' '.join(targets)}\n")
    sys.stdout.flush()
    return subprocess.run(["moon", "run", *targets], check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
