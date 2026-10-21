"""Quotas on the blob store, on memory, SQLite and PostgreSQL, as the owner and under row-level
security: a workspace's and a tenant's bytes and files, counted as each put inserts.
"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from artifactr.files.blobs import Blobs, OverQuota, Quota, TooLarge, once
from artifactr.files.manifest import DOCX
from artifactr.workspace import Scope
from tests.files.clock import FakeClock
from tests.files.conftest import BACKENDS, stores_on

ACME = Scope("acme", "w1")
WORKSPACE = Quota(bytes=10, files=2)
TENANT = Quota(bytes=15, files=3)


@pytest.fixture(params=BACKENDS)
async def blobs(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[Blobs]:
    async with stores_on(
        request.param, tmp_path, FakeClock(), workspace_quota=WORKSPACE, tenant_quota=TENANT
    ) as stores:
        yield stores.blobs


async def refused(blobs: Blobs, scope: Scope, artifact_id: str, data: bytes) -> OverQuota:
    with pytest.raises(OverQuota) as raised:
        await blobs.put(scope, artifact_id, once(data), DOCX)
    return raised.value


async def test_a_workspace_holds_its_bytes_to_its_quota(blobs: Blobs) -> None:
    put = await blobs.put(ACME, "a1", once(b"123456"), DOCX)
    over = await refused(blobs, ACME, "a1", b"12345")
    assert (over.over, over.limit) == ("workspace_bytes", 10)
    assert str(over) == "the workspace bytes quota of 10 would be passed"
    assert await blobs.put(ACME, "a1", once(b"1234"), DOCX), "up to the quota"
    assert await blobs.put(ACME, "a1", once(b"123456"), DOCX) == put, "bytes it has add nothing"


async def test_a_workspace_holds_its_files_to_its_quota(blobs: Blobs) -> None:
    await blobs.put(ACME, "a1", once(b"1"), DOCX)
    await blobs.put(ACME, "a2", once(b"2"), DOCX)
    assert await blobs.put(ACME, "a2", once(b"3"), DOCX), "a file's new bytes are no new file"
    over = await refused(blobs, ACME, "a3", b"4")
    assert (over.over, over.limit) == ("workspace_files", 2)


async def test_a_tenant_holds_its_workspaces_together_to_its_quota(blobs: Blobs) -> None:
    await blobs.put(ACME, "a1", once(b"1234567890"), DOCX)
    w2 = Scope("acme", "w2")
    over = await refused(blobs, w2, "a1", b"123456")
    assert (over.over, over.limit) == ("tenant_bytes", 15)
    await blobs.put(w2, "a1", once(b"1"), DOCX)
    await blobs.put(w2, "a2", once(b"2"), DOCX)
    over = await refused(blobs, Scope("acme", "w3"), "a1", b"3")
    assert (over.over, over.limit) == ("tenant_files", 3)
    assert await blobs.put(Scope("globex", "w1"), "a1", once(b"1234567890"), DOCX), (
        "another tenant's are its own"
    )


async def test_puts_at_once_never_pass_a_quota_together(blobs: Blobs) -> None:
    puts = [blobs.put(ACME, f"a{i}", once(b"1234"), DOCX) for i in range(4)]
    outcomes = await asyncio.gather(*puts, return_exceptions=True)
    assert sum(not isinstance(o, BaseException) for o in outcomes) == 2
    assert all(isinstance(o, OverQuota) for o in outcomes if isinstance(o, BaseException))


async def test_bytes_put_together_are_stored_whole_or_not_at_all(blobs: Blobs) -> None:
    with pytest.raises(OverQuota):
        await blobs.put_all(ACME, "a1", [(b"123456", DOCX), (b"12345", "text/plain")])
    assert await blobs.put_all(ACME, "a1", [(b"1234567890", DOCX)]), "nothing of it was kept"
    with pytest.raises(TooLarge):
        await blobs.put_all(ACME, "a2", [(b"x" * (blobs.limit + 1), DOCX)])
