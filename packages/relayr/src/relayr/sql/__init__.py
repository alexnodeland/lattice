"""The ledger in SQL: PostgreSQL or SQLite, through SQLAlchemy 2's asyncio extension.

Install `relayr-ai[postgres]` (asyncpg) or `relayr-ai[sqlite]` (aiosqlite). Upgrade the database
with [`migrate`][relayr.sql.migrate], then give the followers a
[`SqlLedger`][relayr.sql.SqlLedger]:

```python
engine = create_async_engine("postgresql+asyncpg://localhost/app")
await migrate(engine)
ledger = SqlLedger(engine)
```

For SQLite, create the engine with [`create_sqlite_engine`][relayr.sql.create_sqlite_engine].
[`create_schema`][relayr.sql.create_schema] creates the tables without migrations, for tests and
prototypes.
"""

from relayr.sql.ledger import SqlLedger
from relayr.sql.schema import create_schema, migrate
from relayr.sql.sqlite import create_sqlite_engine

__all__ = ["SqlLedger", "create_schema", "create_sqlite_engine", "migrate"]
