"""Bindings, each kept to its tenant (lattice ADR-0040, grantr ADR-0041).

A binding is stored whole, as JSON, beside its workspace, source and connection, which the
intake and a workspace's reads go by. On PostgreSQL the table gets the policy every other table
has (revision 0003): a transaction sees, changes and adds only its tenant's rows.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "grantr_bindings"

CURRENT = "current_setting('lattice.tenant_id', true)"


def upgrade() -> None:
    """Upgrade the schema."""
    op.create_table(
        TABLE,
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("connection", sa.String(), nullable=False),
        sa.Column("binding", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "id", name=op.f("pk_grantr_bindings")),
    )
    op.create_index("ix_grantr_bindings_connection", TABLE, ["tenant_id", "source", "connection"])
    op.create_index("ix_grantr_bindings_workspace", TABLE, ["tenant_id", "workspace"])
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {TABLE}_tenant ON {TABLE}"
        f" USING (tenant_id = {CURRENT}) WITH CHECK (tenant_id = {CURRENT})"
    )


def downgrade() -> None:
    """Downgrade the schema: dropping the table drops its indexes and policy."""
    op.drop_table(TABLE)
