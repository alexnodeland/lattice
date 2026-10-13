"""SQLite engines that serialize transactions the way :class:`~artifactr.sql.SqlStorage` needs.

SQLite has no row locks and ignores ``FOR UPDATE``. Instead, every transaction takes the
database's write lock as it begins (``BEGIN IMMEDIATE``), so a transaction's reads cannot go
stale before it writes, and concurrent writers wait for each other instead of failing.

Since transactions run one at a time anyway, an engine keeps a single connection. A process's
transactions queue for it and take turns in the order they begin, as they do on in-memory
storage, instead of polling for the write lock; only other processes contend for the lock.

lattice-core holds the engine, which every library's SQL storage shares (lattice
ADR-0018); this module re-exports it. Install ``artifactr-ai[sqlite]`` for its async driver,
aiosqlite.
"""

from lattice_core.sql.sqlite import create_sqlite_engine

__all__ = ["create_sqlite_engine"]
