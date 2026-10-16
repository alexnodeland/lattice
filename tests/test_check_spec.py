"""The formal specs agree with their configurations, READMEs and tests (scripts/check_spec.py)."""

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
PROPERTIES
    I2_Written
"""
TESTS = """
def test_i1_once() -> None: ...


async def test_i2_written() -> None: ...


def test_i3_upgraded() -> None: ...
"""


def write(root: Path, spec: str = SPEC, config: str = CONFIG, tests: str = TESTS) -> None:
    """A package `pkg` whose spec, configuration, README and tests are the ones given."""
    folder = root / "docs" / "pkg" / "spec"
    folder.mkdir(parents=True)
    (folder / "Claim.tla").write_text(spec)
    (folder / "Claim.cfg").write_text(config)
    (folder / "README.md").write_text("`I1_Once` and `I2_Written`.\n")
    (root / "packages" / "pkg" / "tests").mkdir(parents=True)
    (root / "packages" / "pkg" / "tests" / "test_claim.py").write_text(tests)


def test_the_repositorys_specs_agree() -> None:
    assert check_spec.problems(ROOT) == []


def test_a_spec_that_agrees_passes(tmp_path: Path) -> None:
    write(tmp_path)
    assert check_spec.problems(tmp_path) == []


def test_each_disagreement_is_found(tmp_path: Path) -> None:
    spec = SPEC.replace("test_i1_once", "test_i1_renamed").replace("I2_Written == TRUE\n", "")
    write(
        tmp_path,
        spec=spec.replace("Not modelled: I3", "Not modelled: nothing"),
        config=CONFIG.replace("I1_Once", "I1_Once\n    Unlisted"),
        tests=TESTS + "\ndef test_i4_new() -> None: ...\n",
    )
    assert check_spec.problems(tmp_path) == [
        "docs/pkg/spec/Claim.tla: I1_Once's test test_i1_renamed is not a test of pkg",
        "docs/pkg/spec/Claim.tla: I2_Written is in the table but not defined",
        "docs/pkg/spec/Claim.tla: pkg's tests hold I3, which no row names",
        "docs/pkg/spec/Claim.tla: pkg's tests hold I4, which no row names",
        "docs/pkg/spec/Claim.cfg: Unlisted is not in the table",
    ]


def test_a_property_the_readme_leaves_out_is_found(tmp_path: Path) -> None:
    write(tmp_path)
    (tmp_path / "docs" / "pkg" / "spec" / "README.md").write_text("`I1_Once` alone.\n")
    assert check_spec.problems(tmp_path) == [
        "docs/pkg/spec/Claim.tla: I2_Written is not in docs/pkg/spec/README.md"
    ]


def test_a_spec_with_no_table_is_found(tmp_path: Path) -> None:
    write(tmp_path, spec="---- MODULE Claim ----\n====\n", config="SPECIFICATION Spec\n")
    assert check_spec.problems(tmp_path) == [
        "docs/pkg/spec/Claim.tla: no property table in its header",
        "docs/pkg/spec/Claim.tla: pkg's tests hold I1, which no row names",
        "docs/pkg/spec/Claim.tla: pkg's tests hold I2, which no row names",
        "docs/pkg/spec/Claim.tla: pkg's tests hold I3, which no row names",
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


def test_a_root_with_no_spec_fails(tmp_path: Path) -> None:
    assert check_spec.problems(tmp_path) == [f"no spec in {tmp_path}/docs/*/spec/"]
