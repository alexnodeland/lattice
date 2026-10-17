"""Each formal spec agrees with its package (scripts/check_spec.py): one test per disagreement."""

from pathlib import Path

import check_spec
import pytest

ROOT = Path(__file__).parent.parent

SPEC = """---- MODULE Claim ----
\\* Property      | ADR      | Test
\\* I1_Once       | I1       | test_i1_once
\\* I2_Written    | I1, I2   | test_i2_written
\\*
\\* Not modelled: I3, the upgrade.
Take(p) == TRUE
Tick == TRUE
I1_Once == TRUE
I2_Written == TRUE
====
"""
CONFIG = """\\* A comment that names Unlisted is no property.
SPECIFICATION Spec
CONSTANTS
    N = 2
INVARIANTS
    TypeOK
    I1_Once
    (* Nor is Unlisted, in a comment of this kind. *)
PROPERTIES
    I2_Written
"""
README = """`I1_Once` and `I2_Written`.

| Action | Code |
|---|---|
| `Take` | `Runner._take`, its `save_cursor(asked)` |
| `Tick` | storage's clock |
"""
TESTS = """
def test_i1_once() -> None: ...


async def test_i2_written() -> None: ...


def test_i3_upgraded() -> None: ...


def test_i30x_not_numbered_so() -> None: ...
"""
SOURCE = """
class Runner:
    async def _take(self) -> None: ...


async def save_cursor() -> None: ...
"""
MOON = "spec: 'scripts/tlc Claim.tla Claim.cfg'\n"


def write(root: Path, **files: str) -> None:
    """A package `pkg` with a spec; ``files`` replaces any of its files, by name."""
    contents = {
        "spec": SPEC,
        "config": CONFIG,
        "readme": README,
        "tests": TESTS,
        "source": SOURCE,
        "moon": MOON,
    } | files
    spec = root / "docs" / "pkg" / "spec"
    package = root / "packages" / "pkg"
    for folder in (spec, package / "tests", package / "src" / "pkg"):
        folder.mkdir(parents=True)
    (spec / "Claim.tla").write_text(contents["spec"])
    (spec / "Claim.cfg").write_text(contents["config"])
    (spec / "README.md").write_text(contents["readme"])
    (package / "tests" / "test_claim.py").write_text(contents["tests"])
    (package / "src" / "pkg" / "runner.py").write_text(contents["source"])
    (package / "moon.yml").write_text(contents["moon"])


def test_the_repositorys_specs_agree() -> None:
    assert check_spec.problems(ROOT) == []


def test_a_spec_that_agrees_passes(tmp_path: Path) -> None:
    write(tmp_path)
    assert check_spec.problems(tmp_path) == []


def test_a_root_with_no_spec_fails(tmp_path: Path) -> None:
    assert check_spec.problems(tmp_path) == [f"no spec in {tmp_path}/docs/*/spec/"]


@pytest.mark.parametrize(
    ("files", "problem"),
    [
        (
            {"spec": SPEC.replace("I2_Written == TRUE\n", "")},
            "docs/pkg/spec/Claim.tla: I2_Written is in the table but not defined",
        ),
        (
            {"readme": README.replace(" and `I2_Written`", "")},
            "docs/pkg/spec/Claim.tla: I2_Written is not in docs/pkg/spec/README.md",
        ),
        (
            {"config": CONFIG.replace("PROPERTIES\n    I2_Written\n", "")},
            "docs/pkg/spec/Claim.tla: I2_Written is checked by no configuration",
        ),
        (
            {"spec": SPEC.replace("| test_i1_once", "| test_i1_renamed")},
            "docs/pkg/spec/Claim.tla: I1_Once's test test_i1_renamed is not a test of pkg",
        ),
        (
            {
                "spec": SPEC.replace("| test_i1_once", "| test_i3_upgraded"),
                "tests": TESTS.replace("def test_i1_once", "def test_once"),
            },
            "docs/pkg/spec/Claim.tla: I1_Once's test test_i3_upgraded is for I3, not I1",
        ),
        (
            {"tests": TESTS + "\n\ndef test_i4_new() -> None: ...\n"},
            "docs/pkg/spec/Claim.tla: pkg's tests hold I4, which no row names",
        ),
        (
            {"config": CONFIG + "    Unlisted\n"},
            "docs/pkg/spec/Claim.cfg: Unlisted is not in the table",
        ),
        (
            {"moon": "spec: 'scripts/tlc Claim.tla'\n"},
            "docs/pkg/spec/Claim.cfg is not in packages/pkg/moon.yml: no task runs it",
        ),
        (
            {"readme": "`I1_Once` and `I2_Written`.\n"},
            "docs/pkg/spec/README.md: no `| Action | Code |` table",
        ),
        (
            {"readme": README.replace("| `Tick` |", "| `Tock` |")},
            "docs/pkg/spec/README.md: the action Tock is not in the spec",
        ),
        (
            {"source": SOURCE.replace("def _take", "def _took")},
            "docs/pkg/spec/README.md: _take is not defined in the package",
        ),
    ],
)
def test_each_disagreement_is_found(tmp_path: Path, files: dict[str, str], problem: str) -> None:
    write(tmp_path, **files)
    assert check_spec.problems(tmp_path) == [problem]


def test_a_spec_with_no_table_is_found(tmp_path: Path) -> None:
    write(tmp_path, spec="---- MODULE Claim ----\nTake(p) == TRUE\nTick == TRUE\n====\n")
    assert check_spec.problems(tmp_path) == [
        "docs/pkg/spec/Claim.tla: no property table in its header",
        "docs/pkg/spec/Claim.tla: pkg's tests hold I1, which no row names",
        "docs/pkg/spec/Claim.tla: pkg's tests hold I2, which no row names",
        "docs/pkg/spec/Claim.tla: pkg's tests hold I3, which no row names",
        "docs/pkg/spec/Claim.cfg: I1_Once is not in the table",
        "docs/pkg/spec/Claim.cfg: I2_Written is not in the table",
    ]


def test_main_fails_with_each_problem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, config=CONFIG + "    Unlisted\n")
    monkeypatch.chdir(tmp_path)
    assert check_spec.main() == 1
    assert capsys.readouterr().err == "docs/pkg/spec/Claim.cfg: Unlisted is not in the table\n"
    (tmp_path / "docs" / "pkg" / "spec" / "Claim.cfg").write_text(CONFIG)
    assert check_spec.main() == 0
