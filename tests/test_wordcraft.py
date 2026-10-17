"""scripts/wordcraft: what it unpacks is the pinned release's, however many runs fetch it."""

import hashlib
import io
import os
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

CURL = """#!/usr/bin/env bash
# Writes $FAKE_DOWNLOAD's file to --output, slowly, so two runs' downloads overlap.
while [[ $# -gt 0 ]]; do [[ $1 == --output ]] && out=$2; shift; done
head -c 5 "$FAKE_DOWNLOAD" >"$out"
sleep 0.3
cat "$FAKE_DOWNLOAD" >"$out"
"""
UNAME = """#!/usr/bin/env bash
[[ $1 == -s ]] && echo Darwin || echo arm64
"""


def archive(*names: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as made:
        for name in names:
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFREG | 0o755) << 16
            made.writestr(info, "#!/bin/sh\n")
    return buffer.getvalue()


CLI = archive("wordcraft-cli-9.9.9-macos-universal/wordcraft-cli")
WEB = archive("wordcraft-web-9.9.9/index.html", "wordcraft-web-9.9.9/x_bg.wasm")


@pytest.fixture
def scripts(tmp_path: Path) -> Path:
    """scripts/wordcraft, pinned to `CLI` and `WEB`, with a curl and a uname of its own."""
    folder = tmp_path / "scripts"
    folder.mkdir()
    shutil.copy(ROOT / "scripts" / "wordcraft", folder / "wordcraft")
    (folder / "wordcraft.sha256").write_text(
        f"{hashlib.sha256(b'linux').hexdigest()}  wordcraft-9.9.9-linux-x86_64.tar.gz\n"
        f"{hashlib.sha256(CLI).hexdigest()}  wordcraft-cli-9.9.9-macos-universal.zip\n"
        f"{hashlib.sha256(WEB).hexdigest()}  wordcraft-web-9.9.9.zip\n"
    )
    tools = tmp_path / "bin"
    tools.mkdir()
    for name, body in (("curl", CURL), ("uname", UNAME)):
        (tools / name).write_text(body)
        (tools / name).chmod(0o755)
    return folder


def wordcraft(scripts: Path, what: str, download: bytes) -> subprocess.Popen[str]:
    root = scripts.parent
    fetched = root / f"download-{hashlib.sha256(download).hexdigest()}"
    fetched.write_bytes(download)
    env = {
        **os.environ,
        "PATH": f"{root / 'bin'}:{os.environ['PATH']}",
        "WORDCRAFT_CACHE": str(root / "cache"),
        "FAKE_DOWNLOAD": str(fetched),
    }
    return subprocess.Popen(
        [str(scripts / "wordcraft"), what],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_the_pin_is_wordcrafts_0_7_0_release() -> None:
    pin = [
        line.split() for line in (ROOT / "scripts" / "wordcraft.sha256").read_text().splitlines()
    ]
    assert {name: digest for digest, name in pin} == {
        "wordcraft-0.7.0-linux-aarch64.tar.gz": (
            "b5fce7f31bbbf38828c1714d7d43244ae85f034bbe761dfa401e044f976ba45e"
        ),
        "wordcraft-0.7.0-linux-x86_64.tar.gz": (
            "63009f88e3dbaea70ac1378fabc8555ae14775d32829175c5da2551abe03932f"
        ),
        "wordcraft-cli-0.7.0-macos-universal.zip": (
            "56bda3406af0aa1c96cece8ad145ab2602d2f7f8919d758d4292c5c75f2dfb50"
        ),
        "wordcraft-web-0.7.0.zip": (
            "98df7c68a0ac788a9ac0f531fd34c31ab7d89965abb4935f57168d287dab3189"
        ),
    }


def test_runs_at_once_on_a_cold_cache_each_find_the_whole_cli(scripts: Path) -> None:
    runs = [wordcraft(scripts, "cli", CLI) for _ in range(3)]
    results = [(run.wait(timeout=30), *run.communicate()) for run in runs]
    assert [code for code, _, _ in results] == [0, 0, 0], results
    paths = {out.strip() for _, out, _ in results}
    assert len(paths) == 1
    (cli,) = paths
    assert cli.endswith("wordcraft-cli-9.9.9-macos-universal/wordcraft-cli")
    assert os.access(cli, os.X_OK)
    cache = scripts.parent / "cache"
    assert (cache / hashlib.sha256(CLI).hexdigest()).is_symlink()
    unpacked = [p for p in cache.iterdir() if p.name.startswith("unpacking.")]
    assert len(unpacked) == 1, "one run's unpacking is kept, and the others' go"


def test_the_browser_build_is_its_directory(scripts: Path) -> None:
    run = wordcraft(scripts, "web", WEB)
    code, out, _ = run.wait(timeout=30), *run.communicate()
    assert code == 0
    assert sorted(p.name for p in Path(out.strip()).iterdir()) == ["index.html", "x_bg.wasm"]


def test_a_download_with_other_bytes_is_never_unpacked_nor_kept(scripts: Path) -> None:
    run = wordcraft(scripts, "cli", archive("evil/wordcraft-cli"))
    code, out, err = run.wait(timeout=30), *run.communicate()
    assert code == 1
    assert "is not wordcraft-cli-9.9.9-macos-universal.zip" in err
    assert out == ""
    assert list((scripts.parent / "cache").iterdir()) == []


def test_a_cached_asset_with_other_bytes_is_never_unpacked(scripts: Path) -> None:
    cache = scripts.parent / "cache"
    cache.mkdir()
    (cache / "wordcraft-cli-9.9.9-macos-universal.zip").write_bytes(b"tampered")
    run = wordcraft(scripts, "cli", CLI)
    code, out, err = run.wait(timeout=30), *run.communicate()
    assert code == 1
    assert "remove it to download it again" in err
    assert out == ""


def test_anything_else_is_refused(scripts: Path) -> None:
    run = wordcraft(scripts, "desktop", CLI)
    code, _, err = run.wait(timeout=30), *run.communicate()
    assert code == 2
    assert "no desktop for Darwin arm64" in err
