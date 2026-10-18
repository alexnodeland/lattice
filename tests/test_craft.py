"""scripts/craft: what it unpacks is the pinned release's, however many runs fetch it."""

import hashlib
import io
import os
import re
import shutil
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
PINS = ROOT / "scripts" / "crafts"

CURL = """#!/usr/bin/env bash
# Writes $FAKE_DOWNLOAD's file to --output, slowly, so two runs' downloads overlap.
while [[ $# -gt 0 ]]; do [[ $1 == --output ]] && out=$2; shift; done
head -c 5 "$FAKE_DOWNLOAD" >"$out"
sleep 0.3
cat "$FAKE_DOWNLOAD" >"$out"
"""
UNAME = """#!/usr/bin/env bash
[[ $1 == -s ]] && echo "${FAKE_SYSTEM:-Darwin}" || echo "${FAKE_MACHINE:-arm64}"
"""


def archive(*names: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as made:
        for name in names:
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFREG | 0o755) << 16
            made.writestr(info, "#!/bin/sh\n")
    return buffer.getvalue()


def tarball(*names: str) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as made:
        for name in names:
            info = tarfile.TarInfo(name)
            info.mode, info.size = 0o755, 10
            made.addfile(info, io.BytesIO(b"#!/bin/sh\n"))
    return buffer.getvalue()


LINUX = tarball(
    "toolcraft-9.9.9-linux-x86_64/bin/toolcraft-cli",
    "toolcraft-9.9.9-linux-x86_64/share/doc/toolcraft/LICENSE-MIT",
    "toolcraft-9.9.9-linux-x86_64/share/doc/toolcraft/NOTICE",
    "toolcraft-9.9.9-linux-x86_64/share/toolcraft/models/ATTRIBUTION.txt",
    "toolcraft-9.9.9-linux-x86_64/share/toolcraft/models/ocr.rten.LICENCE.txt",
    "toolcraft-9.9.9-linux-x86_64/share/toolcraft/models/ocr.rten",
)
EMPTY = tarball("toolcraft-9.9.9-linux-aarch64/README.md")
CLI = archive("toolcraft-cli-9.9.9-macos-universal/toolcraft-cli")
WEB = archive("toolcraft-web-9.9.9/index.html", "toolcraft-web-9.9.9/x_bg.wasm")
ALONE = tarball("toolcraft-cli-9.9.9-linux-x86_64/toolcraft-cli")


def pin(*assets: tuple[bytes, str]) -> str:
    return "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for data, name in assets)


PIN = pin(
    (EMPTY, "toolcraft-9.9.9-linux-aarch64.tar.gz"),
    (LINUX, "toolcraft-9.9.9-linux-x86_64.tar.gz"),
    (CLI, "toolcraft-cli-9.9.9-macos-universal.zip"),
    (WEB, "toolcraft-web-9.9.9.zip"),
)


@pytest.fixture
def scripts(tmp_path: Path) -> Path:
    """scripts/craft, pinning toolcraft to `PIN`, with a curl and a uname of its own."""
    folder = tmp_path / "scripts"
    (folder / "crafts").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "craft", folder / "craft")
    (folder / "crafts" / "toolcraft.sha256").write_text(PIN)
    tools = tmp_path / "bin"
    tools.mkdir()
    for name, body in (("curl", CURL), ("uname", UNAME)):
        (tools / name).write_text(body)
        (tools / name).chmod(0o755)
    return folder


def craft(
    scripts: Path,
    what: str,
    download: bytes,
    *,
    app: str = "toolcraft",
    machine: tuple[str, str] = ("Darwin", "arm64"),
) -> subprocess.Popen[str]:
    root = scripts.parent
    fetched = root / f"download-{hashlib.sha256(download).hexdigest()}"
    fetched.write_bytes(download)
    env = {
        **os.environ,
        "PATH": f"{root / 'bin'}:{os.environ['PATH']}",
        "CRAFT_CACHE": str(root / "cache"),
        "FAKE_DOWNLOAD": str(fetched),
        "FAKE_SYSTEM": machine[0],
        "FAKE_MACHINE": machine[1],
    }
    return subprocess.Popen(
        [str(scripts / "craft"), app, what],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def finished(run: subprocess.Popen[str]) -> tuple[int, str, str]:
    code = run.wait(timeout=30)
    out, err = run.communicate()
    return code, out, err


ASSET = re.compile(
    r"(?P<app>[a-z]+)(?P<kind>-cli|-web)?-(?P<version>\d+\.\d+\.\d+)"
    r"(?P<target>-linux-x86_64\.tar\.gz|-linux-aarch64\.tar\.gz|-macos-universal\.zip|\.zip)"
)


@pytest.mark.parametrize("path", sorted(PINS.glob("*.sha256")), ids=lambda path: path.stem)
def test_each_pin_names_four_assets_of_one_release(path: Path) -> None:
    lines = [line.split("  ") for line in path.read_text().splitlines()]
    assert all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest, _ in lines), "SHA-256s"
    found = [match for _, name in lines if (match := ASSET.fullmatch(name))]
    assert len(found) == len(lines) == 4, "one asset for each of what scripts/craft asks for"
    assert {match["app"] for match in found} == {path.stem}
    assert len({match["version"] for match in found}) == 1, "one release"
    assert sorted(((match["kind"] or "-cli")[1:], match["target"]) for match in found) == [
        ("cli", "-linux-aarch64.tar.gz"),
        ("cli", "-linux-x86_64.tar.gz"),
        ("cli", "-macos-universal.zip"),
        ("web", ".zip"),
    ]


