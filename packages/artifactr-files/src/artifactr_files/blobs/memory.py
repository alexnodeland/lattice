"""Blobs in memory, for tests, examples and single-process prototypes."""

from collections.abc import AsyncIterable, Set
from datetime import datetime

from artifactr.core import ArtifactId
from artifactr.workspace import Scope
from artifactr_files.blobs.port import DEFAULT_LIMIT, Clock, check_limit, spool, utc_now
from artifactr_files.manifest import Blob

type _Key = tuple[str, str, ArtifactId, str]


class InMemoryBlobs:
    """The whole [`Blobs`][artifactr_files.blobs.Blobs] port in memory: nothing outlives it.

    Args:
        clock: Returns the current time, which a put is stamped with.
        limit: The largest blob, in bytes: 25 MiB unless given, and at most 100 MiB.
    """

    def __init__(self, *, clock: Clock = utc_now, limit: int = DEFAULT_LIMIT) -> None:
        self._clock = clock
        self._limit = check_limit(limit)
        self._blobs: dict[_Key, tuple[bytes, datetime]] = {}

    async def put(
        self, scope: Scope, artifact_id: ArtifactId, data: AsyncIterable[bytes], media_type: str
    ) -> Blob:
        """Store bytes for an artifact, and name them, as `Blobs.put` does."""
        content, sha256 = await spool(data, self._limit)
        self._blobs[(scope.tenant_id, scope.workspace_id, artifact_id, sha256)] = (
            content,
            self._clock(),
        )
        return Blob(sha256=sha256, size=len(content), media_type=media_type)

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
