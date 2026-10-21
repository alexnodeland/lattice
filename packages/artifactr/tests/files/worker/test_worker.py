"""The worker and the `Worker` that calls it, over the stand-in for `wordcraft-cli mcp`.

Every request goes through httpx's ASGI transport, so no socket is opened. `test_hostile.py` runs
the hostile corpus through the same worker, over WordCraft itself.
"""

import os
import re
import resource
import runpy
import signal
import socket
import stat
import sys
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from functools import partial
from pathlib import Path
from typing import cast

import anyio
import httpx
import pytest
import uvicorn
from starlette.routing import Route

from artifactr.files.app import App, AppCommand, AppFailed, Applied, FakeApp, Inspection
from artifactr.files.craft import CRAFTS
from artifactr.files.wordcraft import Subprocess
from artifactr.files.worker import Limits, Worker, worker_app
from artifactr.files.worker.__main__ import (
    ADAPTERS,
    HEAD,
    app_from_environment,
    worker_from_environment,
)
from artifactr.files.worker.limits import CONFINE
from artifactr.files.worker.wire import CALL, CALL_LIMIT, Hello
from tests.files.wordcraft.test_headless import FAKE, PNG

TOKEN = "a-token-for-the-tests-of-32-or-more"
LIMITS = Limits(edit=10, render=5, files=1 << 20, reply=1 << 20)

Connect = Callable[..., Awaitable[Worker]]


