"""A row for each tenant held to a quota, locked while a put counts what the tenant holds.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "artifactr_files_tenants"
TABLES = (TABLE,)
"""The tables it creates: each names its tenant in ``tenant_id``."""
CURRENT = "current_setting('lattice.tenant_id', true)"


def upgrade() -> None:
    """Upgrade the schema."""
    op.create_table(
        TABLE,
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", name=op.f(f"pk_{TABLE}")),
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
