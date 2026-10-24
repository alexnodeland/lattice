"""The deletions owed people removed from a tenant: their events there, up to their removal.

Written and read as the tables' owner alone: an admin removes another person, so the row is no
person's own, and the role the application connects as is granted nothing on it.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "portalr_analytics_removals_owed"
POLICY = "portalr_analytics_removals_owed_none"


def upgrade() -> None:
    """Upgrade the schema."""
    op.create_table(
        TABLE,
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "tenant_id", name=op.f("pk_" + TABLE)),
    )
    if op.get_bind().dialect.name == "postgresql":
        # A policy that lets no row through: the owner, who bypasses it, reads and writes it, and
        # a grant made by default, as Supabase makes to its public roles, reads nothing. A table
        # of the application's has a policy, as stackr's smoke test holds every one to.
        op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {POLICY} ON {TABLE} USING (false) WITH CHECK (false)")


def downgrade() -> None:
    """Downgrade the schema."""
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"DROP POLICY {POLICY} ON {TABLE}")
    op.drop_table(TABLE)