def cli(tmp_path: Path, name: str, script: str) -> Path:
    """An executable that runs a line of Python, standing in for a CLI, and says how it ended."""
    path = tmp_path / name
    path.write_text(f'#!/bin/sh\n"{sys.executable}" -I -c "{script}"\necho "status $?" >&2\n')
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def stand_in(tmp_path: Path, mode: str = "") -> Path:
    """The stand-in for `wordcraft-cli`, misbehaving as `mode` says."""
    path = tmp_path / f"wordcraft-cli{mode}"
    path.write_text(
        f'#!/bin/sh\nexport FAKE_PIDS="{tmp_path / "pids"}"\n'
        f'exec "{sys.executable}" -I "{FAKE}" --mode "{mode}" "$@"\n'
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture
async def connect() -> AsyncIterator[Connect]:
    """Connect a `Worker` to a worker over an app, with the token it is given."""
    workers: list[Worker] = []

    async def connect(app: App, *, limits: Limits = LIMITS, build: str | None = None) -> Worker:
        served = worker_app(app, token=TOKEN, limits=limits, build=build)
        transport = httpx.ASGITransport(app=served)
        worker = await Worker.connect("http://worker", token=TOKEN, transport=transport)
        workers.append(worker)
        return worker

    yield connect
    for worker in workers:
        await worker.aclose()


def wordcraft(cli: Path, limits: Limits = LIMITS) -> Subprocess:
    return Subprocess(cli, version="0.7.0", limit=limits.files, launcher=limits.launcher())


async def test_it_is_the_app_the_worker_runs_in_its_image(connect: Connect, tmp_path: Path) -> None:
    app: App = await connect(wordcraft(stand_in(tmp_path)), build="sha256:abc")
    assert (app.name, app.version, app.build) == ("wordcraft", "0.7.0", "sha256:abc")
    assert (app.talk, app.integration) == ("save", "files:wordcraft")


async def test_its_calls_are_the_apps_own(connect: Connect, tmp_path: Path) -> None:
    local = wordcraft(stand_in(tmp_path))
    worker = await connect(local)
    commands = [AppCommand(name="text.insert", args={"text": "Terms"})]
    applied = await worker.apply(None, commands, deadline=10)
    assert applied.inspection == (await local.apply(None, commands, deadline=10)).inspection
    assert await worker.inspect(applied.content, deadline=10) == applied.inspection
    assert (await worker.render(applied.content, 1, scale=0.5, deadline=10)).startswith(PNG)
    assert await worker.commands("heading") == await local.commands("heading")


async def test_what_the_app_refuses_the_worker_refuses(connect: Connect, tmp_path: Path) -> None:
    worker = await connect(wordcraft(stand_in(tmp_path)))
    with pytest.raises(AppFailed, match="not a valid zip package") as refused:
        await worker.inspect(b"PK junk", deadline=10)
    assert refused.value.failure == "refused"


async def test_a_call_is_held_to_the_workers_deadline(connect: Connect, tmp_path: Path) -> None:
    worker = await connect(wordcraft(stand_in(tmp_path, "hang")), limits=Limits(edit=2))
    started = time.monotonic()
    # What is left of the deadline once the call has its turn: 2s, or a hair less on a busy
    # machine.
    with pytest.raises(AppFailed, match=r"took more than (2|1\.\d+)s$") as late:
        await worker.apply(None, [], deadline=60)
    assert late.value.failure == "timeout"
    assert time.monotonic() - started < 10


async def test_a_call_waits_its_turn_within_its_deadline(connect: Connect, tmp_path: Path) -> None:
    worker = await connect(wordcraft(stand_in(tmp_path, "hang")), limits=Limits(edit=2))
    failures: list[str] = []

    async def call(deadline: float) -> None:
        with pytest.raises(AppFailed) as failed:
            await worker.inspect(b"PK", deadline=deadline)
        failures.append(str(failed.value))

    async with anyio.create_task_group() as calls:
        calls.start_soon(call, 2)
        await anyio.sleep(0.5)
        calls.start_soon(call, 1)
    busy, late = failures
    assert busy == "timeout: the worker was busy for more than 1s"
    assert re.fullmatch(r"timeout: wordcraft-cli took more than (2|1\.\d+)s", late)


async def test_a_file_past_the_limit_is_too_large(connect: Connect) -> None:
    worker = await connect(FakeApp())
    with pytest.raises(AppFailed, match="the file is larger than") as large:
        await worker.inspect(b"x" * (LIMITS.files + 1), deadline=10)
    assert large.value.failure == "too_large"


async def test_a_reply_past_the_limit_is_too_large(connect: Connect) -> None:
    worker = await connect(FakeApp(), limits=Limits(reply=100))
    with pytest.raises(AppFailed, match="the reply is larger than 100 bytes") as large:
        await worker.apply(
            None, [AppCommand(name="add_paragraph", args={"text": "x"})], deadline=10
        )
    assert large.value.failure == "too_large"


@pytest.fixture
def listening() -> Iterator[str]:
    """A worker over the fake app, served by uvicorn as the entry point serves it, on loopback."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        config = uvicorn.Config(
            worker_app(FakeApp(), token=TOKEN, limits=LIMITS),
            http="h11",
            h11_max_incomplete_event_size=HEAD,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        serving = threading.Thread(target=server.run, kwargs={"sockets": [sock]})
        serving.start()
        while not server.started:
            time.sleep(0.01)
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
        server.should_exit = True
        serving.join()


async def test_a_call_in_any_language_reaches_the_app_over_http(listening: str) -> None:
    worker = await Worker.connect(listening, token=TOKEN)
    batch = [AppCommand(name="add_paragraph", args={"text": "café, 東京"})]
    applied = await worker.apply(None, batch, deadline=10)
    assert applied.inspection.text == "café, 東京"
    await worker.aclose()


async def test_a_batch_as_long_as_a_call_may_be_is_read_whole(listening: str) -> None:
    worker = await Worker.connect(listening, token=TOKEN)
    text = "é" * ((CALL_LIMIT - 200) // 6)  # each escaped as \u00e9
    applied = await worker.apply(
        None, [AppCommand(name="add_paragraph", args={"text": text})], deadline=10
    )
    assert applied.inspection.text == text
    await worker.aclose()


async def test_a_batch_past_the_calls_limit_is_too_large_before_it_is_sent(
    connect: Connect,
) -> None:
    worker = await connect(FakeApp())
    batch = [AppCommand(name="add_paragraph", args={"text": "x" * (CALL_LIMIT + 1)})]
    with pytest.raises(AppFailed, match="the call is larger than") as large:
        await worker.apply(None, batch, deadline=10)
    assert large.value.failure == "too_large"


async def test_a_call_that_isnt_one_is_refused() -> None:
    served = worker_app(FakeApp(), token=TOKEN, limits=LIMITS)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=served), base_url="http://worker"
    ) as client:
        reply = await client.post(
            "/render",
            headers={"Authorization": f"Bearer {TOKEN}", CALL: '{"page": 0}'},
            content=FakeApp.file("x"),
        )
    assert reply.status_code == 422
    assert reply.json() == {"failure": "refused", "message": "the call is not one: 3 errors"}


async def test_another_token_is_refused_before_any_call() -> None:
    transport = httpx.ASGITransport(app=worker_app(FakeApp(), token=TOKEN, limits=LIMITS))
    with pytest.raises(httpx.HTTPStatusError, match="401"):
        await Worker.connect("http://worker", token="guess", transport=transport)


@pytest.mark.parametrize(
    "authorization",
    [None, f"Basic {TOKEN}", TOKEN, f"Bearer{TOKEN}", "Bearer ", f"Bearer {TOKEN}x"],
    ids=["missing", "basic", "bare", "unspaced", "empty", "longer"],
)
async def test_only_the_bearer_token_is_let_in(authorization: str | None) -> None:
    served = worker_app(FakeApp(), token=TOKEN, limits=LIMITS)
    headers = {} if authorization is None else {"Authorization": authorization}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=served), base_url="http://worker"
    ) as client:
        reply = await client.post("/inspect", headers=headers, content=FakeApp.file("x"))
    assert reply.status_code == 401
    assert reply.headers["www-authenticate"] == "Bearer"


def test_limits_below_what_an_apps_cli_needs_are_refused() -> None:
    blender = FakeApp()
    blender.name = "blender"
    with pytest.raises(ValueError, match="blender needs an address space of 4294967296 bytes"):
        worker_app(blender, token=TOKEN, limits=Limits())
    assert worker_app(blender, token=TOKEN, limits=Limits(memory=4 << 30))


def test_an_empty_token_would_admit_anyone() -> None:
    with pytest.raises(ValueError, match="needs a token"):
        worker_app(FakeApp(), token="", limits=LIMITS)
    with pytest.raises(ValueError, match="needs a token"):
        worker_from_environment({"WORKER_TOKEN": "", "WORKER_CLI": "x", "WORKER_VERSION": "1"})


async def test_a_worker_that_cant_be_reached_is_a_crash() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    hello = Hello(name="fake", version="1.0", build=None, talk="save", integration="files:fake")
    client = httpx.AsyncClient(transport=httpx.MockTransport(unreachable), base_url="http://worker")
    async with client:
        with pytest.raises(AppFailed, match="can't be reached") as crashed:
            await Worker(client, hello).inspect(b"", deadline=1)
    assert crashed.value.failure == "crashed"


# ─── the limits the CLI is started under ─────────────────────────────────────


@pytest.mark.parametrize(
    ("script", "limits", "cause"),
    [
        (
            "while True: pass",
            Limits(cpu=1),  # SIGXCPU at the limit, or SIGKILL where the hard limit is the soft one
            f"status ({128 + signal.SIGXCPU}|{128 + signal.SIGKILL})",
        ),
        (
            "open('big', 'wb').write(bytes(2 << 20)); input()",
            Limits(files=1 << 20),
            "File too large",
        ),
        pytest.param(
            "b = bytearray(1 << 30); input()",
            Limits(memory=256 << 20),
            "MemoryError",
            marks=pytest.mark.skipif(
                sys.platform == "darwin", reason="macOS doesn't enforce an address space's limit"
            ),
        ),
    ],
    ids=["cpu", "files", "memory"],
)
async def test_a_cli_past_its_limits_is_ended_as_a_crash(
    tmp_path: Path, script: str, limits: Limits, cause: str
) -> None:
    hostile = wordcraft(cli(tmp_path, "wordcraft-cli", script), limits)
    started = time.monotonic()
    with pytest.raises(AppFailed) as crashed:
        await hostile.inspect(b"PK", deadline=20)
    assert crashed.value.failure == "crashed"
    assert re.search(cause, str(crashed.value))
    assert time.monotonic() - started < 15


def test_the_environment_says_which_wordcraft_it_runs(tmp_path: Path) -> None:
    served = worker_from_environment(
        {
            "WORKER_TOKEN": TOKEN,
            "WORKER_CLI": str(stand_in(tmp_path)),
            "WORKER_VERSION": "0.7.0",
            "WORKER_BUILD": "sha256:abc",
            "WORKER_LIMITS": '{"edit": 5}',
        }
    )
    assert [route.path for route in served.routes if isinstance(route, Route)] == [
        "/",
        "/apply",
        "/inspect",
        "/render",
        "/commands",
    ]


@pytest.mark.parametrize("name", sorted(ADAPTERS))
async def test_the_environment_says_which_app_it_runs_under_the_limits(
    tmp_path: Path, name: str
) -> None:
    hostile = cli(tmp_path, f"{name}-cli", "open('big', 'wb').write(bytes(2 << 20)); input()")
    environ = {"WORKER_APP": name, "WORKER_CLI": str(hostile), "WORKER_VERSION": "1.2.3"}
    app = app_from_environment(environ, Limits(files=1 << 20))
    assert (app.name, app.version) == (name, "1.2.3")
    with pytest.raises(AppFailed, match="File too large") as crashed:
        await app.apply(None, [], deadline=20)
    assert crashed.value.failure == "crashed"


def test_a_short_token_or_wordcrafts_old_names_are_refused(tmp_path: Path) -> None:
    cli = {"WORKER_CLI": str(stand_in(tmp_path)), "WORKER_VERSION": "0.7.0"}
    with pytest.raises(ValueError, match="at least 32 characters"):
        worker_from_environment({**cli, "WORKER_TOKEN": "s3cret"})
    with pytest.raises(ValueError, match="are now WORKER_CLI and WORKER_VERSION"):
        worker_from_environment({"WORKER_TOKEN": TOKEN, "WORDCRAFT_CLI": "x"})


def test_empty_limits_are_the_defaults(tmp_path: Path) -> None:
    environ = {"WORKER_TOKEN": TOKEN, "WORKER_CLI": str(stand_in(tmp_path)), "WORKER_LIMITS": ""}
    assert worker_from_environment({**environ, "WORKER_VERSION": "0.7.0"}).routes


def test_a_worker_runs_every_app_whose_files_lattice_keeps_trusting_only_its_own_confinement() -> (
    None
):
    kept = {name for name, craft in CRAFTS.items() if craft.reach == "file"}
    assert set(ADAPTERS) == kept
    for name, adapter in ADAPTERS.items():
        assert isinstance(adapter, partial) == (CRAFTS[name].roots == "none"), name


def test_a_worker_runs_no_app_it_has_no_adapter_for() -> None:
    environ = {"WORKER_APP": "filmcraft", "WORKER_CLI": "x", "WORKER_VERSION": "1"}
    with pytest.raises(ValueError, match="'filmcraft', and a worker runs one of wordcraft"):
        app_from_environment(environ, LIMITS)


async def test_a_worker_built_before_its_loop_is_opened_as_the_application_starts() -> None:
    served = worker_app(FakeApp(), token=TOKEN, limits=LIMITS, build="sha256:abc")
    worker = Worker.at("http://worker", token=TOKEN, transport=httpx.ASGITransport(app=served))
    with pytest.raises(RuntimeError, match="isn't open"):
        _ = worker.integration
    await worker.open()
    assert (worker.name, worker.build, worker.integration) == ("fake", "sha256:abc", "files:fake")
    await worker.aclose()


def _replying(reply: httpx.Response) -> Worker:
    hello = Hello(name="fake", version="1.0", build=None, talk="save", integration="files:fake")
    transport = httpx.MockTransport(lambda _request: reply)
    return Worker(httpx.AsyncClient(transport=transport, base_url="http://worker"), hello)


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (httpx.Response(500, text="Internal Server Error"), "replied 500 to /inspect"),
        (httpx.Response(200, text="not JSON"), "the worker's reply is not one"),
        (httpx.Response(422, json={"failure": "late"}), "the worker's reply is not one"),
    ],
    ids=["status", "garbled", "unknown-failure"],
)
async def test_a_reply_that_isnt_a_calls_is_a_crash(reply: httpx.Response, message: str) -> None:
    worker = _replying(reply)
    with pytest.raises(AppFailed, match=message) as crashed:
        await worker.inspect(b"", deadline=1)
    assert crashed.value.failure == "crashed"
    await worker.aclose()


async def test_what_the_worker_cant_tell_as_a_reply_is_a_crash(connect: Connect) -> None:
    class Garbled(FakeApp):
        async def apply(self, *_args: object, **_kwargs: object) -> Applied:
            inspection = Inspection.model_construct(fingerprint="not a digest")
            return Applied(content=cast(bytes, 1), inspection=inspection)

    worker = await connect(Garbled())
    with pytest.raises(AppFailed, match="the reply is not one") as crashed:
        await worker.apply(None, [], deadline=10)
    assert crashed.value.failure == "crashed"


async def test_the_deadline_bounds_the_whole_exchange(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow(_request: httpx.Request) -> httpx.Response:
        await anyio.sleep(30)
        return httpx.Response(200)

    hello = Hello(name="fake", version="1.0", build=None, talk="save", integration="files:fake")
    client = httpx.AsyncClient(transport=httpx.MockTransport(slow), base_url="http://worker")
    monkeypatch.setattr("artifactr.files.worker.client.GRACE", 0.1)
    started = time.monotonic()
    async with client:
        with pytest.raises(AppFailed, match="didn't reply to /inspect") as late:
            await Worker(client, hello).inspect(b"", deadline=0.2)
    assert late.value.failure == "timeout"
    assert time.monotonic() - started < 5


@pytest.mark.parametrize(
    ("platform", "limited"),
    [
        ("linux", {resource.RLIMIT_CPU: 3, resource.RLIMIT_FSIZE: 5, resource.RLIMIT_AS: 4}),
        ("darwin", {resource.RLIMIT_CPU: 3, resource.RLIMIT_FSIZE: 5}),
    ],
)
def test_the_launcher_sets_the_limits_then_becomes_the_cli(
    monkeypatch: pytest.MonkeyPatch, platform: str, limited: dict[int, int]
) -> None:
    set_: dict[int, int] = {}
    became: list[list[str]] = []
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(resource, "setrlimit", lambda kind, both: set_.update({kind: both[0]}))
    monkeypatch.setattr(os, "execvp", lambda _file, argv: became.append(argv))
    launcher = Limits(cpu=3, memory=4, files=5).launcher()
    monkeypatch.setattr(sys, "argv", [launcher[2], *launcher[3:], "cli", "mcp", "--x"])
    runpy.run_path(str(CONFINE), run_name="__main__")
    assert set_ == limited
    assert became == [["cli", "mcp", "--x"]]


def test_the_launcher_needs_a_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "main" in runpy.run_path(str(CONFINE)), "imported, it starts nothing"
    monkeypatch.setattr(sys, "argv", ["confine.py", "--cpu=1", "--memory=1", "--files=1", "--"])
    with pytest.raises(SystemExit):
        runpy.run_path(str(CONFINE), run_name="__main__")


def test_the_module_serves_the_worker_on_loopback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    served: list[tuple[str, int]] = []
    monkeypatch.setattr(uvicorn, "run", lambda _app, host, port, **_: served.append((host, port)))
    monkeypatch.setenv("WORKER_TOKEN", TOKEN)
    monkeypatch.setenv("WORKER_CLI", str(stand_in(tmp_path)))
    monkeypatch.setenv("WORKER_VERSION", "0.7.0")
    monkeypatch.delitem(sys.modules, "artifactr.files.worker.__main__")
    runpy.run_module("artifactr.files.worker", run_name="__main__")
    assert served == [("127.0.0.1", 8080)]
