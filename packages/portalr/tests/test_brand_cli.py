"""``portalr brand``: a kit started from each start is one the portal can serve, and checked."""

import json
import os
import sys
from pathlib import Path

import pytest

from portalr.brand import cli
from portalr.brand.cli import STARTS, main
from portalr.brand.tokens import DEFAULT

KIT_FILES = {"brand.json", "tokens.light.json", "tokens.dark.json", "tokens.reference.json"}


def said(capsys: pytest.CaptureFixture[str]) -> tuple[str, str]:
    out = capsys.readouterr()
    return out.out, out.err


def started(tmp_path: Path, start: str = "template") -> Path:
    kit = tmp_path / "kit"
    assert main(["brand", "init", str(kit), "--from", start]) == 0
    return kit


@pytest.mark.parametrize("start", sorted(STARTS))
def test_a_kit_started_from_each_start_validates(
    start: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kit = started(tmp_path, start)
    assert f"from {start}" in said(capsys)[0]
    assert main(["brand", "validate", str(kit)]) == 0
    assert "is one the portal can serve" in said(capsys)[0]
    assert [p.name for p in tmp_path.iterdir()] == ["kit"], "nothing is left beside it"


def test_a_started_kit_carries_the_default_in_full_and_a_notice(tmp_path: Path) -> None:
    kit = started(tmp_path)
    reference = json.loads((kit / "tokens.reference.json").read_text())
    assert reference["light"] == json.loads((DEFAULT / "tokens.light.json").read_text())
    assert reference["dark"] == json.loads((DEFAULT / "tokens.dark.json").read_text())
    assert "placeholders" in (kit / "NOTICE").read_text()


def test_an_examples_notice_says_whose_it_is(tmp_path: Path) -> None:
    text = (started(tmp_path, "calm") / "NOTICE").read_text()
    assert "portalr's example kit, calm" in text
    assert "portalr's MIT licence" in text
    assert "placeholders" not in text


def test_a_kit_is_started_in_an_empty_folder_too(tmp_path: Path) -> None:
    (tmp_path / "kit").mkdir()
    kit = started(tmp_path)
    assert {p.name for p in kit.iterdir()} >= KIT_FILES


@pytest.mark.parametrize("kind", ["full", "file", "dangling link"])
def test_a_kit_is_not_started_over_anything(
    kind: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    there = tmp_path / "there"
    if kind == "full":
        there.mkdir()
        (there / "mine.txt").write_text("keep")
    elif kind == "file":
        there.write_text("keep")
    else:
        there.symlink_to(tmp_path / "nowhere")
    assert main(["brand", "init", str(there)]) == 1
    assert "not an empty folder" in said(capsys)[1]
    if kind == "full":
        assert (there / "mine.txt").read_text() == "keep"
    elif kind == "file":
        assert there.read_text() == "keep"
    else:
        assert there.is_symlink()


def test_a_kit_that_cant_be_written_leaves_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(_: str) -> str:
        raise PermissionError(13, "Permission denied", "NOTICE")

    monkeypatch.setattr(cli, "notice", refused)
    assert main(["brand", "init", str(tmp_path / "kit")]) == 1
    assert said(capsys)[1] == "NOTICE: Permission denied\n"
    assert list(tmp_path.iterdir()) == []


def test_every_fault_is_said(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kit = started(tmp_path)
    (kit / "assets" / "favicon.svg").unlink()
    (kit / "tokens.light.json").write_text('{"color": {"nope": {"$value": "#000000"}}}')
    said(capsys)
    assert main(["brand", "validate", str(kit)]) == 1
    err = said(capsys)[1]
    assert "color.nope" in err
    assert "favicon.svg" in err


def test_faults_can_be_said_as_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kit = started(tmp_path)
    said(capsys)
    assert main(["brand", "validate", str(kit), "--json"]) == 0
    ok = json.loads(said(capsys)[0])
    assert ok["ok"] is True
    assert ok["name"] == "kit"
    assert len(ok["hash"]) == 16
    assert ok["faults"] == []
    (kit / "assets" / "favicon.svg").unlink()
    assert main(["brand", "validate", str(kit), "--json"]) == 1
    faults = json.loads(said(capsys)[0])
    assert faults["ok"] is False
    assert faults["faults"] == ["assets/favicon.svg: no such file in the kit"]


def test_a_hostile_name_forges_no_line_and_no_escape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kit = started(tmp_path)
    hostile = "x\nERROR forged\x1b[31m"
    (kit / "tokens.light.json").write_text(json.dumps({"color": {hostile: {"$value": "#000000"}}}))
    said(capsys)
    assert main(["brand", "validate", str(kit)]) == 1
    err = said(capsys)[1]
    assert "\x1b" not in err
    assert err.count("\n") == 1
    assert "ERROR forged" in err


def test_a_folder_that_isnt_there_is_said_to_be_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["brand", "validate", str(tmp_path / "none\x1b")]) == 1
    err = said(capsys)[1]
    assert "no such folder" in err
    assert "\x1b" not in err


@pytest.mark.parametrize("name", ["brand.json", "tokens.light.json", "assets/favicon.svg"])
@pytest.mark.parametrize("kind", ["fifo", "folder", "link"])
def test_a_kit_file_that_isnt_a_plain_file_is_refused_unopened(
    name: str, kind: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kit = started(tmp_path)
    file = kit / name
    file.unlink()
    if kind == "fifo":
        os.mkfifo(file)
    elif kind == "folder":
        file.mkdir()
    else:
        file.symlink_to(kit / "tokens.dark.json")
    said(capsys)
    assert main(["brand", "validate", str(kit)]) == 1
    assert f"{name}: a plain file of the kit's own" in said(capsys)[1]


@pytest.mark.parametrize("name", ["brand.json", "tokens.light.json"])
def test_a_number_too_long_to_read_is_a_fault(
    name: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kit = started(tmp_path)
    (kit / name).write_text('{"version": ' + "9" * 5000 + "}")
    said(capsys)
    assert main(["brand", "validate", str(kit)]) == 1
    assert f"{name}: not JSON in UTF-8" in said(capsys)[1]


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="needs file permissions")
@pytest.mark.parametrize("name", ["brand.json", "tokens.light.json", "assets/mark-light.svg"])
def test_a_file_that_cant_be_read_is_a_fault(
    name: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kit = started(tmp_path)
    (kit / name).chmod(0)
    said(capsys)
    assert main(["brand", "validate", str(kit)]) == 1
    assert f"{name}: can't be read" in said(capsys)[1]


def test_a_command_line_portalr_doesnt_take_exits_with_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for wrong in (["brand"], ["brand", "init"], ["brand", "init", "kit", "--from", "nope"]):
        with pytest.raises(SystemExit) as raised:
            main(wrong)
        assert raised.value.code == 2
    assert "usage: portalr" in said(capsys)[1]


def test_a_kit_isnt_started_where_its_folder_has_no_parent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["brand", "init", str(tmp_path / "none" / "kit")]) == 1
    assert "no such folder to start a kit in" in said(capsys)[1]
    assert list(tmp_path.iterdir()) == []


def test_a_missing_folder_is_said_as_json_too(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["brand", "validate", str(tmp_path / "none"), "--json"]) == 1
    out, err = said(capsys)
    assert json.loads(out)["faults"] == [f"{str(tmp_path / 'none')!r}: no such folder"]
    assert err == ""


@pytest.mark.parametrize("as_json", [False, True])
def test_a_refusal_with_no_file_named_is_said_plainly(
    as_json: bool, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def gone(_: Path) -> object:
        raise OSError("the disk has gone")

    monkeypatch.setattr(cli, "load", gone)
    assert main(["brand", "validate", "kit", *(["--json"] if as_json else [])]) == 1
    out, err = said(capsys)
    if as_json:
        assert json.loads(out) == {"ok": False, "faults": ["the disk has gone"]}
    else:
        assert err == "the disk has gone\n"
