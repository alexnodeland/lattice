"""Settings, on a tenant or in a workspace, kept to their tenant (lattice ADR-0030, ADR-0035).

A tenant's own setting has an empty workspace, so the primary key is free of nulls. Unsetting
keeps the row, with a null value, so its version keeps counting. ``profile_version`` is null
until profiles name the one a value was set under. On PostgreSQL the table gets the policy every
other table has (revision 0003): a transaction sees, changes and adds only its tenant's rows.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "grantr_settings"

CURRENT = "current_setting('lattice.tenant_id', true)"


def upgrade() -> None:
    """Upgrade the schema."""
    op.create_table(
        TABLE,
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("written", sa.JSON(), nullable=False),
        sa.Column("profile_version", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "workspace", "key", name=op.f("pk_grantr_settings")),
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {TABLE}_tenant ON {TABLE}"
        f" USING (tenant_id = {CURRENT}) WITH CHECK (tenant_id = {CURRENT})"
    )


def downgrade() -> None:
    """Downgrade the schema: dropping the table drops its policy."""
    op.drop_table(TABLE)
