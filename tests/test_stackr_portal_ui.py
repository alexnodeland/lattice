"""The template's scripts/build-portal-ui.sh: the commit it builds portalr's UIs from is the one
uv.lock pins portalr at, the one place that says which portalr is installed."""

import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parent.parent
    / "packages"
    / "stackr"
    / "template"
    / "{% if use_portal %}scripts{% endif %}"
    / "build-portal-ui.sh"
)
PINNED = "0123456789abcdef0123456789abcdef01234567"
OTHER = "fedcba9876543210fedcba9876543210fedcba98"

REPOSITORY = "https://github.com/alexnodeland/lattice"


def package(name: str, source: str) -> str:
    """A package of a lock file."""
    return f'[[package]]\nname = "{name}"\nversion = "1"\nsource = {source}\n'


def git(path: str, rev: str) -> str:
    """A git source, as uv writes one: the rev asked for, and the commit it resolved to."""
    return f'{{ git = "{REPOSITORY}?subdirectory=packages%2F{path}&rev={rev}#{rev}" }}'


LOCK = "version = 1\n\n" + "\n".join(
    [
        package("grantr", git("grantr", OTHER)),
        package("portalr", git("portalr", PINNED)),
        package("portalr-other", f'{{ git = "https://example.test/x?rev={OTHER}#{OTHER}" }}'),
    ]
)


def run(lock: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "uv.lock"
    path.write_text(lock)
    return subprocess.run(
        ["bash", str(SCRIPT), "--print-rev", str(path)], capture_output=True, text=True, check=False
    )


def test_the_commit_is_the_one_the_lock_pins_portalr_at_and_no_other_packages(
    tmp_path: Path,
) -> None:
    done = run(LOCK, tmp_path)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == PINNED


@pytest.mark.parametrize(
    "lock",
    [
        "version = 1\n\n" + package("portalr", '{ editable = "../portalr" }'),
        "version = 1\n\n" + package("grantr", '{ registry = "https://pypi.org/simple" }'),
        "",
    ],
    ids=["a path source", "no portalr", "empty"],
)
def test_a_lock_that_pins_portalr_at_no_commit_fails_and_says_so(lock: str, tmp_path: Path) -> None:
    done = run(lock, tmp_path)
    assert done.returncode == 1
    assert "pins portalr at no git commit" in done.stderr
