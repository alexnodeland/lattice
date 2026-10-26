"""The hostile corpus, through the worker, over WordCraft itself.

Every hostile file ends within its deadline, inspected and rendered: the zip bomb and the nested
XML refused by WordCraft's own limits, and the enormous image, which WordCraft 0.11.0 reads without
decoding its pixels, read, with a page no larger than any other (native files ADR-0013). These
run only where `ARTIFACTR_TEST_CRAFT` is `wordcraft` and `ARTIFACTR_TEST_CRAFT_CLI` names its
CLI, as `moon run artifactr:fidelity` sets them; the limits themselves are tested on every pull
request, in `test_worker.py`.
"""

import os
import time
from collections.abc import AsyncIterator

import httpx
import pytest

from artifactr.files.app import AppFailed
from artifactr.files.wordcraft import Subprocess
from artifactr.files.worker import Limits, Worker, worker_app
from tests.files.corpus.harness import pinned
from tests.files.worker.hostile import HOSTILE

pytestmark = [pytest.mark.craft("wordcraft"), pytest.mark.timeout(180)]
LIMITS = Limits()
GRACE = 5
REFUSED = {
    "zip_bomb": "part word/document.xml declares 4294967956 bytes",
    "nested_xml": "XML nesting too deep",
}
"""What WordCraft 0.11.0's own limits refuse each with."""


@pytest.fixture
async def worker() -> AsyncIterator[Worker]:
    wordcraft = Subprocess(
        os.environ["ARTIFACTR_TEST_CRAFT_CLI"],
        version=pinned("wordcraft"),
        limit=LIMITS.files,
        launcher=LIMITS.launcher(),
    )
    served = worker_app(wordcraft, token="t", limits=LIMITS)
    transport = httpx.ASGITransport(app=served)
    worker = await Worker.connect("http://worker", token="t", transport=transport)
    yield worker
    await worker.aclose()


@pytest.mark.parametrize("name", sorted(REFUSED))
async def test_a_hostile_file_is_refused_within_its_deadline(worker: Worker, name: str) -> None:
    hostile = HOSTILE[name]()
    for deadline, call in (
        (LIMITS.edit, lambda: worker.inspect(hostile, deadline=LIMITS.edit)),
        (LIMITS.render, lambda: worker.render(hostile, 1, scale=1, deadline=LIMITS.render)),
    ):
        started = time.monotonic()
        with pytest.raises(AppFailed, match=REFUSED[name]) as refused:
            await call()
        assert refused.value.failure == "refused"
        assert time.monotonic() - started < deadline + GRACE


async def test_the_enormous_image_is_read_without_its_pixels(worker: Worker) -> None:
    hostile = HOSTILE["enormous_image"]()
    started = time.monotonic()
    inspection = await worker.inspect(hostile, deadline=LIMITS.edit)
    assert (inspection.pages, inspection.text, inspection.outline) == (1, "", "")
    page = await worker.render(hostile, 1, scale=1, deadline=LIMITS.render)
    assert page.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(page) < 1 << 20, "a page, not the image's 65,535 pixels a side"
    assert time.monotonic() - started < LIMITS.edit + LIMITS.render
