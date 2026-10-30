"""scripts/bun-install: the pinned Bun installs bun.lock as it is, or fails, saying why."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

BUN = """#!/usr/bin/env bash
# Reports $FAKE_VERSION; `install` appends $FAKE_LOCK_EDIT to bun.lock, exits $FAKE_INSTALL_STATUS.
if [[ $1 == --version ]]; then echo "$FAKE_VERSION"; exit 0; fi
[[ $* == "install --frozen-lockfile" ]] || exit 9
printf '%s' "$FAKE_LOCK_EDIT" >>bun.lock
exit "$FAKE_INSTALL_STATUS"
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository with scripts/bun-install, a .prototools pinning Bun 1.2.3, and a bun.lock."""
    (tmp_path / "scripts").mkdir()
    shutil.copy(ROOT / "scripts" / "bun-install", tmp_path / "scripts" / "bun-install")
    (tmp_path / ".prototools").write_text('proto = "0.1.0"\nbun = "1.2.3"\n')
    (tmp_path / "bun.lock").write_text("{}\n")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "bun").write_text(BUN)
    (tmp_path / "bin" / "bun").chmod(0o755)
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-qm", "init"], check=True)
    return tmp_path


def install(
    repo: Path, version: str = "1.2.3", status: int = 0, edit: str = ""
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "BUN": str(repo / "bin" / "bun"),
        "FAKE_VERSION": version,
        "FAKE_INSTALL_STATUS": str(status),
        "FAKE_LOCK_EDIT": edit,
    }
    return subprocess.run(
        [str(repo / "scripts" / "bun-install")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        cwd="/",
    )


def test_the_pinned_bun_installs_the_lockfile_as_it_is(repo: Path) -> None:
    result = install(repo)
    assert result.returncode == 0, result.stderr
    assert (repo / "bun.lock").read_text() == "{}\n"


def test_another_bun_is_refused_before_it_installs(repo: Path) -> None:
    result = install(repo, version="1.9.9", edit="rewritten")
    assert result.returncode == 1
    assert "pins Bun 1.2.3" in result.stderr
    assert "1.9.9" in result.stderr
    assert (repo / "bun.lock").read_text() == "{}\n"


def test_a_lockfile_that_would_change_fails_with_how_to_update_it(repo: Path) -> None:
    result = install(repo, status=1)
    assert result.returncode == 1
    assert "an install would change it" in result.stderr


def test_an_install_that_writes_the_lockfile_anyway_fails(repo: Path) -> None:
    result = install(repo, edit="rewritten")
    assert result.returncode == 1
    assert "the install changed bun.lock" in result.stderr
