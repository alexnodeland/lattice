"""Record the message ids used in each workspace, so each is used once.

The table is filled from the stored ``message_posted`` events.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade the schema."""
    messages = op.create_table(
        "artifactr_messages",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id", "workspace_id", "id", name=op.f("pk_artifactr_messages")
        ),
    )
    events = sa.table(
        "artifactr_events",
        sa.column("tenant_id", sa.String()),
        sa.column("workspace_id", sa.String()),
        sa.column("event_type", sa.String()),
        sa.column("envelope", sa.JSON()),
    )
    used = (
        sa.select(
            events.c.tenant_id,
            events.c.workspace_id,
            events.c.envelope[("event", "message_id")].as_string(),
        )
        .where(events.c.event_type == "message_posted")
        .distinct()
    )
    op.execute(messages.insert().from_select(["tenant_id", "workspace_id", "id"], used))


def downgrade() -> None:
    """Downgrade the schema."""
    op.drop_table("artifactr_messages")
