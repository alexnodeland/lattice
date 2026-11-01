"""Approvals, each kept to its tenant (lattice ADR-0035, grantr ADR-0038).

An approval is stored whole, as JSON, beside its state and workspace, which the pending
approvals are read by. On PostgreSQL the table gets the policy every other table has (revision
0003): a transaction sees, changes and adds only its tenant's rows.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "grantr_approvals"

CURRENT = "current_setting('lattice.tenant_id', true)"


def upgrade() -> None:
    """Upgrade the schema."""
    op.create_table(
        TABLE,
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("approval", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "id", name=op.f("pk_grantr_approvals")),
    )
    op.create_index("ix_grantr_approvals_state", TABLE, ["tenant_id", "state", "workspace"])
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
