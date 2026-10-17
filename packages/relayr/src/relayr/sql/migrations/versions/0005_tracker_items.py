"""The keys runs write to their workspace's tracker by (lattice RFC-0004), kept to their tenant.

On PostgreSQL the table gets the policy every other table has (revision 0004): a transaction
sees, changes and adds only its tenant's rows.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "relayr_tracker_items"

CURRENT = "current_setting('lattice.tenant_id', true)"


def upgrade() -> None:
    """Upgrade the schema."""
    op.create_table(
        TABLE,
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("correlation_id", sa.String(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ref", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("written", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id", "workspace_id", "kind", "key", name=op.f("pk_relayr_tracker_items")
        ),
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {TABLE}_tenant ON {TABLE}"
        f" USING (tenant_id = {CURRENT}) WITH CHECK (tenant_id = {CURRENT})"
    )


def downgrade() -> None:
    """Downgrade the schema."""
    op.drop_table(TABLE)
