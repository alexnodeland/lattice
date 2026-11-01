"""Connections, each kept to its tenant (lattice RFC-0014, grantr ADR-0043).

A connection is stored whole, as JSON, beside its person and client, which portr's check on
every call goes by. On PostgreSQL the table gets the policy every other table has (revision
0003): a transaction sees, changes and adds only its tenant's rows.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "grantr_connections"

CURRENT = "current_setting('lattice.tenant_id', true)"


def upgrade() -> None:
    """Upgrade the schema."""
    op.create_table(
        TABLE,
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("connection", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "id", name=op.f("pk_grantr_connections")),
    )
    op.create_index("ix_grantr_connections_user", TABLE, ["tenant_id", "user_id", "client_id"])
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {TABLE}_tenant ON {TABLE}"
        f" USING (tenant_id = {CURRENT}) WITH CHECK (tenant_id = {CURRENT})"
    )


def downgrade() -> None:
    """Downgrade the schema: dropping the table drops its index and policy."""
    op.drop_table(TABLE)
