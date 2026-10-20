"""The hostile corpus, through the worker, over WordCraft itself: RFC-0003's phase 3 exit.

Every hostile file must end within its deadline, inspected and rendered, and never past a limit
unnoticed: the zip bomb and the nested XML in a typed failure, and the enormous image, which
WordCraft 0.7.0 reads without decoding its pixels, in a reading. These run only where
`ARTIFACTR_TEST_CRAFT` is `wordcraft` and `ARTIFACTR_TEST_CRAFT_CLI` names its CLI, as
`moon run artifactr:fidelity` sets them; the limits themselves are tested on every pull request,
in `test_worker.py`.
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
REFUSED = {"zip_bomb", "nested_xml"}


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


@pytest.mark.parametrize("name", sorted(HOSTILE))
async def test_a_hostile_file_ends_within_its_deadline(worker: Worker, name: str) -> None:
    hostile = HOSTILE[name]()
    for deadline, call in (
        (LIMITS.edit, lambda: worker.inspect(hostile, deadline=LIMITS.edit)),
        (LIMITS.render, lambda: worker.render(hostile, 1, scale=1, deadline=LIMITS.render)),
    ):
        started = time.monotonic()
        if name in REFUSED:
            with pytest.raises(AppFailed):
                await call()
        else:
            await call()
        assert time.monotonic() - started < deadline + GRACE
