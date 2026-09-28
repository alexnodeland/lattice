"""SQL storage: workspaces in PostgreSQL or SQLite, through SQLAlchemy 2's asyncio extension.

Install ``artifactr[postgres]`` (asyncpg) or ``artifactr[sqlite]`` (aiosqlite). Upgrade the
database with :func:`migrate`, then open workspaces over a :class:`SqlStorage`::

    engine = create_async_engine("postgresql+asyncpg://localhost/app")
    await migrate(engine)
    workspaces = Workspaces(SqlStorage(engine))

For SQLite, create the engine with :func:`create_sqlite_engine`. :func:`create_schema` creates
the tables without migrations, for tests and prototypes.
"""

from artifactr.sql.schema import create_schema, migrate
from artifactr.sql.sqlite import create_sqlite_engine
from artifactr.sql.storage import SqlStorage

__all__ = ["SqlStorage", "create_schema", "create_sqlite_engine", "migrate"]
