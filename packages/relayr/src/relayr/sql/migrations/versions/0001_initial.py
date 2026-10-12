"""The initial schema.

Revision ID: 0001
Revises:
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade the schema."""
    op.create_table(
        "relayr_followers",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("holder", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "workspace_id", name=op.f("pk_relayr_followers")),
    )
    op.create_table(
        "relayr_dead_letters",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("envelope_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("error", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id", "workspace_id", "seq", name=op.f("pk_relayr_dead_letters")
        ),
    )


def downgrade() -> None:
    """Downgrade the schema."""
    op.drop_table("relayr_dead_letters")
    op.drop_table("relayr_followers")
