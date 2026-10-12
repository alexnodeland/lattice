"""SQL storage: grantr in PostgreSQL or SQLite, through SQLAlchemy 2's asyncio extension.

Install ``grantr[postgres]`` (asyncpg) or ``grantr[sqlite]`` (aiosqlite). Upgrade the database
with :func:`migrate`, then give :class:`~grantr.grants.Grants` a :class:`SqlStorage`::

    engine = create_async_engine("postgresql+asyncpg://localhost/app")
    await migrate(engine)
    grants = Grants(SqlStorage(engine), catalogs=[artifactr.ACTIONS, reflexr.ACTIONS])

For SQLite, create the engine with :func:`create_sqlite_engine`. :func:`create_schema` creates
the tables without migrations, for tests and prototypes.
"""

from grantr.sql.schema import create_schema, migrate
from grantr.sql.sqlite import create_sqlite_engine
from grantr.sql.storage import SqlStorage

__all__ = ["SqlStorage", "create_schema", "create_sqlite_engine", "migrate"]
