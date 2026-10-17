"""scripts/tlc: the jar it runs is the pinned one, however many runs download it at once."""

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
JAR = b"the pinned jar's bytes"

CURL = """#!/usr/bin/env bash
# Writes $FAKE_DOWNLOAD to --output, slowly, so two runs' downloads overlap.
while [[ $# -gt 0 ]]; do [[ $1 == --output ]] && out=$2; shift; done
printf '%s' "${FAKE_DOWNLOAD:0:5}" >"$out"
sleep 0.3
printf '%s' "$FAKE_DOWNLOAD" >"$out"
"""
JAVA = """#!/usr/bin/env bash
# Checks that the jar on the classpath is whole, as TLC would read it, while the other run renames.
while [[ $# -gt 0 ]]; do [[ $1 == -cp ]] && jar=$2; shift; done
sleep 0.3
[[ $(cat "$jar") == "$FAKE_JAR" ]] || { echo "java: $jar is not whole" >&2; exit 3; }
echo "java ran $(basename "$jar")"
"""


@pytest.fixture
def scripts(tmp_path: Path) -> Path:
    """scripts/tlc, pinned to ``JAR``, with a curl and a java of the test's own on the PATH."""
    folder = tmp_path / "scripts"
    folder.mkdir()
    shutil.copy(ROOT / "scripts" / "tlc", folder / "tlc")
    digest = hashlib.sha256(JAR).hexdigest()
    (folder / "tlc.sha256").write_text(f"{digest}  tla2tools-9.9.9.jar\n")
    tools = tmp_path / "bin"
    tools.mkdir()
    for name, body in (("curl", CURL), ("java", JAVA)):
        (tools / name).write_text(body)
        (tools / name).chmod(0o755)
    (tmp_path / "Spec.tla").write_text("")
    return folder


def tlc(scripts: Path, download: bytes, *configs: str) -> subprocess.Popen[str]:
    root = scripts.parent
    env = {
        **os.environ,
        "PATH": f"{root / 'bin'}:{os.environ['PATH']}",
        "TLC_CACHE": str(root / "cache"),
        "FAKE_DOWNLOAD": download.decode(),
        "FAKE_JAR": JAR.decode(),
    }
    return subprocess.Popen(
        [str(scripts / "tlc"), str(root / "Spec.tla"), *configs],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_the_pinned_tla2tools_is_1_7_4() -> None:
    pin = (ROOT / "scripts" / "tlc.sha256").read_text().split()
    assert pin == [
        "936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88",
        "tla2tools-1.7.4.jar",
    ]


def test_runs_at_once_on_a_cold_cache_each_run_the_whole_jar(scripts: Path) -> None:
    runs = [tlc(scripts, JAR, "One.cfg") for _ in range(3)]
    results = [(run.wait(timeout=30), *run.communicate()) for run in runs]
    assert [code for code, _, _ in results] == [0, 0, 0], results
    assert all("java ran tla2tools-9.9.9.jar" in out for _, out, _ in results)
    assert sorted(p.name for p in (scripts.parent / "cache").iterdir()) == ["tla2tools-9.9.9.jar"]


def test_a_download_with_other_bytes_never_runs_nor_stays(scripts: Path) -> None:
    run = tlc(scripts, b"something else", "One.cfg")
    code, out, err = run.wait(timeout=30), *run.communicate()
    assert code == 1
    assert "is not tla2tools-9.9.9.jar" in err
    assert "java ran" not in out
    assert list((scripts.parent / "cache").iterdir()) == []


def test_a_cached_jar_with_other_bytes_never_runs(scripts: Path) -> None:
    cache = scripts.parent / "cache"
    cache.mkdir()
    (cache / "tla2tools-9.9.9.jar").write_bytes(b"tampered")
    run = tlc(scripts, JAR, "One.cfg")
    code, out, err = run.wait(timeout=30), *run.communicate()
    assert code == 1
    assert "remove it to download it again" in err
    assert "java ran" not in out


def test_each_configuration_runs_in_turn(scripts: Path) -> None:
    run = tlc(scripts, JAR, "One.cfg", "Two.cfg")
    code, out, _ = run.wait(timeout=30), *run.communicate()
    assert code == 0
    assert out.count("java ran") == 2
    assert "tlc: Spec.tla with One.cfg" in out
    assert "tlc: Spec.tla with Two.cfg" in out


def test_no_configuration_is_refused(scripts: Path) -> None:
    run = tlc(scripts, JAR)
    code, _, err = run.wait(timeout=30), *run.communicate()
    assert code == 2
    assert "name at least one configuration" in err
