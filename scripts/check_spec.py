r"""Check that each formal spec agrees with its configurations, README, tasks, code and tests.

Usage: scripts/check_spec.py   (from the root)

A spec lives in docs/<package>/spec/ (ADR-0025). Its header comment names each property it checks,
the invariant of the package's record it stands for, and a test that holds the code to the same
invariant, one row each:

    \* I1_ConsumedAtMostOnce    | I1       | test_i1_messages_sent_at_once_...

and a line that says which invariants it leaves out: ``\* Not modelled: I7, ...``. Its README has
a table, ``| Action | Code |``, of each action and the functions it models. This fails when

- there is no spec, or a spec has no table;
- a property in the table is not defined in the spec, not named in its README, or checked by no
  configuration (.cfg);
- a configuration checks a property that is not in the table, TypeOK aside;
- a test in the table is not a test of the package, or is named for another invariant
  (``test_i3_...`` in a row of I1);
- an invariant that the package's tests are named for is in no row, and not left out;
- a configuration is not named in the package's moon.yml, so no task runs it;
- the README has no action table, an action in it is not defined in the spec, or a function it
  names (backticked, as ``Runner._take`` or ``save_cursor(asked)``) is not defined in the package.

So renaming a test, a function or a property, or adding an invariant or a configuration, cannot
leave the spec behind unnoticed.
"""

import re
import sys
from pathlib import Path

ROW = re.compile(r"^\\\* (\w+)\s+\|\s*(I\d+(?:,\s*I\d+)*)\s*\|\s*(test_\w+)\s*$", re.MULTILINE)
LEFT_OUT = re.compile(r"^\\\* Not modelled: (.*)$", re.MULTILINE)
NUMBERED = re.compile(r"^test_i(\d+)_\w+$")
TEST = re.compile(r"^(?:async )?def (test_\w+)\(", re.MULTILINE)
CFG_COMMENT = re.compile(r"\\\*.*?$|\(\*.*?\*\)", re.MULTILINE | re.DOTALL)
CFG_SECTION = re.compile(r"^(INVARIANTS?|PROPERTY|PROPERTIES)\b(.*?)(?=^[A-Z]+\b|\Z)", re.M | re.S)
ACTIONS = re.compile(r"^\| Action \| Code \|\n\|[-|]+\|\n((?:\|.*\n?)*)", re.MULTILINE)
EXEMPT = frozenset({"TypeOK"})


def _checked(config: Path) -> list[str]:
    """The properties a configuration checks."""
    settings = CFG_COMMENT.sub("", config.read_text())
    return [p for section in CFG_SECTION.finditer(settings) for p in re.findall(r"\w+", section[2])]


def _named(cell: str) -> list[str]:
    """What a cell of the action table names: the last part of each backticked name."""
    return [name.split(".")[-1] for name in re.findall(r"`([A-Za-z_][\w.]*)", cell)]


def _actions(readme: str, spec: str, source: str, name: str) -> list[str]:
    """What the README's action table names that the spec or the package doesn't define."""
    table = ACTIONS.search(readme)
    if table is None:
        return [f"{name}: no `| Action | Code |` table"]
    found: list[str] = []
    for row in table[1].splitlines():
        actions, _, code = row.strip().strip("|").partition("|")
        found += [
            f"{name}: the action {action} is not in the spec"
            for action in _named(actions)
            if not re.search(rf"^{action}(\(.*\))? ==", spec, re.MULTILINE)
        ]
        found += [
            f"{name}: {function} is not defined in the package"
            for function in _named(code)
            if not re.search(rf"^\s*(?:async )?(?:def|class) {function}\b", source, re.MULTILINE)
        ]
    return found


def _spec(spec: Path, root: Path) -> list[str]:
    """Every disagreement between one spec and its package."""
    package = root / "packages" / spec.parent.parent.name
    text = spec.read_text()
    name = spec.relative_to(root)
    readme = spec.with_name("README.md")
    documented = readme.read_text() if readme.exists() else ""
    tests = set(TEST.findall("\n".join(p.read_text() for p in package.glob("tests/**/*.py"))))
    source = "\n".join(p.read_text() for p in package.glob("src/**/*.py"))
    moon = package / "moon.yml"
    tasks = moon.read_text() if moon.exists() else ""
    checked = {config: _checked(config) for config in sorted(spec.parent.glob("*.cfg"))}
    everywhere = {p for properties in checked.values() for p in properties}
    rows = ROW.findall(text)
    found = [] if rows else [f"{name}: no property table in its header"]
    numbers: set[str] = set()
    for prop, invariants, test in rows:
        named = set(re.findall(r"I\d+", invariants))
        numbers |= named
        if not re.search(rf"^{prop} ==", text, re.MULTILINE):
            found.append(f"{name}: {prop} is in the table but not defined")
        if not re.search(rf"\b{prop}\b", documented):
            found.append(f"{name}: {prop} is not in {readme.relative_to(root)}")
        if prop not in everywhere:
            found.append(f"{name}: {prop} is checked by no configuration")
        if test not in tests:
            found.append(f"{name}: {prop}'s test {test} is not a test of {package.name}")
        elif (number := NUMBERED.match(test)) and f"I{number[1]}" not in named:
            found.append(f"{name}: {prop}'s test {test} is for I{number[1]}, not {invariants}")
    left_out = LEFT_OUT.search(text)
    numbers.update(re.findall(r"I\d+", left_out[1]) if left_out else [])
    held = {f"I{number[1]}" for test in tests if (number := NUMBERED.match(test))}
    found += [
        f"{name}: {package.name}'s tests hold {n}, which no row names"
        for n in sorted(held - numbers)
    ]
    table = {prop for prop, _, _ in rows} | EXEMPT
    for config, properties in checked.items():
        where = config.relative_to(root)
        found += [f"{where}: {p} is not in the table" for p in properties if p not in table]
        if config.name not in tasks:
            found.append(f"{where} is not in {moon.relative_to(root)}: no task runs it")
    return found + _actions(documented, text, source, str(readme.relative_to(root)))


def problems(root: Path) -> list[str]:
    """Every disagreement between the specs under ``root``/docs and their packages."""
    specs = sorted(root.glob("docs/*/spec/*.tla"))
    if not specs:
        return [f"no spec in {root}/docs/*/spec/"]
    return [problem for spec in specs for problem in _spec(spec, root)]


def main() -> int:
    """Print each disagreement, and fail if there is one."""
    found = problems(Path.cwd())
    for problem in found:
        sys.stderr.write(f"{problem}\n")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
