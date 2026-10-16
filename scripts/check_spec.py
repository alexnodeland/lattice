r"""Check that each formal spec's properties agree with its configurations, README and tests.

Usage: scripts/check_spec.py   (from the root)

A spec lives in docs/<package>/spec/ (ADR-0025). Its header comment names each property it checks,
the invariant of the package's record it stands for, and a test that holds the code to the same
invariant, one row each:

    \* I1_ConsumedAtMostOnce    | I1       | test_i1_messages_sent_at_once_...

and a line that says which invariants it leaves out: ``\* Not modelled: I7, ...``. This fails when

- a property in the table is not defined in the spec, or not named in the spec's README.md;
- a configuration (.cfg) checks a property that is not in the table, TypeOK aside;
- a test in the table is not a test of the package;
- an invariant that the package's tests are named for (``test_i3_...``) is in no row, and not
  left out.

So renaming a test, or adding an invariant, cannot leave the spec behind unnoticed.
"""

import re
import sys
from pathlib import Path

ROW = re.compile(r"^\\\* (\w+)\s+\|\s*(I\d+(?:,\s*I\d+)*)\s*\|\s*(test_\w+)\s*$", re.MULTILINE)
LEFT_OUT = re.compile(r"^\\\* Not modelled: (.*)$", re.MULTILINE)
NUMBERED_TEST = re.compile(r"^(?:async )?def test_i(\d+)_", re.MULTILINE)
CFG_SECTION = re.compile(r"^(INVARIANTS?|PROPERTY|PROPERTIES)\b(.*?)(?=^[A-Z]+\b|\Z)", re.M | re.S)
EXEMPT = frozenset({"TypeOK"})


def problems(root: Path) -> list[str]:
    """Every disagreement between the specs under ``root``/docs and the packages' tests."""
    specs = sorted(root.glob("docs/*/spec/*.tla"))
    found = [] if specs else [f"no spec in {root}/docs/*/spec/"]
    for spec in specs:
        package = spec.parent.parent.name
        text = spec.read_text()
        readme = spec.with_name("README.md")
        documented = readme.read_text() if readme.exists() else ""
        tests = "\n".join(
            p.read_text() for p in (root / "packages" / package).glob("tests/**/*.py")
        )
        name = spec.relative_to(root)
        rows = ROW.findall(text)
        if not rows:
            found.append(f"{name}: no property table in its header")
        numbers: set[str] = set()
        for prop, invariants, test in rows:
            numbers.update(re.findall(r"I\d+", invariants))
            if not re.search(rf"^{prop} ==", text, re.MULTILINE):
                found.append(f"{name}: {prop} is in the table but not defined")
            if not re.search(rf"\b{prop}\b", documented):
                found.append(f"{name}: {prop} is not in {readme.relative_to(root)}")
            if not re.search(rf"^(?:async )?def {test}\(", tests, re.MULTILINE):
                found.append(f"{name}: {prop}'s test {test} is not a test of {package}")
        left_out = LEFT_OUT.search(text)
        numbers.update(re.findall(r"I\d+", left_out[1]) if left_out else [])
        held = {f"I{n}" for n in NUMBERED_TEST.findall(tests)}
        found += [
            f"{name}: {package}'s tests hold {n}, which no row names"
            for n in sorted(held - numbers)
        ]
        table = {prop for prop, _, _ in rows}
        for config in sorted(spec.parent.glob("*.cfg")):
            settings = re.sub(r"\\\*.*$", "", config.read_text(), flags=re.MULTILINE)
            checked = [
                p
                for section in CFG_SECTION.finditer(settings)
                for p in re.findall(r"\w+", section[2])
            ]
            found += [
                f"{config.relative_to(root)}: {p} is not in the table"
                for p in checked
                if p not in table | EXEMPT
            ]
    return found


def main() -> int:
    """Print each disagreement, and fail if there is one."""
    found = problems(Path.cwd())
    for problem in found:
        sys.stderr.write(f"{problem}\n")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
