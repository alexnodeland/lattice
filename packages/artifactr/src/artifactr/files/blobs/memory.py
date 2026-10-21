"""Blobs in memory, for tests, examples and single-process prototypes."""

from collections.abc import AsyncIterable, Set
from datetime import datetime

from artifactr.core import ArtifactId
from artifactr.files.blobs.port import (
    DEFAULT_LIMIT,
    Clock,
    Quota,
    Usage,
    check_limit,
    check_quota,
    spool,
    utc_now,
)
from artifactr.files.manifest import Blob
from artifactr.workspace import Scope

type _Key = tuple[str, str, ArtifactId, str]


class InMemoryBlobs:
    """The whole [`Blobs`][artifactr.files.blobs.Blobs] port in memory: nothing outlives it.

    Args:
        clock: Returns the current time, which a put is stamped with.
        limit: The largest blob, in bytes: 25 MiB unless given, and at most 100 MiB.
        workspace_quota: The most each workspace's native files may hold: no limit by default.
        tenant_quota: The most each tenant's native files may hold: no limit by default.
    """

    def __init__(
        self,
        *,
        clock: Clock = utc_now,
        limit: int = DEFAULT_LIMIT,
        workspace_quota: Quota | None = None,
        tenant_quota: Quota | None = None,
    ) -> None:
        self._clock = clock
        self._limit = check_limit(limit)
        self._quotas = (workspace_quota or Quota(), tenant_quota or Quota())
        self._blobs: dict[_Key, tuple[bytes, datetime]] = {}

    async def put(
        self, scope: Scope, artifact_id: ArtifactId, data: AsyncIterable[bytes], media_type: str
    ) -> Blob:
        """Store bytes for an artifact, and name them, as `Blobs.put` does."""
        content, sha256 = await spool(data, self._limit)
        key = (scope.tenant_id, scope.workspace_id, artifact_id, sha256)
        if key not in self._blobs:
            workspace, tenant = self._quotas
            check_quota(
                (workspace, self._usage(key[:2])),
                (tenant, self._usage(key[:1])),
                size=len(content),
                new_file=not any(k[:3] == key[:3] for k in self._blobs),
            )
        self._blobs[key] = (content, self._clock())
        return Blob(sha256=sha256, size=len(content), media_type=media_type)

    def _usage(self, prefix: tuple[str, ...]) -> Usage:
        """What the blobs whose keys start with `prefix` hold: a workspace's, or a tenant's."""
        mine = {k: content for k, (content, _) in self._blobs.items() if k[: len(prefix)] == prefix}
        return Usage(
            bytes=sum(len(content) for content in mine.values()),
            files=len({k[:3] for k in mine}),
        )

    async def get(self, scope: Scope, artifact_id: ArtifactId, sha256: str) -> bytes | None:
        """Return an artifact's bytes with this digest, or None if it has none."""
        found = self._blobs.get((scope.tenant_id, scope.workspace_id, artifact_id, sha256))
        return None if found is None else found[0]

    async def collect(
        self, scope: Scope, referenced: Set[tuple[ArtifactId, str]], *, before: datetime
    ) -> int:
        """Delete the workspace's unreferenced blobs last put before `before`; return how many."""
        doomed = [
            key
            for key, (_, last_put) in self._blobs.items()
            if key[:2] == (scope.tenant_id, scope.workspace_id)
            and last_put < before
            and key[2:] not in referenced
        ]
        for key in doomed:
            del self._blobs[key]
        return len(doomed)
