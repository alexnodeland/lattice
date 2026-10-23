"""Alembic's environment for portalr's migrations, run on a connection already open."""

from alembic import context

from portalr.analytics.sql import VERSION_TABLE, metadata

context.configure(
    connection=context.config.attributes["connection"],
    target_metadata=metadata,
    version_table=VERSION_TABLE,
)
with context.begin_transaction():
    context.run_migrations()
