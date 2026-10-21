"""The blob store's port, and what every adapter shares: the size limit and the digest.

A blob is keyed by its tenant, workspace and artifact, then its digest, as artifactr's keys
start (lattice RFC-0003, D2). Its access is its artifact's, so a manifest that names another
artifact's digest finds nothing, and revisions of one artifact share its unchanged bytes. Bytes
are never shared across artifacts, or tenants, which would tell an uploader that someone else
has a file.
"""

import hashlib
from collections.abc import AsyncIterable, Callable, Sequence, Set
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal, Protocol, cast

from artifactr.core import ArtifactId
from artifactr.files.manifest import Blob
from artifactr.workspace import Scope

MIB: Final = 1024 * 1024

DEFAULT_LIMIT: Final = 25 * MIB
"""How large a blob may be unless the store is told otherwise."""

MOST: Final = 100 * MIB
"""The largest limit a store may be given: below the most a file sent to the worker may hold,
256 MiB by default, so the store refuses a file before the worker would."""

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


@dataclass(frozen=True)
class Quota:
    """The most a workspace's native files may hold, or a tenant's: bytes, and files.

    A file is an artifact with bytes in the store, so an upload counts from its put, before it
    is committed, until collection deletes the bytes that nothing names. None is no limit.
    """

    bytes: int | None = None
    files: int | None = None


Over = Literal["workspace_bytes", "workspace_files", "tenant_bytes", "tenant_files"]
"""Which quota a put would pass."""


@dataclass(frozen=True)
class Usage:
    """What a workspace's native files hold, or a tenant's, in the store."""

    bytes: int
    files: int


class OverQuota(Exception):
    """New bytes would take a workspace or a tenant past its quota; nothing was stored.

    Attributes:
        over: Which quota.
        limit: The quota, in bytes or files.
    """

    def __init__(self, over: Over, limit: int) -> None:
        super().__init__(f"the {over.replace('_', ' ')} quota of {limit} would be passed")
        self.over: Over = over
        self.limit = limit


def check_quota(
    workspace: tuple[Quota, Usage], tenant: tuple[Quota, Usage], *, size: int, new_file: bool
) -> None:
    """Refuse new bytes that would take the workspace or the tenant past a quota.

    Raises:
        OverQuota: For the first quota passed: the workspace's before the tenant's, bytes first.
    """
    for level, (quota, usage) in (("workspace", workspace), ("tenant", tenant)):
        if quota.bytes is not None and usage.bytes + size > quota.bytes:
            raise OverQuota(cast(Over, f"{level}_bytes"), quota.bytes)
        if new_file and quota.files is not None and usage.files >= quota.files:
            raise OverQuota(cast(Over, f"{level}_files"), quota.files)


class Blobs(Protocol):
    """Where the bytes of native files are kept, by artifact and digest."""

    @property
    def limit(self) -> int:
        """The largest blob, in bytes."""
        ...

    async def put(
        self, scope: Scope, artifact_id: ArtifactId, data: AsyncIterable[bytes], media_type: str
    ) -> Blob:
        """Store bytes for an artifact, and name them.

        The digest and size are computed as the bytes arrive, never taken from a client. Putting
        bytes the artifact already has stores nothing new, and marks them as put now, so that
        [`collect`][artifactr.files.blobs.Blobs.collect] keeps them for the commit that follows.

        Raises:
            TooLarge: If the bytes are larger than the store's limit.
            OverQuota: If new bytes would take the workspace or the tenant past a quota.
        """
        ...

    async def put_all(
        self, scope: Scope, artifact_id: ArtifactId, parts: Sequence[tuple[bytes, str]]
    ) -> list[Blob]:
        """Store several bytes for an artifact at once, each with its media type: all or none.

        The new bytes among them are counted against the quotas together, so a file and what
        was read from it are stored whole, or not at all.

        Raises:
            TooLarge: If any is larger than the store's limit.
            OverQuota: If the new bytes would take the workspace or the tenant past a quota.
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


async def spool(data: AsyncIterable[bytes], limit: int) -> bytes:
    """Read bytes as they arrive, into one buffer.

    Raises:
        TooLarge: As soon as more than `limit` bytes have arrived, before they are kept.
    """
    spooled = bytearray()
    async for chunk in data:
        if len(spooled) + len(chunk) > limit:
            raise TooLarge(limit)
        spooled += chunk
    return bytes(spooled)


def named(parts: Sequence[tuple[bytes, str]], limit: int) -> list[Blob]:
    """Each of the bytes named by its digest, size and media type.

    Raises:
        TooLarge: If any is larger than `limit`.
    """
    if any(len(content) > limit for content, _ in parts):
        raise TooLarge(limit)
    return [
        Blob(sha256=hashlib.sha256(content).hexdigest(), size=len(content), media_type=media_type)
        for content, media_type in parts
    ]


async def once(data: bytes) -> AsyncIterable[bytes]:
    """Bytes already in memory, as the stream that `Blobs.put` takes."""
    yield data
