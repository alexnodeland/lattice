"""scripts/generate.py: a generated file holds only what its module printed."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "generate.py"
GENERATOR = """\
import sys

sys.stdout.write("generated " + " ".join(sys.argv[1:]) + "\\n")
"""
FAILING = "raise SystemExit('the generator failed')\n"


def run(tmp_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the script as a task does, after a tool that printed first, as proto's shim can."""
    command = 'echo \'{"type":"message","message":"a notice"}\'; "$@"'
    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    return subprocess.run(
        ["sh", "-c", command, "sh", sys.executable, str(SCRIPT), *arguments],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_file_holds_only_what_the_module_printed(tmp_path: Path) -> None:
    (tmp_path / "generator.py").write_text(GENERATOR)
    ran = run(tmp_path, "out.json", "generator", "rules", "v1")
    assert ran.returncode == 0, ran.stderr
    assert (tmp_path / "out.json").read_text() == "generated rules v1\n"
    assert ran.stdout == '{"type":"message","message":"a notice"}\n', "the notice stays out"


def test_a_module_that_fails_leaves_the_file_as_it_was(tmp_path: Path) -> None:
    (tmp_path / "failing.py").write_text(FAILING)
    (tmp_path / "out.json").write_text("{}\n")
    ran = run(tmp_path, "out.json", "failing")
    assert ran.returncode == 1
    assert "the generator failed" in ran.stderr
    assert (tmp_path / "out.json").read_text() == "{}\n"


@pytest.mark.parametrize("arguments", [(), ("out.json",)])
def test_it_says_how_to_call_it_without_an_output_and_a_module(
    tmp_path: Path, arguments: tuple[str, ...]
) -> None:
    ran = run(tmp_path, *arguments)
    assert ran.returncode == 1
    assert "Usage: scripts/generate.py OUTPUT MODULE" in ran.stderr
