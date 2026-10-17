"""CI runs the scenarios of each UI one after another (lattice ADR-0002, portalr issue 172).

Issue 172, a scenario's first sign-in sometimes never rendering its Email field, was diagnosed as
``net::ERR_NETWORK_CHANGED``: Chromium on Linux fails every request it has in flight, even one to
127.0.0.1, when a network interface comes or goes, so the sign-in page's script chunks fail and
its route never renders. A compose stack coming up or down adds and removes a bridge and its
veths. PR 168 made CI run such a task in one project at a time, which is ``ONE_AT_A_TIME``, so
one UI's stack no longer comes down while the other's Chromium loads.

Issue 254, the browser unit tests failing to start, has the same mechanism, from other projects'
containers, and PR 256 addresses it for those tests. Neither change covers the interface changes
that the scenarios' own compose stack, or other Docker activity in the Acceptance job, can still
make, so issue 172 is not fixed, and stays open.

This test is a regression guard and not the fix: it holds every moon task that runs
``scripts/bdd`` to ``ONE_AT_A_TIME``. Its limit: it matches the literal ``scripts/bdd``
(``STACK_SCRIPTS``). A task that starts a stack another way, such as stackr's ``scripts/smoke``,
or something under ``examples/``, is not caught, and must be added to ``STACK_SCRIPTS`` as it is
added.

TODO(#172): keep the scenarios' Chromium from seeing the interface changes of their own stack and
of the job's other containers; a guard on how CI batches tasks can't.
"""

import runpy
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
AFFECTED = runpy.run_path(str(ROOT / "scripts" / "affected.py"))
STACK_SCRIPTS = ("scripts/bdd",)
"""What a task runs that brings a compose stack up, and down again."""


def test_a_task_runs_all_at_once_unless_it_starts_a_stack() -> None:
    batches = AFFECTED["batches"]
    targets = ["app:bdd", "admin:bdd"]
    assert batches("bdd", targets) == [["app:bdd"], ["admin:bdd"]]
    assert batches("test", targets) == [targets]


def test_every_task_that_starts_a_stack_runs_one_project_at_a_time() -> None:
    one_at_a_time = AFFECTED["ONE_AT_A_TIME"]
    starting: dict[str, list[str]] = {}
    for moon in ROOT.glob("packages/*/**/moon.yml"):
        for name, task in (yaml.safe_load(moon.read_text()).get("tasks") or {}).items():
            command = f"{task.get('command', '')} {task.get('script', '')}"
            if any(script in command for script in STACK_SCRIPTS):
                starting.setdefault(name, []).append(str(moon.parent.relative_to(ROOT)))
    assert starting, "no task starts a stack: update STACK_SCRIPTS"
    assert [name for name in starting if name not in one_at_a_time] == []
