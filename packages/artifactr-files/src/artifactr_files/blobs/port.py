"""The blob store's port, and what every adapter shares: the size limit and the digest.

A blob is keyed by its tenant, workspace and artifact, then its digest, as artifactr's keys
start (lattice RFC-0003, D2). Its access is its artifact's, so a manifest that names another
artifact's digest finds nothing, and revisions of one artifact share its unchanged bytes. Bytes
are never shared across artifacts, or tenants, which would tell an uploader that someone else
has a file.
"""

import hashlib
from collections.abc import AsyncIterable, Callable, Set
from datetime import UTC, datetime
from typing import Final, Protocol

from artifactr.core import ArtifactId
from artifactr.workspace import Scope
from artifactr_files.manifest import Blob

MIB: Final = 1024 * 1024

DEFAULT_LIMIT: Final = 25 * MIB
"""How large a blob may be unless the store is told otherwise."""

MOST: Final = 100 * MIB
"""The largest limit a store may be given."""

Clock = Callable[[], datetime]
"""Returns the current time; injectable, so that tests control when a blob was put."""


def utc_now() -> datetime:
    """The current time, in UTC."""
    return datetime.now(UTC)


class TooLarge(Exception):
    """The bytes are larger than the store's limit; nothing was stored.

    Attributes:
        limit: The store's limit, in bytes.
    """

    def __init__(self, limit: int) -> None:
        super().__init__(f"the file is larger than {limit} bytes")
        self.limit = limit


class Blobs(Protocol):
    """Where the bytes of native files are kept, by artifact and digest."""

    async def put(
        self, scope: Scope, artifact_id: ArtifactId, data: AsyncIterable[bytes], media_type: str
    ) -> Blob:
        """Store bytes for an artifact, and name them.

        The digest and size are computed as the bytes arrive, never taken from a client. Putting
        bytes the artifact already has stores nothing new, and marks them as put now, so that
        [`collect`][artifactr_files.blobs.Blobs.collect] keeps them for the commit that follows.

        Raises:
            TooLarge: If the bytes are larger than the store's limit.
        """
        ...

    async def get(self, scope: Scope, artifact_id: ArtifactId, sha256: str) -> bytes | None:
        """Return an artifact's bytes with this digest, or None if it has none."""
        ...

    async def collect(
        self, scope: Scope, referenced: Set[tuple[ArtifactId, str]], *, before: datetime
    ) -> int:
        """Delete the workspace's blobs last put before `before` that aren't `referenced`.

        A blob put again meanwhile is kept, whatever `referenced` says.

        Args:
            scope: The workspace.
            referenced: Every `(artifact, digest)` a revision or a pending proposal names.
            before: Only blobs last put before this, such as a day ago.

        Returns:
            How many were deleted.
        """
        ...


def check_limit(limit: int) -> int:
    """Return a store's limit, refused unless it is from one byte to 100 MiB.

    Raises:
        ValueError: If it is out of that range.
    """
    if not 1 <= limit <= MOST:
        raise ValueError(f"a blob's limit is between 1 and {MOST} bytes, not {limit}")
    return limit


async def spool(data: AsyncIterable[bytes], limit: int) -> tuple[bytes, str]:
    """Read bytes as they arrive, and return them with their SHA-256.

    Raises:
        TooLarge: As soon as more than `limit` bytes have arrived.
    """
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    size = 0
    async for chunk in data:
        size += len(chunk)
        if size > limit:
            raise TooLarge(limit)
        digest.update(chunk)
        chunks.append(chunk)
    return b"".join(chunks), digest.hexdigest()


async def once(data: bytes) -> AsyncIterable[bytes]:
    """Bytes already in memory, as the stream that `Blobs.put` takes."""
    yield data
