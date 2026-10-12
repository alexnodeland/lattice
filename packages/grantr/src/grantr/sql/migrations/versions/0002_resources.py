"""Restricted threads and artifacts.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade the schema."""
    op.create_table(
        "grantr_resources",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("resource_kind", sa.String(), nullable=False),
        sa.Column("resource_workspace", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("restricted", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "resource_kind",
            "resource_workspace",
            "resource_id",
            name=op.f("pk_grantr_resources"),
        ),
    )
    op.create_index(
        "ix_grantr_resources_restricted",
        "grantr_resources",
        ["tenant_id", "resource_workspace", "restricted"],
    )


def downgrade() -> None:
    """Downgrade the schema."""
    op.drop_index("ix_grantr_resources_restricted", table_name="grantr_resources")
    op.drop_table("grantr_resources")
