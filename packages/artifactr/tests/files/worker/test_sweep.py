"""What the worker clears after each call, over a stand-in for `/proc`."""

import os
from pathlib import Path

import httpx

from artifactr.files.app import FakeApp
from artifactr.files.worker import Limits, Worker, worker_app
from artifactr.files.worker.sweep import sweep


def process(proc: Path, pid: int, parent: int) -> None:
    """A process in the stand-in `/proc`, as this user's, under its parent."""
    (proc / str(pid)).mkdir()
    (proc / str(pid) / "stat").write_text(f"{pid} (a (strange) name) S {parent} 1 1 0")


def test_every_other_process_of_this_user_is_killed_and_the_calls_files_are_gone(
    tmp_path: Path,
) -> None:
    proc, temporary = tmp_path / "proc", tmp_path / "tmp"
    proc.mkdir()
    temporary.mkdir()
    me = os.getpid()
    (proc / "1").mkdir()  # the container's init, whose parent isn't listed
    process(proc, 7, 1)
    process(proc, me, 7)
    process(proc, 4242, 1)  # a stray: in a session of its own, under init
    (proc / "self").mkdir()
    (proc / "4343").symlink_to(proc / "gone")  # ended as it was listed
    (temporary / "wordcraft-x" / "in").mkdir(parents=True)
    (temporary / "planted").write_text("for the next call")
    (temporary / "link").symlink_to(tmp_path)
    killed: list[int] = []
    assert sweep(proc=proc, temporary=temporary, kill=lambda pid, _: killed.append(pid)) == [4242]
    assert killed == [4242]
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
