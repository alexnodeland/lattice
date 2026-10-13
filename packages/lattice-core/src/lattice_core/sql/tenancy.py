"""Row-level security: each transaction tells PostgreSQL its tenant (lattice RFC-0001).

Storage that turns the option on opens its sessions as :class:`TenantSession`, which sets
:data:`SETTING` to its tenant, for the transaction only, as the transaction begins. Policies like
those :func:`tenant_policy` makes then show each transaction only its tenant's rows. A pooled
connection never carries a tenant into its next transaction, and a session that names no tenant
can't begin one.
"""

from collections.abc import Collection
from typing import Any, Final

from sqlalchemy import Connection, event, text
from sqlalchemy.orm import Session, SessionTransaction

__all__ = ["CURRENT", "SETTING", "TENANT", "TenantSession", "grant", "tenant_policy"]

SETTING: Final = "lattice.tenant_id"
"""The PostgreSQL setting that holds a transaction's tenant."""

TENANT: Final = "tenant_id"
"""The key of a :class:`TenantSession`'s tenant in its ``info``."""

CURRENT: Final = f"current_setting('{SETTING}', true)"
"""The transaction's tenant, in SQL: null, or empty, when it names none, which no row's is."""


class TenantSession(Session):
    """A session that tells PostgreSQL its tenant as each transaction begins.

    It sets :data:`SETTING` to the tenant in its ``info``. SQLite has no row-level security,
    so there it sets nothing, but a session must still name its tenant.
    """


@event.listens_for(TenantSession, "after_begin")
def _set_tenant(session: Session, transaction: SessionTransaction, connection: Connection) -> None:
    del transaction
    tenant: Any = session.info.get(TENANT)
    if not isinstance(tenant, str) or not tenant:
        raise RuntimeError("a transaction under row-level security must name its tenant")
    if connection.dialect.name == "postgresql":
        connection.execute(
            text("SELECT set_config(:setting, :tenant, true)"),
            {"setting": SETTING, "tenant": tenant},
        )


def tenant_policy(table: str, column: str = "tenant_id") -> tuple[str, ...]:
    """The DDL that keeps a table's rows to their tenant, on PostgreSQL.

    The policy is enabled, not forced, so the tables' owner isn't held by it. A transaction
    sees, changes and adds only rows whose ``column`` is its tenant; one that names none, or an
    empty one, sees nothing.
    """
    return (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"CREATE POLICY {table}_tenant ON {table}"
        f" USING ({column} = {CURRENT}) WITH CHECK ({column} = {CURRENT})",
    )


def grant(connection: Connection, role: str, tables: Collection[str]) -> None:
    """Let a role use some tables as storage does, and their sequences, on PostgreSQL.

    It grants the role ``USAGE`` on the current schema, reading and writing each table, and
    ``USAGE`` on the sequences the tables own. Granting again changes nothing.
    """
    if connection.dialect.name != "postgresql":
        return
    quote = connection.dialect.identifier_preparer.quote
    grantee = quote(role)
    schema = connection.scalar(text("SELECT current_schema()"))
    connection.execute(text(f"GRANT USAGE ON SCHEMA {quote(str(schema))} TO {grantee}"))
    for table in sorted(tables):
        connection.execute(
            text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {quote(table)} TO {grantee}")
        )
    owned = connection.scalars(
        text(
            "SELECT s.relname FROM pg_class s"
            " JOIN pg_depend d ON d.objid = s.oid AND d.deptype IN ('a', 'i')"
            " JOIN pg_class t ON t.oid = d.refobjid"
            " WHERE s.relkind = 'S' AND t.relname = ANY(:tables)"
            " AND t.relnamespace = current_schema()::regnamespace"
        ),
        {"tables": sorted(tables)},
    )
    for sequence in owned:
        connection.execute(text(f"GRANT USAGE ON SEQUENCE {quote(sequence)} TO {grantee}"))
