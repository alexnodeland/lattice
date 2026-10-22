"""Probe one crafting app's worker, from a container on its network: scripts/check-files runs it.

Usage: python -I _files_probe.py URL APP VERSION   (WORKER_TOKEN in the environment)

It runs in the worker's own image, which has artifactr and the app's release in /opt/craft, and
checks:

- the release's licence files are there, and each notice `CRAFTS` lists, such as PdfCraft's OCR
  models' attribution and licences
- the worker runs the app at its pinned version, and refuses a request without its token
- a new file is made, read back and, if the app renders, rendered
- hostile files each end within their deadline, in a typed failure: a zip bomb, a file past the
  worker's limit, and bytes that are no file of the app's. The bomb is a zip: an app whose files
  are zips reads into it, and one whose files aren't refuses it at its first bytes

Each check prints `ok: ...` or `FAIL: ...`; it exits 1 if any failed.
"""

import asyncio
import io
import os
import re
import sys
import time
import zipfile
from collections.abc import Awaitable
from pathlib import Path

import httpx
from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.craft import CRAFTS
from artifactr.files.worker import Limits, Worker

DEADLINE = 30.0
LICENCE = re.compile(r"(LICEN[CS]E|COPYING)", re.IGNORECASE)
DRAWN = {
    "freecad": [AppCommand(name="box", args={"length": 10, "width": 10, "height": 10})],
    "blender": [
        AppCommand(name="cube", args={"size": 2}),
        AppCommand(name="camera", args={"at": [6, -6, 4]}),
        AppCommand(name="light", args={"type": "sun", "energy": 3, "at": [4, -4, 8]}),
    ],
    "figcraft": [
        AppCommand(name="frame.create", args={"x": 0, "y": 0, "width": 200, "height": 100})
    ],
}
"""What a new file is given, for an app whose blank file has nothing to render."""
failed: list[str] = []
"""What failed, which the exit status tells."""


def report(passed: bool, what: str) -> None:
    print(f"{'ok' if passed else 'FAIL'}: {what}", flush=True)
    if not passed:
        failed.append(what)


def bomb() -> bytes:
    """A zip whose one part inflates to 1 GiB of zeros, past the worker's limit on any file."""
    packed = io.BytesIO()
    with zipfile.ZipFile(packed, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        with archive.open("content.xml", "w", force_zip64=True) as part:
            zeros = bytes(1 << 20)
            for _ in range(1 << 10):
                part.write(zeros)
    return packed.getvalue()


async def refused(worker: Worker, what: str, call: Awaitable[object], kinds: set[str]) -> None:
    """Check that a call ends within its deadline, in one of these typed failures."""
    started = time.monotonic()
    try:
        await call
    except AppFailed as failed:
        took = time.monotonic() - started
        report(
            failed.failure in kinds and took < DEADLINE + 5,
            f"{worker.name}: {what} is {failed.failure}, in {took:.1f}s"
            + ("" if failed.failure in kinds else f": {str(failed)[:300]}"),
        )
    else:
        report(False, f"{worker.name}: {what} was read")


def notices(app: str) -> None:
    """Check that the release's licences, and each notice the app declares, travel with its CLI."""
    release = Path("/opt/craft")
    licences = sorted(path.name for path in release.rglob("*") if LICENCE.match(path.name))
    report(bool(licences), f"{app}: its release's licences are in its image: {', '.join(licences)}")
    for notice in CRAFTS[app].notices:
        for file in notice.files:
            report((release / file).is_file(), f"{app}: {notice.licence} {file} is in its image")


async def main(url: str, app: str, version: str) -> None:
    notices(app)
    token = os.environ["WORKER_TOKEN"]
    async with httpx.AsyncClient(base_url=url) as anonymous:
        status = (await anonymous.get("/")).status_code
    report(status == 401, f"{app}: a request without the token is refused ({status})")

    worker = await Worker.connect(url, token=token)
    try:
        report(
            (worker.name, worker.version) == (app, version),
            f"{app}: the worker runs {worker.name} {worker.version}",
        )
        made = await worker.apply(None, DRAWN.get(app, []), deadline=DEADLINE)
        read = await worker.inspect(made.content, deadline=DEADLINE)
        report(
            read.media_type in CRAFTS[app].formats,
            f"{app}: a new file is made and read back, as {read.media_type}",
        )
        if CRAFTS[app].render:
            png = await worker.render(made.content, 1, scale=1.0, deadline=DEADLINE)
            report(png.startswith(b"\x89PNG"), f"{app}: its first page renders, {len(png)} bytes")

        limit = Limits().files
        await refused(
            worker,
            "a zip bomb",
            worker.inspect(bomb(), deadline=DEADLINE),
            {"too_large", "refused"},
        )
        await refused(
            worker,
            "a file past the limit",
            worker.inspect(bytes(limit + 1), deadline=DEADLINE),
            {"too_large"},
        )
        await refused(
            worker,
            "bytes of no format",
            worker.inspect(b"not a file", deadline=DEADLINE),
            {"refused"},
        )
    finally:
        await worker.aclose()


if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:4]))
    sys.exit(1 if failed else 0)
