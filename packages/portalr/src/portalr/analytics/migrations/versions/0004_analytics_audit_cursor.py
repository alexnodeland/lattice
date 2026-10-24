"""How far each tenant's audit log in grantr has been read for removals.

Written and read as the tables' owner alone, as the removals owed are: it is no person's own, and
the role the application connects as is granted nothing on it.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "portalr_analytics_audit_cursor"
POLICY = "portalr_analytics_audit_cursor_none"


def upgrade() -> None:
    """Upgrade the schema."""
    op.create_table(
        TABLE,
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("seq", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", name=op.f("pk_" + TABLE)),
    )
    if op.get_bind().dialect.name == "postgresql":
        # As the removals owed: a policy that lets no row through, for the owner alone.
        op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {POLICY} ON {TABLE} USING (false) WITH CHECK (false)")


def downgrade() -> None:
    """Downgrade the schema."""
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"DROP POLICY {POLICY} ON {TABLE}")
    op.drop_table(TABLE)
