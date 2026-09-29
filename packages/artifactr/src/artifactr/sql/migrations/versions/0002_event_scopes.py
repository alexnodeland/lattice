"""Keep each event's type and thread in columns, so reads of some threads filter in the database.

Both are filled from the stored envelopes: the type from ``event.type``, and the thread from
the envelope's ``thread_id``.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29
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
    op.add_column("artifactr_events", sa.Column("event_type", sa.String(), nullable=True))
    op.add_column("artifactr_events", sa.Column("thread_id", sa.String(), nullable=True))
    events = sa.table(
        "artifactr_events",
        sa.column("envelope", sa.JSON()),
        sa.column("event_type", sa.String()),
        sa.column("thread_id", sa.String()),
    )
    op.execute(
        events.update().values(
            event_type=events.c.envelope[("event", "type")].as_string(),
            thread_id=events.c.envelope["thread_id"].as_string(),
        )
    )
    # SQLite cannot add NOT NULL to a column, so batch mode copies the table there.
    with op.batch_alter_table("artifactr_events") as batch:
        batch.alter_column("event_type", existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    """Downgrade the schema."""
    with op.batch_alter_table("artifactr_events") as batch:
        batch.drop_column("thread_id")
        batch.drop_column("event_type")
