"""Blobs in a SQL database: PostgreSQL's `bytea`, SQLite's `BLOB`.

Every database call is awaited to its end, even when its caller is cancelled, and the
cancellation is raised after it, as in artifactr's storage (artifactr ADR-0047).
"""

from collections.abc import AsyncIterable, Set
from datetime import datetime
from itertools import batched
from typing import Final

from sqlalchemy import ColumnElement, delete, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from artifactr.core import ArtifactId
from artifactr.files.blobs import DEFAULT_LIMIT, Clock, Quota
from artifactr.files.blobs.port import Usage, check_limit, check_quota, spool, utc_now
from artifactr.files.manifest import Blob
from artifactr.files.sql.tables import BlobRow, TenantRow
from artifactr.workspace import Scope
from lattice_core.sql.sessions import awaited_to_the_end, lock_row
from lattice_core.sql.tenancy import TENANT_KEY, TenantSession

BATCH: Final = 500
"""How many blobs one statement of a collection deletes, to stay within a database's parameters."""


class SqlBlobs:
    """The [`Blobs`][artifactr.files.blobs.Blobs] port in a SQL database.

    Create the tables with [`migrate`][artifactr.files.sql.migrate] first. The same code runs on
    PostgreSQL and on SQLite, whose engines must come from
    [`create_sqlite_engine`][artifactr.files.sql.create_sqlite_engine].

    Args:
        engine: The database. The store does not dispose of it.
        clock: Returns the current time, which a put is stamped with.
        limit: The largest blob, in bytes: 25 MiB unless given, and at most 100 MiB. The bytes
            are held in memory as they arrive, up to it.
        row_level_security: Whether each transaction names its tenant to PostgreSQL, whose
            policies, which the migrations create, then show it only that tenant's rows.
        workspace_quota: The most each workspace's native files may hold: no limit by default.
        tenant_quota: The most each tenant's native files may hold: no limit by default. With
            either, a put of new bytes counts what is held in the same transaction as it
            inserts them, under a lock on the tenant's row, so puts at once can't both pass.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        clock: Clock = utc_now,
        limit: int = DEFAULT_LIMIT,
        row_level_security: bool = False,
        workspace_quota: Quota | None = None,
        tenant_quota: Quota | None = None,
    ) -> None:
        self._sessions = async_sessionmaker(
            engine,
            expire_on_commit=False,
            sync_session_class=TenantSession if row_level_security else Session,
        )
        self._clock = clock
        self._limit = check_limit(limit)
        self._quotas = (workspace_quota or Quota(), tenant_quota or Quota())
        self._held = workspace_quota is not None or tenant_quota is not None

    def _session(self, scope: Scope) -> AsyncSession:
        return self._sessions(info={TENANT_KEY: scope.tenant_id})

    async def put(
        self, scope: Scope, artifact_id: ArtifactId, data: AsyncIterable[bytes], media_type: str
    ) -> Blob:
        """Store bytes for an artifact, and name them, as `Blobs.put` does."""
        content, sha256 = await spool(data, self._limit)
        await self._store(scope, artifact_id, sha256, content)
        return Blob(sha256=sha256, size=len(content), media_type=media_type)

    @awaited_to_the_end
    async def _store(
        self, scope: Scope, artifact_id: ArtifactId, sha256: str, content: bytes
    ) -> None:
        """Insert the bytes, within the quotas, or mark the ones already there as put now."""
        now = self._clock()
        new = BlobRow(
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            artifact_id=artifact_id,
            sha256=sha256,
            size=len(content),
            data=content,
            last_put=now,
        )
        async with self._session(scope) as session, session.begin():
            key = (scope.tenant_id, scope.workspace_id, artifact_id, sha256)
            if self._held:
                await self._check_quotas(session, scope, key, len(content))
            row = await lock_row(session, BlobRow, key, new)
            row.last_put = now

    async def _check_quotas(
        self, session: AsyncSession, scope: Scope, key: tuple[str, ...], size: int
    ) -> None:
        """Refuse new bytes past a quota, counted under the tenant's lock."""
        tenant_id = scope.tenant_id
        await lock_row(session, TenantRow, tenant_id, TenantRow(tenant_id=tenant_id))
        if await session.get(BlobRow, key) is not None:
            return
        workspace, tenant = self._quotas
        artifact = await session.scalar(
            select(func.count()).where(*_workspace(scope), BlobRow.artifact_id == key[2])
        )
        check_quota(
            (workspace, await _usage(session, _workspace(scope))),
            (tenant, await _usage(session, (BlobRow.tenant_id == tenant_id,))),
            size=size,
            new_file=not artifact,
        )

    @awaited_to_the_end
    async def get(self, scope: Scope, artifact_id: ArtifactId, sha256: str) -> bytes | None:
        """Return an artifact's bytes with this digest, or None if it has none."""
        async with self._session(scope) as session:
            return await session.scalar(
                select(BlobRow.data).where(*_key(scope, artifact_id, sha256))
            )

    @awaited_to_the_end
    async def collect(
        self, scope: Scope, referenced: Set[tuple[ArtifactId, str]], *, before: datetime
    ) -> int:
        """Delete the workspace's unreferenced blobs last put before `before`; return how many.

        The blobs old enough are read, and those not referenced deleted in batches, each
        statement checking again that the blob is still old enough: a blob put again meanwhile,
        for a revision about to be committed, is kept.
        """
        workspace = _workspace(scope)
        stale = BlobRow.last_put < before
        key = tuple_(BlobRow.artifact_id, BlobRow.sha256)
        async with self._session(scope) as session, session.begin():
            connection = await session.connection()
            old = await connection.execute(
                select(BlobRow.artifact_id, BlobRow.sha256).where(*workspace, stale)
            )
            doomed = [(a, d) for a, d in old if (a, d) not in referenced]
            deleted = 0
            for keys in batched(doomed, BATCH):
                done = await connection.execute(
                    delete(BlobRow).where(*workspace, stale, key.in_(keys))
                )
                deleted += done.rowcount
        return deleted


async def _usage(session: AsyncSession, where: tuple[ColumnElement[bool], ...]) -> Usage:
    """What the blobs `where` picks out hold: their bytes, and the artifacts they are of."""
    held = await session.scalar(select(func.coalesce(func.sum(BlobRow.size), 0)).where(*where))
    artifacts = select(BlobRow.workspace_id, BlobRow.artifact_id).where(*where).distinct()
    files = await session.scalar(select(func.count()).select_from(artifacts.subquery()))
    return Usage(bytes=int(held or 0), files=files or 0)


def _workspace(scope: Scope) -> tuple[ColumnElement[bool], ...]:
    return (BlobRow.tenant_id == scope.tenant_id, BlobRow.workspace_id == scope.workspace_id)


def _key(scope: Scope, artifact_id: ArtifactId, sha256: str) -> tuple[ColumnElement[bool], ...]:
    return (*_workspace(scope), BlobRow.artifact_id == artifact_id, BlobRow.sha256 == sha256)
