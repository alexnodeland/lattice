"""What the worker clears after each call, over a stand-in for `/proc`."""

import os
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from artifactr.files.app import AppFailed, FakeApp
from artifactr.files.worker import Limits, Worker, worker_app
from artifactr.files.worker.sweep import PASSES, SweepFailed, sweep


def process(proc: Path, pid: int, parent: int) -> None:
    """A process in the stand-in `/proc`, as this user's, under its parent."""
    (proc / str(pid)).mkdir()
    (proc / str(pid) / "stat").write_text(f"{pid} (a (strange) name) S {parent} 1 1 0")


def others(count: int) -> list[int]:
    """Process ids above this process's, as many as asked: never its own, which the sweep keeps.

    A fixed id could be the test's own process's, which the sweep would keep, not kill.
    """
    return [os.getpid() + offset for offset in range(1, count + 1)]


def test_every_other_process_of_this_user_is_killed_and_the_calls_files_are_gone(
    tmp_path: Path,
) -> None:
    proc, temporary = tmp_path / "proc", tmp_path / "tmp"
    proc.mkdir()
    temporary.mkdir()
    me = os.getpid()
    parent, stray, gone = others(3)
    (proc / "1").mkdir()  # the container's init, whose parent isn't listed
    process(proc, parent, 1)
    process(proc, me, parent)
    process(proc, stray, 1)  # a stray: in a session of its own, under init
    (proc / "self").mkdir()
    (proc / str(gone)).symlink_to(proc / "gone")  # ended as it was listed
    (temporary / "wordcraft-x" / "in").mkdir(parents=True)
    (temporary / "planted").write_text("for the next call")
    (temporary / "link").symlink_to(tmp_path)
    sealed = temporary / "sealed" / "deeper"
    sealed.mkdir(parents=True)
    (sealed / "filler").write_bytes(b"to fill the tmpfs for good")
    sealed.chmod(0)
    sealed.parent.chmod(0)
    killed: list[int] = []
    assert sweep(proc=proc, temporary=temporary, kill=lambda pid, _: killed.append(pid)) == [stray]
    assert killed == [stray]
    assert list(temporary.iterdir()) == []
    assert tmp_path.exists(), "a link is removed, never followed"


async def test_the_worker_sweeps_after_each_call_before_the_next() -> None:
    swept: list[int] = []
    served = worker_app(
        FakeApp(), token="s3cret", limits=Limits(), sweep=lambda: swept.append(len(swept))
    )
    transport = httpx.ASGITransport(app=served)
    worker = await Worker.connect("http://worker", token="s3cret", transport=transport)
    made = await worker.apply(None, [], deadline=5)
    await worker.inspect(made.content, deadline=5)
    await worker.aclose()
    assert swept == [0, 1]


def test_a_worker_with_no_parent_listed_keeps_itself(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    proc.mkdir()
    process(proc, os.getpid(), 0)
    assert sweep(proc=proc, temporary=proc / str(os.getpid()), kill=os.kill) == []


def respawning(proc: Path, times: int) -> Callable[[int, int], None]:
    """A kill whose stray starts another, at a higher id, `times` times over."""
    spawned: list[int] = []

    def kill(pid: int, _signal: int) -> None:
        if len(spawned) < times:
            spawned.append(pid + 1)
            process(proc, pid + 1, 1)

    return kill


@pytest.mark.parametrize("times", [1, PASSES - 2])
def test_strays_that_start_each_other_again_are_killed_again(tmp_path: Path, times: int) -> None:
    proc, temporary = tmp_path / "proc", tmp_path / "tmp"
    proc.mkdir()
    temporary.mkdir()
    process(proc, os.getpid(), 0)
    [first] = others(1)
    process(proc, first, 1)
    killed = sweep(proc=proc, temporary=temporary, kill=respawning(proc, times))
    assert killed == list(range(first, first + 1 + times))


def test_strays_that_keep_starting_fail_the_sweep(tmp_path: Path) -> None:
    proc, temporary = tmp_path / "proc", tmp_path / "tmp"
    proc.mkdir()
    temporary.mkdir()
    process(proc, os.getpid(), 0)
    process(proc, others(1)[0], 1)
    with pytest.raises(SweepFailed, match=f"still starting after {PASSES} sweeps"):
        sweep(proc=proc, temporary=temporary, kill=respawning(proc, PASSES))


def test_what_cant_be_removed_fails_the_sweep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc, temporary = tmp_path / "proc", tmp_path / "tmp"
    proc.mkdir()
    temporary.mkdir()
    process(proc, os.getpid(), 0)
    (temporary / "kept").write_text("")
    monkeypatch.setattr("artifactr.files.worker.sweep._remove", lambda _path: None)
    with pytest.raises(SweepFailed, match="still holds kept"):
        sweep(proc=proc, temporary=temporary)


async def test_a_worker_that_cant_clear_itself_serves_nothing_more() -> None:
    def fails() -> None:
        raise SweepFailed("tmp still holds kept")

    served = worker_app(FakeApp(), token="s3cret", limits=Limits(), sweep=fails)
    transport = httpx.ASGITransport(app=served)
    worker = await Worker.connect("http://worker", token="s3cret", transport=transport)
    with pytest.raises(AppFailed, match="couldn't clear itself") as failed:
        await worker.apply(None, [], deadline=5)
    assert failed.value.failure == "crashed"
    async with httpx.AsyncClient(transport=transport, base_url="http://worker") as client:
        health = await client.get("/", headers={"Authorization": "Bearer s3cret"})
    assert health.status_code == 503
    await worker.aclose()
