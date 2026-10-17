"""Blobs and check-outs in SQL: PostgreSQL or SQLite, through SQLAlchemy 2's asyncio extension.

Install `artifactr-files-ai[postgres]` (asyncpg) or `artifactr-files-ai[sqlite]` (aiosqlite).
Upgrade the database with [`migrate`][artifactr_files.sql.migrate], then give
[`NativeFiles`][artifactr_files.files.NativeFiles] the stores:

```python
engine = create_async_engine("postgresql+asyncpg://localhost/app")
await migrate(engine)
files = NativeFiles(SqlBlobs(engine), SqlCheckouts(engine), app)
```

With row-level security, migrate as the tables' owner, granting a role that owns nothing the
tables, and give the stores that role's engine with `row_level_security=True`, as artifactr's
storage has it (artifactr ADR-0066). For SQLite, create the engine with
[`create_sqlite_engine`][artifactr_files.sql.create_sqlite_engine].
[`create_schema`][artifactr_files.sql.create_schema] creates the tables without migrations, for
tests and prototypes.
"""

from artifactr_files.sql.blobs import SqlBlobs
from artifactr_files.sql.checkouts import SqlCheckouts
from artifactr_files.sql.schema import create_schema, migrate
from lattice_core.sql.sqlite import create_sqlite_engine

__all__ = ["SqlBlobs", "SqlCheckouts", "create_schema", "create_sqlite_engine", "migrate"]
