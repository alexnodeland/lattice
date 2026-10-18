"""What the tracker followers read (lattice RFC-0004, phase 2), kept to their tenant.

Each workspace bound to a tracker project gets a follower's row, with its lease and cursor; a
row per item of the project, with its last snapshot and relayr's recent writes to it; and the
changes it could not publish. On PostgreSQL each table gets the policy every other table has
(revision 0004): a transaction sees, changes and adds only its tenant's rows.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FOLLOWERS = "relayr_tracker_followers"
SNAPSHOTS = "relayr_tracker_snapshots"
DEAD_LETTERS = "relayr_tracker_dead_letters"

CURRENT = "current_setting('lattice.tenant_id', true)"


def _workspace() -> list[sa.Column[str]]:
    return [
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
    ]


def upgrade() -> None:
    """Upgrade the schema."""
    op.create_table(
        FOLLOWERS,
        *_workspace(),
        sa.Column("project", sa.String(), nullable=True),
        sa.Column("cursor_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor_id", sa.String(), nullable=True),
        sa.Column("swept_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("holder", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "workspace_id", name=op.f(f"pk_{FOLLOWERS}")),
    )
    op.create_table(
        SNAPSHOTS,
        *_workspace(),
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("item", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("comments_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("writes", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id", "workspace_id", "item_id", name=op.f(f"pk_{SNAPSHOTS}")
        ),
    )
    op.create_table(
        DEAD_LETTERS,
        *_workspace(),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("error", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id", "workspace_id", "event_id", name=op.f(f"pk_{DEAD_LETTERS}")
        ),
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in (FOLLOWERS, SNAPSHOTS, DEAD_LETTERS):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant ON {table}"
            f" USING (tenant_id = {CURRENT}) WITH CHECK (tenant_id = {CURRENT})"
        )


def downgrade() -> None:
    """Downgrade the schema."""
    for table in (DEAD_LETTERS, SNAPSHOTS, FOLLOWERS):
        op.drop_table(table)