def test_runs_at_once_on_a_cold_cache_each_find_the_whole_cli(scripts: Path) -> None:
    runs = [craft(scripts, "cli", CLI) for _ in range(3)]
    results = [finished(run) for run in runs]
    assert [code for code, _, _ in results] == [0, 0, 0], results
    paths = {out.strip() for _, out, _ in results}
    assert len(paths) == 1
    (cli,) = paths
    assert cli.endswith("toolcraft-cli-9.9.9-macos-universal/toolcraft-cli")
    assert os.access(cli, os.X_OK)
    cache = scripts.parent / "cache"
    assert (cache / hashlib.sha256(CLI).hexdigest()).is_symlink()
    unpacked = [p for p in cache.iterdir() if p.name.startswith("unpacking.")]
    assert len(unpacked) == 1, "one run's unpacking is kept, and the others' go"


def test_on_linux_the_cli_is_the_tarballs(scripts: Path) -> None:
    code, out, _ = finished(craft(scripts, "cli", LINUX, machine=("Linux", "x86_64")))
    assert code == 0
    assert out.strip().endswith("toolcraft-9.9.9-linux-x86_64/bin/toolcraft-cli")


def test_a_cli_only_tarball_is_pinned_as_a_full_one_is(scripts: Path) -> None:
    alone = pin((ALONE, "toolcraft-cli-9.9.9-linux-x86_64.tar.gz"))
    (scripts / "crafts" / "toolcraft.sha256").write_text(alone)
    code, out, _ = finished(craft(scripts, "cli", ALONE, machine=("Linux", "x86_64")))
    assert code == 0
    assert out.strip().endswith("toolcraft-cli-9.9.9-linux-x86_64/toolcraft-cli")


def test_a_pin_of_both_tarballs_is_refused_before_anything_is_fetched(scripts: Path) -> None:
    both = PIN + pin((ALONE, "toolcraft-cli-9.9.9-linux-x86_64.tar.gz"))
    (scripts / "crafts" / "toolcraft.sha256").write_text(both)
    code, out, err = finished(craft(scripts, "cli", ALONE, machine=("Linux", "x86_64")))
    assert code == 1
    assert "must pin one asset like toolcraft(-cli)?-" in err
    assert out == ""
    assert not (scripts.parent / "cache").exists()


def test_the_notices_are_each_licence_and_notice_beside_the_cli(scripts: Path) -> None:
    code, out, _ = finished(craft(scripts, "notices", LINUX, machine=("Linux", "x86_64")))
    assert code == 0
    found = [line.split("toolcraft-9.9.9-linux-x86_64/")[1] for line in out.splitlines()]
    assert found == [
        "share/doc/toolcraft/LICENSE-MIT",
        "share/doc/toolcraft/NOTICE",
        "share/toolcraft/models/ATTRIBUTION.txt",
        "share/toolcraft/models/ocr.rten.LICENCE.txt",
    ]


def test_an_asset_without_what_was_asked_for_fails(scripts: Path) -> None:
    code, out, err = finished(craft(scripts, "cli", EMPTY, machine=("Linux", "aarch64")))
    assert code == 1
    assert "toolcraft-9.9.9-linux-aarch64.tar.gz holds no cli" in err
    assert out == ""


def test_the_browser_build_is_its_directory(scripts: Path) -> None:
    code, out, _ = finished(craft(scripts, "web", WEB))
    assert code == 0
    assert sorted(p.name for p in Path(out.strip()).iterdir()) == ["index.html", "x_bg.wasm"]


def test_a_download_with_other_bytes_is_never_unpacked_nor_kept(scripts: Path) -> None:
    code, out, err = finished(craft(scripts, "cli", archive("evil/toolcraft-cli")))
    assert code == 1
    assert "is not toolcraft-cli-9.9.9-macos-universal.zip" in err
    assert out == ""
    assert list((scripts.parent / "cache").iterdir()) == []


def test_a_cached_asset_with_other_bytes_is_never_unpacked(scripts: Path) -> None:
    cache = scripts.parent / "cache"
    cache.mkdir()
    (cache / "toolcraft-cli-9.9.9-macos-universal.zip").write_bytes(b"tampered")
    code, out, err = finished(craft(scripts, "cli", CLI))
    assert code == 1
    assert "remove it to download it again" in err
    assert out == ""


@pytest.mark.parametrize(
    ("app", "what", "message"),
    [
        ("toolcraft", "desktop", "no desktop for Darwin arm64"),
        ("othercraft", "cli", "no pin for othercraft"),
        ("../crafts/toolcraft", "cli", "no pin for ../crafts/toolcraft"),
    ],
)
def test_anything_else_is_refused(scripts: Path, app: str, what: str, message: str) -> None:
    code, _, err = finished(craft(scripts, what, CLI, app=app))
    assert code == 2
    assert message in err


def test_the_apps_brand_names_nothing_of_lattices() -> None:
    """The brand licence keeps its name to the official builds: RFC-0003 records the licence."""
    listed = subprocess.run(
        ["git", "grep", "-il", "artcraft", "--", "docs", "packages/*/src", "scripts"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert listed.stdout.split() == ["docs/rfcs/0003-native-files-as-artifacts.md"]
