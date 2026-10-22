"""People's answers to product analytics.

Revision ID: 0001
Revises:
Create Date: 2026-10-22
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
        "portalr_analytics_consent",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("given", sa.Boolean(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_portalr_analytics_consent")),
    )


def downgrade() -> None:
    """Downgrade the schema."""
    op.drop_table("portalr_analytics_consent")
