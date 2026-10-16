"""CI runs the scenarios of each UI one after another (lattice ADR-0002, portalr issue 172).

Each UI's scenarios bring a compose stack up and down, and Chromium on Linux drops its requests
with ``net::ERR_NETWORK_CHANGED`` when the host's network interfaces change, which a stack coming
down in the next project does. So a task that starts a stack runs in one project at a time, and
this holds every such task to ``ONE_AT_A_TIME``, so that a new one can't be added without it.
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
