"""What PyPI serves of a release's files (scripts/pypi.py), read from a fake simple index."""

import hashlib
import json
from pathlib import Path

import pypi
import pytest


def index(**projects: dict[str, str]) -> pypi.Fetch:
    """A PyPI whose simple index holds these projects: filename -> sha256."""

    def get(url: str) -> bytes | None:
        name = url.removeprefix(pypi.INDEX).strip("/")
        if name not in projects:
            return None
        files = [{"filename": f, "hashes": {"sha256": h}} for f, h in projects[name].items()]
        return json.dumps({"files": files}).encode()

    return get


def built(
    tmp_path: Path, name: str = "evalr-0.1.0-py3-none-any.whl", body: bytes = b"wheel"
) -> Path:
    directory = tmp_path / "dist"
    directory.mkdir(exist_ok=True)
    (directory / name).write_bytes(body)
    return directory


def sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("lattice_core_ai-0.1.0-py3-none-any.whl", ("lattice-core-ai", "0.1.0")),
        ("lattice_core_ai-0.1.0.tar.gz", ("lattice-core-ai", "0.1.0")),
        ("relayr_ai-0.1.0.dev0-py3-none-any.whl", ("relayr-ai", "0.1.0.dev0")),
        ("Foo.Bar-1.2.tar.gz", ("foo-bar", "1.2")),
    ],
)
def test_a_files_distribution_and_version_are_read_from_its_name(
    filename: str, expected: tuple[str, str]
) -> None:
    assert pypi.split(filename) == expected


def test_a_file_pypi_does_not_have_is_absent(tmp_path: Path) -> None:
    directory = built(tmp_path)
    assert pypi.report(directory, index()) == ["evalr-0.1.0-py3-none-any.whl: absent"]
    assert pypi.report(directory, index(evalr={"evalr-0.0.9-py3-none-any.whl": "x"})) == [
        "evalr-0.1.0-py3-none-any.whl: absent"
    ]


def test_a_file_pypi_has_with_our_hash_is_the_same_and_with_another_is_different(
    tmp_path: Path,
) -> None:
    directory = built(tmp_path)
    name = "evalr-0.1.0-py3-none-any.whl"
    assert pypi.report(directory, index(evalr={name: sha(b"wheel")})) == [f"{name}: same"]
    assert pypi.report(directory, index(evalr={name: sha(b"other")})) == [f"{name}: different"]


def test_wait_returns_once_pypi_serves_the_file_and_polls_until_then(tmp_path: Path) -> None:
    directory = built(tmp_path)
    name = "evalr-0.1.0-py3-none-any.whl"
    calls: list[str] = []

    def get(url: str) -> bytes | None:
        calls.append(url)
        return index(evalr={name: sha(b"wheel")})(url) if len(calls) >= 3 else None

    slept: list[float] = []
    pypi.wait(directory, get, attempts=5, sleep=slept.append, interval=3)
    assert slept == [3, 3], "it waited twice, and the third time PyPI served the file"


def test_wait_gives_up_and_names_what_is_not_served(tmp_path: Path) -> None:
    directory = built(tmp_path)
    slept: list[float] = []
    with pytest.raises(TimeoutError, match=r"evalr-0\.1\.0-py3-none-any\.whl"):
        pypi.wait(directory, index(), attempts=3, sleep=slept.append)
    assert len(slept) == 2


def test_wait_refuses_a_file_pypi_serves_with_another_hash(tmp_path: Path) -> None:
    directory = built(tmp_path)
    other = index(evalr={"evalr-0.1.0-py3-none-any.whl": sha(b"other")})
    with pytest.raises(ValueError, match="another hash"):
        pypi.wait(directory, other, attempts=2, sleep=lambda _: None)


def test_require_names_what_an_earlier_stage_has_not_published() -> None:
    get = index(**{"lattice-core-ai": {"lattice_core_ai-0.1.0-py3-none-any.whl": "x"}})
    assert pypi.require(["lattice-core-ai==0.1.0"], get) == []
    assert pypi.require(["lattice-core-ai==0.1.0", "evalr==0.1.0"], get) == ["evalr==0.1.0"]
    assert pypi.require(["lattice-core-ai==0.2.0"], get) == ["lattice-core-ai==0.2.0"]
    assert pypi.require([], get) == []


def test_the_commands_exit_with_what_they_found(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = built(tmp_path)
    name = "evalr-0.1.0-py3-none-any.whl"
    assert pypi.main(["report", str(directory)], index()) == 0
    assert "absent" in capsys.readouterr().out
    assert pypi.main(["report", str(directory)], index(evalr={name: sha(b"other")})) == 1
    assert "another hash" in capsys.readouterr().err
    assert pypi.main(["require", "evalr==0.1.0"], index()) == 1
    assert "does not serve evalr==0.1.0" in capsys.readouterr().err
    assert pypi.main(["require"], index()) == 0
    assert pypi.main(["wait", str(directory)], index(evalr={name: sha(b"wheel")})) == 0
    assert pypi.main(["nope"], index()) == 2


def flaky(failures: int, then: bytes | None = None) -> pypi.Fetch:
    """A PyPI that can't be reached this many times, and then answers."""
    calls: list[str] = []

    def get(url: str) -> bytes | None:
        calls.append(url)
        if len(calls) <= failures:
            raise OSError("connection reset")
        return then

    return get


def test_a_fetch_that_fails_is_tried_again_and_then_given_up() -> None:
    slept: list[float] = []
    assert pypi.retried(flaky(2, b"ok"), 3, slept.append)("https://x") == b"ok"
    assert slept == [2.0, 4.0]
    with pytest.raises(OSError, match="connection reset"):
        pypi.retried(flaky(5), 3, slept.append)("https://x")


def test_wait_counts_a_pypi_that_errs_as_not_serving_yet(tmp_path: Path) -> None:
    directory = built(tmp_path)
    name = "evalr-0.1.0-py3-none-any.whl"
    answers = [flaky(1, index(evalr={name: sha(b"wheel")})(f"{pypi.INDEX}/evalr/"))]
    slept: list[float] = []
    pypi.wait(directory, answers[0], attempts=3, sleep=slept.append, interval=1)
    assert slept == [1]


def test_the_commands_report_a_pypi_that_cannot_be_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = built(tmp_path)
    assert pypi.main(["report", str(directory)], flaky(99)) == 1
    assert pypi.main(["require", "evalr==0.1.0"], flaky(99), lambda _: None) == 1
    assert "could not be read" in capsys.readouterr().err
