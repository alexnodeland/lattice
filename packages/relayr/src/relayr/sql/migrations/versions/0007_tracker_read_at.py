"""When each tracker follower last read its project, for the portal to say how far behind it is.

The followers' rows already have their tenant's policy (revision 0006), which covers the column.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FOLLOWERS = "relayr_tracker_followers"


def upgrade() -> None:
    """Upgrade the schema."""
    op.add_column(FOLLOWERS, sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade the schema."""
    with op.batch_alter_table(FOLLOWERS) as table:
        table.drop_column("read_at")
