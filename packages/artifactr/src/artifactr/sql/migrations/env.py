"""Alembic's environment for artifactr's migrations.

:func:`artifactr.sql.migrate` runs it on a connection it has already opened, inside the
transaction it commits, so the migrations are atomic wherever the database's DDL is.
"""

from alembic import context

from artifactr.sql.tables import VERSION_TABLE, metadata

context.configure(
    connection=context.config.attributes["connection"],
    target_metadata=metadata,
    version_table=VERSION_TABLE,
)
with context.begin_transaction():
    context.run_migrations()
