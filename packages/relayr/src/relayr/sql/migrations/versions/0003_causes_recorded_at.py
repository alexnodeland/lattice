"""When each cause was recorded, so causes can be forgotten.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade the schema.

    Causes recorded before this revision are given the time it runs, and are forgotten a time
    to live after it.
    """
    with op.batch_alter_table("relayr_causes") as table:
        table.add_column(
            sa.Column(
                "recorded_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            )
        )
    with op.batch_alter_table("relayr_causes") as table:
        table.alter_column("recorded_at", server_default=None)
    op.create_index(
        "ix_relayr_causes_recorded",
        "relayr_causes",
        ["tenant_id", "workspace_id", "recorded_at"],
    )


def downgrade() -> None:
    """Downgrade the schema."""
    op.drop_index("ix_relayr_causes_recorded", table_name="relayr_causes")
    with op.batch_alter_table("relayr_causes") as table:
        table.drop_column("recorded_at")
